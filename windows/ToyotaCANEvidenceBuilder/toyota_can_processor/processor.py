from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .database import canonical_profile, load_database
from .diagnostics import write_external_diagnostics
from .media import run_ocr, run_transcription
from .sync import Alignment, fit_alignment, validate_sd_sync
from .tcb1 import process_tcb_files
from .versioning import check_manifest


Progress = Callable[[str], None]


@dataclass
class ProcessingOptions:
    write_raw_csv: bool = False
    run_ocr: bool = False
    run_transcription: bool = False
    ocr_profile: str = "AUTO"
    ocr_interval_seconds: float = 2.0
    whisper_model: str = "small.en"


def _safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
        source.extractall(destination)
    return destination


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def _find_capture_json(root: Path) -> Path | None:
    candidates = sorted(root.rglob("CAPTURE_SYNC.json"))
    return candidates[0] if candidates else None


def _control_session(capture: dict[str, Any] | None) -> int | None:
    if not capture:
        return None
    for event in capture.get("control_events", []):
        if event.get("operation") == "START_PASSIVE" and int(event.get("status", 1)) == 0:
            return int(event.get("cyd_session", 0)) or None
    return None


def _session_number(session: Path) -> int | None:
    name = session.name.upper()
    if name.startswith("S") and name[1:].isdigit():
        return int(name[1:])
    return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        return list(csv.DictReader(stream))


def _aligned_csv(source: Path, target: Path, time_field: str, scale_to_us: float,
                 alignment: Alignment | None) -> int:
    if not source.exists():
        return 0
    with source.open("r", newline="", encoding="utf-8-sig", errors="replace") as input_stream, \
            target.open("w", newline="", encoding="utf-8") as output_stream:
        reader = csv.DictReader(input_stream)
        fields = list(reader.fieldnames or []) + ["Video_s"]
        writer = csv.DictWriter(output_stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        count = 0
        for row in reader:
            count += 1
            try:
                esp_us = float(row[time_field]) * scale_to_us
                value = alignment.video_seconds(esp_us) if alignment else None
                row["Video_s"] = "" if value is None else f"{value:.6f}"
            except (KeyError, TypeError, ValueError):
                row["Video_s"] = ""
            writer.writerow(row)
        return count


def _normalized_diagnostics(source: Path, target: Path, firmware: str | None,
                            alignment: Alignment | None) -> dict[str, int]:
    rows = _read_csv(source)
    counts: dict[str, int] = {}
    fields = list(rows[0].keys()) if rows else []
    fields += [name for name in ("OriginalStatus", "NormalizedStatus", "Video_s") if name not in fields]
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            original = row.get("Status", "")
            normalized = original
            if original == "UNEXPECTED_RESPONSE" and firmware and firmware.startswith("2.3."):
                normalized = "LEGACY_POSSIBLE_EXTERNAL_DIAGNOSTIC_TRAFFIC"
            row["OriginalStatus"] = original
            row["NormalizedStatus"] = normalized
            counts[normalized] = counts.get(normalized, 0) + 1
            try:
                mapped = alignment.video_seconds(float(row["RequestTime_us"])) if alignment else None
                row["Video_s"] = "" if mapped is None else f"{mapped:.6f}"
            except (KeyError, TypeError, ValueError):
                row["Video_s"] = ""
            writer.writerow(row)
    return counts


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    manifest = summary.get("manifest", {})
    compatibility = summary.get("compatibility", {})
    alignment = summary.get("alignment") or {}
    warnings = summary.get("warnings", [])
    database = summary.get("decoder_database", {})
    external = summary.get("external_diagnostics", {})
    rows = "".join(f"<li>{html.escape(str(item))}</li>" for item in warnings) or "<li>None</li>"
    body = f"""<!doctype html><html><head><meta charset='utf-8'><title>Toyota CAN report</title>
<style>body{{font-family:Segoe UI,Arial;max-width:1100px;margin:2em auto;color:#17202a}}
table{{border-collapse:collapse}}td,th{{border:1px solid #aaa;padding:.4em}}code{{background:#eee;padding:.1em}}</style></head><body>
<h1>Toyota Hybrid CAN Session {html.escape(str(summary.get('session', '')))}</h1>
<table><tr><th>Firmware</th><td>{html.escape(str(manifest.get('firmware_version')))}</td></tr>
<tr><th>Capture format</th><td>{html.escape(str(manifest.get('format_version')))}</td></tr>
<tr><th>Vehicle profile</th><td>{html.escape(str(manifest.get('vehicle_profile')))}</td></tr>
<tr><th>Profile confidence</th><td>{html.escape(str(manifest.get('profile_confidence_pct')))}%</td></tr>
<tr><th>Compatibility</th><td>{'SUPPORTED' if compatibility.get('supported') else 'BLOCKED'}</td></tr>
<tr><th>Raw records</th><td>{summary.get('raw', {}).get('raw_record_count', 0)}</td></tr>
<tr><th>Decoder database</th><td>{html.escape(str(database.get('name', '')))} {html.escape(str(database.get('version', '')))}</td></tr>
<tr><th>External diagnostic transactions</th><td>{external.get('transactions', 0)}</td></tr>
<tr><th>Decoded battery-block samples</th><td>{external.get('battery_block_rows', 0)}</td></tr>
<tr><th>BLE alignment samples</th><td>{alignment.get('sample_count_used', 0)}</td></tr>
<tr><th>BLE fit residual RMS</th><td>{alignment.get('residual_rms_ms')} ms</td></tr>
<tr><th>Clock drift</th><td>{alignment.get('drift_ppm')} ppm</td></tr></table>
<h2>Warnings</h2><ul>{rows}</ul>
<h2>Time mapping</h2><code>{html.escape(str(alignment.get('formula') or 'No BLE/video alignment available'))}</code>
<p>Every alignment is calculated from this capture's BLE exchanges. No offset from another session is reused.</p>
<p>External diagnostic traffic is passively observed. This report does not authorize the logger to transmit any request or control command.</p>
</body></html>"""
    path.write_text(body, encoding="utf-8")


def process(logger_source: Path, output_parent: Path, companion_source: Path | None = None,
            video_override: Path | None = None, options: ProcessingOptions | None = None,
            progress: Progress | None = None) -> dict[str, Any]:
    options = options or ProcessingOptions()
    progress = progress or (lambda message: None)
    logger_source = logger_source.resolve()
    output_parent = output_parent.resolve()
    output_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = output_parent / f"ToyotaCAN_Evidence_{stamp}"
    output_root.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="toyota_can_process_") as temporary:
        temp = Path(temporary)
        logger_root = _safe_extract(logger_source, temp / "logger") if logger_source.is_file() and zipfile.is_zipfile(logger_source) else logger_source
        companion_root = None
        if companion_source:
            companion_source = companion_source.resolve()
            if companion_source.is_file() and zipfile.is_zipfile(companion_source):
                companion_root = _safe_extract(companion_source, temp / "companion")
            elif companion_source.is_dir():
                companion_root = companion_source
            else:
                companion_root = companion_source.parent

        database, database_info = load_database()
        capture_path = _find_capture_json(companion_root) if companion_root else None
        capture_sync = _load_json(capture_path) if capture_path else None
        selected_session = _control_session(capture_sync)
        manifests = sorted(logger_root.rglob("MANIFEST.JSON"))
        if not manifests:
            raise ValueError("No MANIFEST.JSON was found in the logger source")
        progress(f"Found {len(manifests)} logger session(s)")

        overall: dict[str, Any] = {
            "processor_version": "1.0.1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "logger_source": str(logger_source),
            "logger_source_sha256": _sha256(logger_source),
            "companion_source": str(companion_source) if companion_source else None,
            "companion_source_sha256": _sha256(companion_source) if companion_source else None,
            "ble_selected_session": selected_session,
            "decoder_database": asdict(database_info),
            "sessions": [],
        }

        media_can_battery: Path | None = None
        media_vehicle_profile = "UNKNOWN"
        media_expected_blocks: int | None = None

        for manifest_path in manifests:
            session_path = manifest_path.parent
            session_name = session_path.name
            progress(f"Processing {session_name}")
            target = output_root / session_name
            target.mkdir()
            try:
                manifest = _load_json(manifest_path)
                manifest_error = None
            except Exception as error:
                manifest = {}
                manifest_error = f"Malformed MANIFEST.JSON: {error}"
            compatibility = check_manifest(manifest)
            if manifest_error:
                compatibility.supported = False
                compatibility.errors.insert(0, manifest_error)
            (target / "COMPATIBILITY_REPORT.json").write_text(
                json.dumps(compatibility.to_dict(), indent=2), encoding="utf-8")
            warnings = list(compatibility.warnings) + list(compatibility.errors)
            session_number = _session_number(session_path)
            use_alignment = capture_sync is not None and (
                (selected_session is None and len(manifests) == 1) or selected_session == session_number)
            alignment = fit_alignment(capture_sync) if use_alignment else None
            if alignment:
                (target / "TIME_ALIGNMENT.json").write_text(
                    json.dumps(alignment.to_dict(), indent=2), encoding="utf-8")
                warnings.extend(alignment.warnings)

            sd_sync = _read_csv(session_path / "SYNC.CSV")
            sync_validation = validate_sd_sync(capture_sync, sd_sync) if use_alignment else None
            if sync_validation and not sync_validation["confirmed"]:
                warnings.append("Android/CYD SYNC.CSV corroboration is incomplete")

            raw_summary: dict[str, Any] = {}
            if compatibility.supported:
                tcb_files = sorted(session_path.glob("RAW_*.TCB"))
                if not tcb_files:
                    warnings.append("No RAW_nnn.TCB files were found")
                else:
                    raw_summary = process_tcb_files(
                        tcb_files,
                        target / "CAN_RAW.csv" if options.write_raw_csv else None,
                        target / "CAN_ID_INVENTORY.csv")
                    if raw_summary["truncated_tail_bytes_total"]:
                        warnings.append("A truncated TCB tail was recovered by keeping complete records only")

            _aligned_csv(session_path / "EVENTS.CSV", target / "EVENTS_ALIGNED.csv",
                         "Time_us", 1.0, alignment)
            _aligned_csv(session_path / "DECODED.CSV", target / "DECODED_ALIGNED.csv",
                         "Time_ms", 1000.0, alignment)
            diagnostic_counts = _normalized_diagnostics(
                session_path / "DIAGNOSTICS.CSV", target / "LOGGER_DIAGNOSTICS_NORMALIZED.csv",
                compatibility.firmware_normalized, alignment)
            external_summary: dict[str, Any] = {"transactions": 0, "status_counts": {},
                                                "battery_block_rows": 0}
            if (session_path / "EXTERNAL_DIAGNOSTICS.CSV").exists():
                shutil.copy2(session_path / "EXTERNAL_DIAGNOSTICS.CSV", target / "EXTERNAL_DIAGNOSTICS.csv")
                external_summary = write_external_diagnostics(
                    session_path / "EXTERNAL_DIAGNOSTICS.CSV",
                    target / "EXTERNAL_DIAGNOSTICS_NORMALIZED.csv",
                    target / "BATTERY_BLOCKS_ALIGNED.csv",
                    str(manifest.get("vehicle_profile", "UNKNOWN")), database, alignment)
            if external_summary.get("transactions", 0):
                shutil.copy2(target / "EXTERNAL_DIAGNOSTICS_NORMALIZED.csv",
                             target / "DIAGNOSTICS_NORMALIZED.csv")
            else:
                shutil.copy2(target / "LOGGER_DIAGNOSTICS_NORMALIZED.csv",
                             target / "DIAGNOSTICS_NORMALIZED.csv")

            if use_alignment and external_summary.get("battery_block_rows", 0):
                media_can_battery = target / "BATTERY_BLOCKS_ALIGNED.csv"
                media_vehicle_profile = canonical_profile(str(manifest.get("vehicle_profile", "UNKNOWN")))
                profile_info = database.get("profiles", {}).get(media_vehicle_profile, {})
                value = profile_info.get("block_count")
                media_expected_blocks = int(value) if value is not None else None

            summary = {
                "session": session_name,
                "source_path": str(session_path),
                "manifest": manifest,
                "compatibility": compatibility.to_dict(),
                "raw": raw_summary,
                "alignment": alignment.to_dict() if alignment else None,
                "sync_corroboration": sync_validation,
                "diagnostic_status_counts": diagnostic_counts,
                "external_diagnostics": external_summary,
                "decoder_database": asdict(database_info),
                "warnings": warnings,
            }
            (target / "SESSION_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            _write_report(target / "REPORT.html", summary)
            overall["sessions"].append(summary)

        video = video_override.resolve() if video_override else None
        if video is None and companion_root and capture_sync:
            video_name = capture_sync.get("video_file")
            matches = list(companion_root.rglob(video_name)) if video_name else []
            video = matches[0] if matches else None
        media_results: dict[str, Any] = {}
        if video and options.run_ocr:
            try:
                media_results["ocr"] = run_ocr(video, output_root / "OCR_TEXT.csv",
                                                options.ocr_interval_seconds,
                                                options.ocr_profile, progress,
                                                output_root / "BATTERY_GRAPH_ALIGNED.csv",
                                                media_can_battery, media_vehicle_profile,
                                                media_expected_blocks)
            except Exception as error:
                media_results["ocr_error"] = str(error)
        if video and options.run_transcription:
            try:
                media_results["transcription"] = run_transcription(
                    video, output_root / "VOICE_TRANSCRIPT.csv", options.whisper_model, progress)
            except Exception as error:
                media_results["transcription_error"] = str(error)
        overall["media"] = media_results
        (output_root / "PROCESSING_SUMMARY.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
        progress(f"Complete: {output_root}")
        return {"output": str(output_root), "summary": overall}
