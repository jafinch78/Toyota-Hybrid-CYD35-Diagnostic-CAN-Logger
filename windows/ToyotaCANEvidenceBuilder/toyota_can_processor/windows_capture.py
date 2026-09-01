from __future__ import annotations

import asyncio
import json
import os
import platform
import statistics
import struct
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .dependency_setup import hidden_process_kwargs, resolve_tool


SERVICE_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40001"
COMMAND_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40002"
RESPONSE_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40003"


class CydBleClient:
    def __init__(self) -> None:
        self.client = None
        self.sequence = 1
        self.pending: dict[int, tuple[str, int, asyncio.Future]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.name = ""
        self.address = ""

    async def connect(self, timeout: float = 15.0) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as error:
            raise RuntimeError("Windows BLE capture requires: py -m pip install bleak") from error
        self.loop = asyncio.get_running_loop()

        def filter_device(device, advertisement) -> bool:
            services = [item.lower() for item in (advertisement.service_uuids or [])]
            return SERVICE_UUID in services or (device.name or "").startswith("ToyotaCYD-")

        device = await BleakScanner.find_device_by_filter(filter_device, timeout=timeout)
        if device is None:
            raise RuntimeError("No ToyotaCYD BLE logger was found")
        self.name = device.name or "ToyotaCYD"
        self.address = str(device.address)
        self.client = BleakClient(device)
        await self.client.connect()
        await self.client.start_notify(RESPONSE_UUID, self._notification)

    async def close(self) -> None:
        if self.client:
            try:
                await self.client.stop_notify(RESPONSE_UUID)
            except Exception:
                pass
            await self.client.disconnect()
            self.client = None

    def _next(self) -> int:
        result = self.sequence & 0xFFFF
        self.sequence = (self.sequence + 1) & 0xFFFF
        if result == 0:
            return self._next()
        return result

    def _notification(self, _characteristic: Any, data: bytearray) -> None:
        receive_ns = time.perf_counter_ns()
        if self.loop:
            self.loop.call_soon_threadsafe(self._handle_notification, bytes(data), receive_ns)

    def _handle_notification(self, data: bytes, receive_ns: int) -> None:
        if len(data) < 4 or data[1] != 1:
            return
        packet_type, _, sequence = struct.unpack_from("<BBH", data)
        pending = self.pending.pop(sequence, None)
        if pending is None:
            return
        kind, send_ns, future = pending
        if packet_type == 0x81 and kind == "sync" and len(data) >= 20:
            e2_us, e3_us = struct.unpack_from("<QQ", data, 4)
            future.set_result({"sequence": sequence, "t1_client_ns": send_ns,
                               "e2_esp_us": e2_us, "e3_esp_us": e3_us,
                               "t4_client_ns": receive_ns,
                               "round_trip_ns": receive_ns - send_ns - (e3_us - e2_us) * 1000})
        elif packet_type == 0x82 and kind.startswith("control:") and len(data) >= 20:
            status, logging = struct.unpack_from("<BB", data, 4)
            session = struct.unpack_from("<I", data, 6)[0]
            event_us = struct.unpack_from("<Q", data, 10)[0]
            diagnostic, normal = struct.unpack_from("<BB", data, 18)
            future.set_result({"operation": kind.split(":", 1)[1], "sequence": sequence,
                               "client_send_ns": send_ns, "client_ack_ns": receive_ns,
                               "status": status, "cyd_session": session,
                               "esp_event_us": event_us, "logging_after": bool(logging),
                               "diagnostics_after": bool(diagnostic), "twai_normal_after": bool(normal)})
        elif not future.done():
            future.set_exception(RuntimeError("Unexpected BLE response"))

    async def sync(self) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("BLE is not connected")
        sequence = self._next()
        future = asyncio.get_running_loop().create_future()
        send_ns = time.perf_counter_ns()
        self.pending[sequence] = ("sync", send_ns, future)
        await self.client.write_gatt_char(COMMAND_UUID, struct.pack("<BBH", 1, 1, sequence), response=False)
        try:
            return await asyncio.wait_for(future, timeout=2.0)
        except Exception:
            self.pending.pop(sequence, None)
            raise

    async def control(self, operation: str, opcode: int, marker: int = 0) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("BLE is not connected")
        sequence = self._next()
        future = asyncio.get_running_loop().create_future()
        send_ns = time.perf_counter_ns()
        self.pending[sequence] = (f"control:{operation}", send_ns, future)
        payload = struct.pack("<BBHBBH", 2, 1, sequence, opcode, 0, marker)
        await self.client.write_gatt_char(COMMAND_UUID, payload, response=False)
        try:
            return await asyncio.wait_for(future, timeout=5.0)
        except Exception:
            self.pending.pop(sequence, None)
            raise


class DesktopRecorder:
    def __init__(self, output: Path, microphone: str | None) -> None:
        self.output = output
        self.microphone = microphone
        self.process: subprocess.Popen[str] | None = None
        self.progress_thread: threading.Thread | None = None
        self.video_clock_samples: list[dict[str, int]] = []
        self.start_before_ns = 0
        self.start_after_ns = 0

    def start(self) -> None:
        ffmpeg = resolve_tool("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg was not found on PATH")
        command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-stats_period", "0.1", "-y",
                   "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1", "-i", "desktop"]
        if self.microphone:
            command += ["-f", "dshow", "-i", f"audio={self.microphone}"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
        if self.microphone:
            command += ["-c:a", "aac", "-b:a", "128k"]
        command += ["-progress", "pipe:1", "-nostats", str(self.output)]
        log = self.output.with_suffix(".ffmpeg.log").open("w", encoding="utf-8")
        self.start_before_ns = time.perf_counter_ns()
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, text=True, bufsize=1,
                                        **hidden_process_kwargs())
        self.start_after_ns = time.perf_counter_ns()
        self.progress_thread = threading.Thread(target=self._read_progress, daemon=True)
        self.progress_thread.start()

    def _read_progress(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            if line.startswith("out_time_us="):
                try:
                    video_us = int(line.split("=", 1)[1].strip())
                    self.video_clock_samples.append({"client_read_ns": time.perf_counter_ns(),
                                                     "video_out_time_us": video_us})
                except ValueError:
                    pass

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.stdin:
            try:
                self.process.stdin.write("q\n")
                self.process.stdin.flush()
            except Exception:
                pass
        try:
            self.process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.progress_thread:
            self.progress_thread.join(timeout=2)

    def timing(self) -> dict[str, Any]:
        values = [item["client_read_ns"] - item["video_out_time_us"] * 1000
                  for item in self.video_clock_samples if item["video_out_time_us"] >= 0]
        if values:
            values.sort()
            best = values[:max(1, len(values) // 5)]
            anchor = int(statistics.median(best))
            uncertainty = max(33_333_334, int(max(best) - min(best)) if len(best) > 1 else 100_000_000)
            method = "ffmpeg_progress_low_delay_fit"
        else:
            anchor = self.start_before_ns + (self.start_after_ns - self.start_before_ns) // 2
            uncertainty = max(500_000_000, self.start_after_ns - self.start_before_ns)
            method = "ffmpeg_process_launch_fallback"
        return {"video_start_call_before_ns": self.start_before_ns,
                "video_start_call_after_ns": self.start_after_ns,
                "video_anchor_ns": anchor, "video_anchor_uncertainty_ns": uncertainty,
                "video_anchor_method": method, "video_clock_samples": self.video_clock_samples}


class CaptureDocument:
    def __init__(self, directory: Path, microphone: str | None) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        self.path = directory / "CAPTURE_SYNC.json"
        self.video = directory / "SCREEN.mp4"
        self.data: dict[str, Any] = {
            "format": "ToyotaCANSync-WindowsCapture", "format_version": "1.0",
            "app_version": "1.0.3", "client_platform": "Windows",
            "windows_version": platform.platform(), "clock": "time.perf_counter_ns",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "video_file": self.video.name, "microphone": microphone,
            "sync_samples": [], "control_events": [], "markers": [],
            "closed_cleanly": False,
        }
        self.write()

    def write(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def add_sync(self, sample: dict[str, Any]) -> None:
        self.data["sync_samples"].append(sample)
        self.write()

    def add_control(self, event: dict[str, Any]) -> None:
        self.data["control_events"].append(event)
        self.write()


async def _burst(ble: CydBleClient, document: CaptureDocument, count: int,
                 progress: Callable[[str], None]) -> None:
    for _ in range(count):
        try:
            document.add_sync(await ble.sync())
        except Exception as error:
            progress(f"Sync sample failed: {error}")
        await asyncio.sleep(0.1)


async def run_windows_capture(output_parent: Path, microphone: str | None,
                              progress: Callable[[str], None] = print) -> Path:
    directory = output_parent / f"CAPTURE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    document = CaptureDocument(directory, microphone)
    ble = CydBleClient()
    recorder = DesktopRecorder(document.video, microphone)
    periodic_stop = asyncio.Event()
    marker = 1

    async def periodic() -> None:
        while not periodic_stop.is_set():
            try:
                await asyncio.wait_for(periodic_stop.wait(), timeout=30.0)
                break
            except asyncio.TimeoutError:
                await _burst(ble, document, 5, progress)

    try:
        progress("Scanning for ToyotaCYD...")
        await ble.connect()
        document.data["ble_device_name"] = ble.name
        document.data["ble_device_address"] = ble.address
        document.write()
        progress(f"Connected to {ble.name}; collecting pre-capture clock samples")
        await _burst(ble, document, 15, progress)
        recorder.start()
        document.add_control(await ble.control("START_PASSIVE", 1))
        await _burst(ble, document, 15, progress)
        periodic_task = asyncio.create_task(periodic())
        progress("Desktop and microphone capture active. Type m + Enter for a marker; press Enter to stop.")
        while True:
            choice = (await asyncio.to_thread(input, "capture> ")).strip().lower()
            if choice == "m":
                document.data["markers"].append({"marker": marker, "client_ns": time.perf_counter_ns()})
                document.add_control(await ble.control("MARKER", 3, marker))
                progress(f"Marker {marker} added")
                marker += 1
            elif choice == "":
                break
        periodic_stop.set()
        await _burst(ble, document, 15, progress)
        document.add_control(await ble.control("STOP", 2))
        await periodic_task
        recorder.stop()
        document.data.update(recorder.timing())
        document.data["closed_cleanly"] = True
        document.data["recording_stopped_utc"] = datetime.now(timezone.utc).isoformat()
        document.write()
        progress(f"Capture closed: {directory}")
        return directory
    finally:
        periodic_stop.set()
        if recorder.process and recorder.process.poll() is None:
            recorder.stop()
            document.data.update(recorder.timing())
            document.write()
        await ble.close()


def list_audio_devices() -> str:
    ffmpeg = resolve_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found on PATH")
    result = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            **hidden_process_kwargs())
    return result.stderr
