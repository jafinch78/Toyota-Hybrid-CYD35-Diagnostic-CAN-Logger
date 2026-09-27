from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .meta import decode_record_payload
from .schemas import EVENTS_HEADER, EVENT_NAMES, SEVERITY_NAMES, SOURCE_NAMES, SYNC_HEADER

PREPROCESSOR_NAME = "ToyotaVehicleBusSessionPreprocessor"
PREPROCESSOR_VERSION = "0.1.0"


def _session_start(session):
    for record in session.meta.records:
        if record.record_type == 0x0001:
            return decode_record_payload(record)
    return {}


def _last_record(session, record_type: int, stream_id: int | None = None):
    for record in reversed(session.meta.records):
        if record.record_type == record_type and (stream_id is None or record.stream_id == stream_id):
            return decode_record_payload(record)
    return {}


def _meta_sha256(session) -> str:
    return hashlib.sha256((session.source_root / "SESSION.META").read_bytes()).hexdigest()


def build_legacy_manifest(session) -> dict[str, object]:
    start = _session_start(session)
    counters = _last_record(session, 0x0021, 1)
    can = session.can_stream
    return {
        "format": "ToyotaHybridCAN-Capture",
        "format_version": "1.4",
        "firmware": start.get("logger_name"),
        "firmware_version": start.get("firmware_version"),
        "board_profile": start.get("board_profile"),
        "raw_format": "TCB1_24_byte_records" if can else None,
        "runtime_database": start.get("runtime_database"),
        "build_id": start.get("build_id"),
        "session_id": session.session_id,
        "raw_file_count": len(session.can_paths),
        "first_can_time_us": can.first_time_us if can else None,
        "last_can_time_us": can.last_time_us if can else None,
        "actual_raw_records": can.record_count if can else 0,
        "rx_records": counters.get("rx_records"),
        "tx_records": counters.get("tx_records"),
        "persisted_records": counters.get("persisted_records"),
        "queue_drops": counters.get("queue_drops"),
        "storage_dropped_records": counters.get("storage_dropped_records"),
        "closed_cleanly": session.meta.clean_close,
        "native_capture_format": "TVM1",
        "native_capture_version": "1.0",
        "native_meta_sha256": _meta_sha256(session),
        "native_can_logical_sha256": can.logical_record_sha256 if can else None,
        "preprocessor_name": PREPROCESSOR_NAME,
        "preprocessor_version": PREPROCESSOR_VERSION,
    }


def build_legacy_checkpoint(session) -> dict[str, object]:
    counters = _last_record(session, 0x0021, 1)
    health = _last_record(session, 0x0020)
    storage = _last_record(session, 0x0022)
    can = session.can_stream
    return {
        "session_id": session.session_id,
        "closed_cleanly": session.meta.clean_close,
        "actual_raw_records": can.record_count if can else 0,
        "actual_rx_records": can.rx_count if can else 0,
        "actual_tx_records": can.tx_count if can else 0,
        **counters,
        "health": health,
        "storage_health": storage,
        "meta_recovery": {
            "truncated_tail_bytes": session.meta.recovery.truncated_tail_bytes,
            "crc_error_offsets": list(session.meta.recovery.crc_error_offsets),
            "resynchronized_records": session.meta.recovery.resynchronized_records,
            "sequence_gaps": [list(gap) for gap in session.meta.recovery.sequence_gaps],
        },
    }


def write_legacy_sync(session, path: Path) -> int:
    rows = []
    for record in session.meta.records:
        if record.record_type == 0x0010:
            decoded = decode_record_payload(record)
            rows.append([
                decoded["sequence"], record.time_us, decoded["esp_send_us"],
                SOURCE_NAMES.get(decoded["source"], str(decoded["source"])),
            ])
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(SYNC_HEADER)
        writer.writerows(rows)
    return len(rows)


def write_legacy_events(session, path: Path) -> int:
    rows = []
    for record in session.meta.records:
        if record.record_type == 0x0030:
            decoded = decode_record_payload(record)
            details = ";".join(f"{arg_id}:{value}" for arg_id, _flags, value in decoded["args"])
            rows.append([
                record.time_us,
                SEVERITY_NAMES.get(decoded["severity"], str(decoded["severity"])),
                EVENT_NAMES.get(decoded["event_code"], f"EVENT_{decoded['event_code']}"),
                details,
            ])
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(EVENTS_HEADER)
        writer.writerows(rows)
    return len(rows)
