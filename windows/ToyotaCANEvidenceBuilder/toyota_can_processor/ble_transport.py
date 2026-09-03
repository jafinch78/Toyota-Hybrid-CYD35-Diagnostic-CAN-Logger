from __future__ import annotations

import asyncio
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable


SERVICE_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40001"
COMMAND_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40002"
RESPONSE_UUID = "6ed9f000-4f21-4c8c-a8a7-923c86b40003"


class BleakTransport:
    """Modern-Windows transport used by the established capture path."""

    def __init__(self, notification: Callable[[Any, bytearray], None]) -> None:
        self.notification = notification
        self.client = None
        self.name = ""
        self.address = ""

    async def connect(self, timeout: float = 15.0) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as error:
            raise RuntimeError("Windows BLE capture requires: py -m pip install bleak") from error

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
        await self.client.start_notify(RESPONSE_UUID, self.notification)

    async def write(self, payload: bytes) -> None:
        if not self.client:
            raise RuntimeError("BLE is not connected")
        await self.client.write_gatt_char(COMMAND_UUID, payload, response=False)

    async def close(self) -> None:
        if not self.client:
            return
        try:
            await self.client.stop_notify(RESPONSE_UUID)
        except Exception:
            pass
        await self.client.disconnect()
        self.client = None


class Win1607BridgeTransport:
    """Transport adapter for the external Win1607_BLE_Bridge.exe helper.

    The helper owns only legacy WinRT GATT operations. Packet semantics and
    synchronization fitting remain in Python. RX callbacks are dispatched as
    soon as bridge notification lines are read.
    """

    def __init__(self, notification: Callable[[Any, bytearray], None], executable: Path) -> None:
        self.notification = notification
        self.executable = executable
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.events: asyncio.Queue[str] | None = None
        self.name = "ToyotaCYD"
        self.address = "paired"

    async def connect(self, timeout: float = 15.0) -> None:
        if not self.executable.exists():
            raise RuntimeError(f"Windows 1607 BLE bridge not found: {self.executable}")
        self.loop = asyncio.get_running_loop()
        self.events = asyncio.Queue()
        self.process = subprocess.Popen(
            [str(self.executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()

        ready = await asyncio.wait_for(self.events.get(), timeout=min(timeout, 5.0))
        if not ready.startswith("READY "):
            await self.close()
            raise RuntimeError(f"Windows 1607 BLE bridge did not become ready: {ready}")

        self._send("CONNECT AUTO")
        line = await asyncio.wait_for(self.events.get(), timeout=timeout)
        if not line.startswith("OK CONNECTED"):
            await self.close()
            raise RuntimeError(f"Windows 1607 BLE bridge connect failed: {line}")

        details = line[len("OK CONNECTED"):].strip()
        if details:
            fields = details.split("\t", 1)
            if fields[0]:
                self.name = fields[0]
            if len(fields) == 2 and fields[1]:
                self.address = fields[1]

    def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for raw in self.process.stdout:
            line = raw.strip()
            if line.startswith("RX "):
                try:
                    payload = bytearray.fromhex(line[3:].strip())
                except ValueError:
                    continue
                self.notification(None, payload)
            elif self.loop and self.events:
                self.loop.call_soon_threadsafe(self.events.put_nowait, line)

    def _send(self, line: str) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("Windows 1607 BLE bridge is not running")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    async def write(self, payload: bytes) -> None:
        if not self.events:
            raise RuntimeError("Windows 1607 BLE bridge is not connected")
        if len(payload) not in (4, 8):
            raise RuntimeError("ToyotaCYD-Sync/1 command must be 4 or 8 bytes")
        self._send("WRITE " + payload.hex())
        line = await asyncio.wait_for(self.events.get(), timeout=5.0)
        if not line.startswith("OK WRITE"):
            raise RuntimeError(f"Windows 1607 BLE bridge write failed: {line}")

    async def close(self) -> None:
        process = self.process
        if not process:
            return
        try:
            if process.poll() is None:
                self._send("DISCONNECT")
                self._send("QUIT")
        except Exception:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        self.process = None


def make_transport(notification: Callable[[Any, bytearray], None]):
    """Select Win1607 bridge only when explicitly requested.

    Explicit selection prevents an unvalidated native bridge from silently
    changing the established Bleak path on modern Windows.
    """
    backend = os.environ.get("TOYOTA_BLE_BACKEND", "bleak").strip().lower()
    if backend == "win1607":
        configured = os.environ.get("TOYOTA_WIN1607_BLE_BRIDGE")
        executable = Path(configured) if configured else (
            Path(__file__).resolve().parents[1] / "win1607_ble_bridge" / "Win1607_BLE_Bridge.exe"
        )
        return Win1607BridgeTransport(notification, executable)
    if backend != "bleak":
        raise RuntimeError(f"Unknown TOYOTA_BLE_BACKEND: {backend}")
    return BleakTransport(notification)
