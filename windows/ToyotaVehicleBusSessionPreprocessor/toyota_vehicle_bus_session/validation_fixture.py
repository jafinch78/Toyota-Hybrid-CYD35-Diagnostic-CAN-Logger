from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import csv
import hashlib
import json
import shutil
import struct
import tempfile
import zipfile

from .meta import MetaHeader, MetaRecord, write_meta
from .tcb1 import scan_tcb_stream

EVENT_CODES = {
    "LOGGING_STARTED": 1,
    "LOGGING_STOP_REQUESTED": 2,
    "LOGGING_STOPPED": 3,
    "CAN_TRAFFIC_STARTED": 4,
    "RAW_ROTATION_FAILED": 5,
    "EXTERNAL_TESTER_DETECTED": 6,
    "TWAI_START_FAILED": 7,
    "TWAI_TRANSMIT_BLOCKED": 8,
    "TWAI_TRANSMIT_FAILED": 9,
    "TWAI_MODE_CHANGE_FAILED": 10,
    "BLE_CAPTURE_START": 11,
    "BLE_CAPTURE_STOP": 12,
    "BLE_MARKER": 13,
    "DIAGNOSTIC_ENABLE_REJECTED": 14,
    "DIAGNOSTIC_IDENTITY_UNRESOLVED": 15,
    "DIAGNOSTIC_RUNTIME_DECODE_MISSING": 16,
    "DATABASE_PROFILE_EVIDENCE": 17,
    "PROFILE_CHANGE": 18,
    "DIAGNOSTIC_IDENTITY_FALLBACK": 19,
}
SEVERITIES = {"INFO": 0, "WARNING": 1, "ERROR": 2, "FATAL": 3}
SOURCES = {"BLE": 0, "BLE_PRESTART": 1}


@dataclass(frozen=True)
class NativeFixtureResult:
    session_id: str
    native_session_dir: Path
    report_path: Path


def _lp(value: object) -> bytes:
    raw = str(value or "").encode("utf-8")
    if len(raw) > 255:
        raise ValueError("validation fixture string exceeds TVM1 v1 maximum")
    return struct.pack("<H", len(raw)) + raw


def _find_legacy_root(path: Path) -> Path:
    path = Path(path)
    if not path.is_dir():
        raise ValueError("legacy input must be a folder or ZIP")
    direct = path / "MANIFEST.JSON"
    if direct.is_file():
        return path
    manifests = sorted(path.rglob("MANIFEST.JSON"))
    candidates = [manifest.parent for manifest in manifests if manifest.is_file()]
    if len(candidates) != 1:
        raise ValueError("legacy input must resolve to exactly one session")
    return candidates[0]


def _extract_legacy_zip(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temporary = tempfile.TemporaryDirectory(prefix="toyota_legacy_fixture_")
    root = Path(temporary.name)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for name in archive.namelist():
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError("ZIP path traversal rejected")
            archive.extractall(root)
        return _find_legacy_root(root), temporary
    except Exception:
        temporary.cleanup()
        raise


def _resolve_legacy_source(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None, str]:
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        root, temporary = _extract_legacy_zip(path)
        return root, temporary, "ZIP"
    return _find_legacy_root(path), None, "DIRECTORY"


def synthesize_native_fixture(legacy_canlog: Path, output_dir: Path) -> NativeFixtureResult:
    legacy_input = Path(legacy_canlog)
    source, temporary, source_kind = _resolve_legacy_source(legacy_input)
    try:
        manifest = json.loads((source / "MANIFEST.JSON").read_text(encoding="utf-8"))
        checkpoint_path = source / "CHECKPOINT.JSON"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {}

        session_id = str(manifest.get("session_id") or source.name)
        if not (session_id.startswith("S") and session_id[1:].isdigit()):
            raise ValueError("invalid legacy session id")
        session_number = int(session_id[1:])

        output = Path(output_dir) / session_id
        output.mkdir(parents=True, exist_ok=False)
        raw_paths = tuple(sorted(source.glob("RAW_*.TCB")))
        if not raw_paths:
            raise ValueError("legacy session contains no RAW_*.TCB files")
        raw_report = scan_tcb_stream(raw_paths)

        raw_hashes: dict[str, str] = {}
        for raw_path in raw_paths:
            destination = output / raw_path.name
            shutil.copyfile(raw_path, destination)
            source_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            destination_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            if destination_hash != source_hash:
                raise IOError("RAW identity verification failed")
            raw_hashes[raw_path.name] = source_hash

        records: list[MetaRecord] = []
        sequence = 0

        def add(record_type: int, stream_id: int, time_us: int | None, payload: bytes = b"") -> None:
            nonlocal sequence
            sequence += 1
            records.append(MetaRecord(record_type, stream_id, 0, sequence, int(time_us or 0), payload))

        create_us = raw_report.first_time_us or 0
        add(
            0x0001,
            0,
            create_us,
            _lp(manifest.get("firmware"))
            + _lp(manifest.get("firmware_version"))
            + _lp(manifest.get("board_profile"))
            + _lp(manifest.get("build_id"))
            + _lp(manifest.get("runtime_database")),
        )
        add(
            0x0002,
            1,
            create_us,
            struct.pack(
                "<BBBBBBHI",
                1,
                1,
                1,
                0,
                3,
                0,
                0,
                int(manifest.get("can_bitrate", 500000) or 500000),
            ),
        )
        add(0x0003, 1, create_us)

        for index, chunk in enumerate(raw_report.chunks):
            add(0x0005, 1, chunk.first_time_us or create_us, struct.pack("<H", index) + _lp(chunk.path.name))
            add(
                0x0006,
                1,
                chunk.last_time_us or create_us,
                struct.pack("<HHQQ", index, 0, chunk.records, chunk.path.stat().st_size),
            )

        sync_path = source / "SYNC.CSV"
        if sync_path.is_file():
            with sync_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    add(
                        0x0010,
                        0,
                        int(row.get("ESP_Receive_us") or 0),
                        struct.pack(
                            "<HBBQ",
                            int(row.get("Sequence") or 0),
                            SOURCES.get(row.get("Source", ""), 255),
                            0,
                            int(row.get("ESP_Send_us") or 0),
                        ),
                    )

        warnings: list[dict[str, object]] = []
        events_path = source / "EVENTS.CSV"
        if events_path.is_file():
            with events_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    event_name = row.get("Event", "")
                    details = row.get("Details", "")
                    event_code = EVENT_CODES.get(event_name, 65535)
                    severity = SEVERITIES.get(row.get("Severity", "INFO").upper(), 0)
                    time_us = int(row.get("Time_us") or 0)
                    add(0x0030, 0, time_us, struct.pack("<HBB", event_code, severity, 0))
                    if details or event_code == 65535:
                        warnings.append({
                            "code": "VALIDATION_FIXTURE_LOSSY_EVENT_DETAIL",
                            "time_us": time_us,
                            "event": event_name,
                        })

        rx_records = int(checkpoint.get("session_received_frames", checkpoint.get("received_frames", raw_report.rx_count)) or 0)
        tx_records = int(checkpoint.get("session_transmitted_frames", checkpoint.get("transmitted_frames", raw_report.tx_count)) or 0)
        queue_drops = int(checkpoint.get("can_queue_drops", 0) or 0)
        storage_dropped = int(
            checkpoint.get("sd_log_dropped_frames", checkpoint.get("storage_dropped_records", 0)) or 0
        )
        add(
            0x0021,
            1,
            raw_report.last_time_us or create_us,
            struct.pack(
                "<QQQQQII",
                rx_records,
                tx_records,
                raw_report.record_count,
                queue_drops,
                storage_dropped,
                0,
                0,
            ),
        )
        add(0x0004, 1, raw_report.last_time_us or create_us, struct.pack("<H", 1))

        manifest_clean = bool(manifest.get("closed_cleanly", False))
        checkpoint_clean = bool(checkpoint.get("closed_cleanly", manifest_clean))
        closed_cleanly = manifest_clean and checkpoint_clean and not (source / "SESSION.OPEN").exists()
        if closed_cleanly:
            add(0x00FE, 0, raw_report.last_time_us or create_us, struct.pack("<HBBHH", 0, 1, 0, 1, 0))

        write_meta(
            output / "SESSION.META",
            MetaHeader(1, 0, session_number, 0, create_us),
            records,
        )

        report = {
            "session_id": session_id,
            "validation_only": True,
            "source_kind": source_kind,
            "source_archive": str(legacy_input.resolve()) if source_kind == "ZIP" else None,
            "closed_cleanly": closed_cleanly,
            "raw_identity": raw_hashes,
            "raw_logical_sha256": raw_report.logical_record_sha256,
            "warnings": warnings,
        }
        report_path = output / "SYNTHESIS_REPORT.json"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return NativeFixtureResult(session_id, output, report_path)
    finally:
        if temporary is not None:
            temporary.cleanup()
