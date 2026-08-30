from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .database import canonical_profile, find_definition


READ_ONLY_SERVICES = {0x01, 0x09, 0x21, 0x22}


@dataclass
class Request:
    time_us: int
    can_id: int
    payload: bytes
    service: int
    pid: int | None
    matched: bool = False
    flow_control_seen: bool = False


@dataclass
class Assembly:
    response_id: int
    start_us: int
    end_us: int
    total_length: int
    payload: bytearray
    frame_count: int = 1
    next_sequence: int = 1
    missing_sequences: int = 0


@dataclass
class Transaction:
    request: Request | None
    response_id: int | None
    response_start_us: int | None
    response_end_us: int | None
    response_payload: bytes = b""
    frame_count: int = 0
    missing_sequences: int = 0
    status: str = "NO_RESPONSE"


def _parse_single_frame(data: bytes) -> bytes | None:
    if not data or data[0] >> 4 != 0:
        return None
    length = data[0] & 0x0F
    if length == 0 or length > len(data) - 1:
        return None
    return data[1:1 + length]


def _expected_response_ids(request_id: int) -> set[int]:
    if request_id == 0x7DF:
        return set(range(0x7E8, 0x7F0))
    if 0x700 <= request_id <= 0x7E7:
        return {request_id + 8}
    return set()


def _response_matches(request: Request, response_id: int, payload: bytes) -> bool:
    if response_id not in _expected_response_ids(request.can_id) or not payload:
        return False
    if payload[0] == 0x7F:
        return len(payload) >= 2 and payload[1] == request.service
    if payload[0] != ((request.service + 0x40) & 0xFF):
        return False
    if request.pid is None:
        return True
    return len(payload) >= 2 and payload[1] == request.pid


def _status(request: Request | None, payload: bytes, missing: int) -> str:
    if request is None:
        return "UNMATCHED_RESPONSE"
    if missing:
        return "INCOMPLETE_SEQUENCE"
    if not payload:
        return "NO_RESPONSE"
    if payload[0] == 0x7F:
        return f"NEGATIVE_RESPONSE_{payload[2]:02X}" if len(payload) >= 3 else "NEGATIVE_RESPONSE"
    return "OK" if _response_matches(request, request.can_id + 8 if request.can_id != 0x7DF else 0x7E8, payload) else "UNEXPECTED_RESPONSE"


def reconstruct_external_diagnostics(source: Path) -> list[Transaction]:
    rows: list[tuple[int, int, bytes, str]] = []
    if not source.exists():
        return []
    with source.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        for row in csv.DictReader(stream):
            try:
                rows.append((int(row["Time_us"]), int(row["CAN_ID"], 16),
                             bytes.fromhex(row["DataHex"]), row.get("Classification", "")))
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=lambda item: item[0])
    requests: list[Request] = []
    active: dict[int, Assembly] = {}
    completed: list[Transaction] = []

    def finish(response_id: int, assembly: Assembly) -> None:
        payload = bytes(assembly.payload[:assembly.total_length])
        request = next((candidate for candidate in reversed(requests)
                        if not candidate.matched and _response_matches(candidate, response_id, payload)), None)
        if request:
            request.matched = True
        status = "UNMATCHED_RESPONSE" if request is None else (
            "INCOMPLETE_SEQUENCE" if assembly.missing_sequences else
            (f"NEGATIVE_RESPONSE_{payload[2]:02X}" if payload[:1] == b"\x7f" and len(payload) >= 3 else
             "NEGATIVE_RESPONSE" if payload[:1] == b"\x7f" else "OK"))
        completed.append(Transaction(request, response_id, assembly.start_us, assembly.end_us,
                                     payload, assembly.frame_count,
                                     assembly.missing_sequences, status))

    for time_us, can_id, data, classification in rows:
        pci = data[0] >> 4 if data else -1
        if "REQUEST" in classification:
            payload = _parse_single_frame(data)
            if payload:
                service = payload[0]
                pid = payload[1] if len(payload) >= 2 else None
                requests.append(Request(time_us, can_id, payload, service, pid))
            elif pci == 3:
                response_id = can_id + 8 if can_id != 0x7DF else None
                if response_id in active:
                    for candidate in reversed(requests):
                        if not candidate.matched and response_id in _expected_response_ids(candidate.can_id):
                            candidate.flow_control_seen = True
                            break
            continue
        if "RESPONSE" not in classification or not data:
            continue
        if pci == 0:
            payload = _parse_single_frame(data)
            if payload is None:
                continue
            assembly = Assembly(can_id, time_us, time_us, len(payload), bytearray(payload))
            finish(can_id, assembly)
        elif pci == 1 and len(data) >= 2:
            if can_id in active:
                prior = active.pop(can_id)
                prior.missing_sequences += 1
                finish(can_id, prior)
            total = ((data[0] & 0x0F) << 8) | data[1]
            active[can_id] = Assembly(can_id, time_us, time_us, total, bytearray(data[2:]))
            if len(active[can_id].payload) >= total:
                finish(can_id, active.pop(can_id))
        elif pci == 2 and can_id in active:
            assembly = active[can_id]
            sequence = data[0] & 0x0F
            if sequence != assembly.next_sequence:
                distance = (sequence - assembly.next_sequence) & 0x0F
                assembly.missing_sequences += distance or 1
            assembly.next_sequence = (sequence + 1) & 0x0F
            assembly.payload.extend(data[1:])
            assembly.end_us = time_us
            assembly.frame_count += 1
            if len(assembly.payload) >= assembly.total_length:
                finish(can_id, active.pop(can_id))

    for response_id, assembly in sorted(active.items()):
        assembly.missing_sequences += 1
        finish(response_id, assembly)
    for request in requests:
        if not request.matched:
            completed.append(Transaction(request, None, None, None, b"", 0, 0, "NO_RESPONSE"))
    completed.sort(key=lambda transaction: transaction.request.time_us if transaction.request else
                   (transaction.response_start_us or 0))
    return completed


def _video_time(time_us: int | None, alignment: Any | None) -> str:
    if time_us is None or alignment is None:
        return ""
    value = alignment.video_seconds(float(time_us))
    return "" if value is None else f"{value:.6f}"


def _safety(service: int | None) -> str:
    return "READ_ONLY_DIAGNOSTIC" if service in READ_ONLY_SERVICES else "CONTROL_WRITE_QUARANTINED"


NORMALIZED_FIELDS = [
    "Scope", "RequestTime_us", "ResponseStart_us", "ResponseEnd_us", "Video_s",
    "RequestCAN_ID", "ResponseCAN_ID", "Service", "PID", "RequestPayloadHex",
    "ResponsePayloadHex", "ResponseLength", "ResponseFrames", "Latency_ms",
    "Status", "MissingSequenceCount", "FlowControlObserved", "SafetyClass",
    "EvidenceGrade", "DecoderKey", "DecodedSummary",
]


BATTERY_FIELDS = [
    "RequestTime_us", "ResponseTime_us", "Video_s", "Profile", "ServicePID",
    "PreambleHex", *[f"B{index:02d}_V" for index in range(1, 18)],
    "PackSum_V", "Average_V", "Minimum_V", "Maximum_V", "Difference_V",
    "Status", "EvidenceGrade", "DecoderKey", "RawResponseHex",
]


def decode_block_array(payload: bytes, definition: dict[str, Any]) -> dict[str, Any] | None:
    prefix = bytes.fromhex(str(definition.get("response_prefix", "")))
    if not payload.startswith(prefix):
        return None
    preamble_bytes = int(definition.get("preamble_bytes", 0))
    repeat = definition.get("repeat", {})
    count = int(repeat.get("count", 0))
    width = int(repeat.get("width_bytes", 0))
    start = len(prefix) + preamble_bytes
    if count <= 0 or width <= 0 or len(payload) < start + count * width:
        return None
    offset = float(repeat.get("offset", 0.0))
    scale = float(repeat.get("scale", 1.0))
    endian = str(repeat.get("endian", "big"))
    values = []
    for index in range(count):
        raw = int.from_bytes(payload[start + index * width:start + (index + 1) * width], endian)
        values.append((raw + offset) * scale)
    return {
        "preamble": payload[len(prefix):start],
        "values": values,
        "sum": sum(values),
        "average": sum(values) / len(values),
        "minimum": min(values),
        "maximum": max(values),
        "difference": max(values) - min(values),
    }


def write_external_diagnostics(source: Path, normalized_target: Path, battery_target: Path,
                               profile: str, database: dict[str, Any], alignment: Any | None) -> dict[str, Any]:
    transactions = reconstruct_external_diagnostics(source)
    profile_key = canonical_profile(profile)
    counts: dict[str, int] = {}
    battery_rows = 0
    with normalized_target.open("w", newline="", encoding="utf-8") as normalized_stream, \
            battery_target.open("w", newline="", encoding="utf-8") as battery_stream:
        normalized = csv.DictWriter(normalized_stream, fieldnames=NORMALIZED_FIELDS)
        battery = csv.DictWriter(battery_stream, fieldnames=BATTERY_FIELDS)
        normalized.writeheader()
        battery.writeheader()
        for transaction in transactions:
            request = transaction.request
            service = request.service if request else None
            pid = request.pid if request else None
            definition = find_definition(database, profile_key, request.can_id, service, pid) \
                if request and pid is not None else None
            decoded = None
            decoded_summary = ""
            if definition and definition.get("decoder") == "block_array":
                decoded = decode_block_array(transaction.response_payload, definition)
                if decoded:
                    decoded_summary = (f"blocks={len(decoded['values'])};avg={decoded['average']:.4f}V;"
                                       f"diff={decoded['difference']:.4f}V;sum={decoded['sum']:.2f}V")
            latency = ""
            if request and transaction.response_start_us is not None:
                latency = f"{(transaction.response_start_us - request.time_us) / 1000.0:.3f}"
            counts[transaction.status] = counts.get(transaction.status, 0) + 1
            normalized.writerow({
                "Scope": "EXTERNAL_PASSIVE_OBSERVATION",
                "RequestTime_us": request.time_us if request else "",
                "ResponseStart_us": transaction.response_start_us or "",
                "ResponseEnd_us": transaction.response_end_us or "",
                "Video_s": _video_time(request.time_us if request else transaction.response_start_us, alignment),
                "RequestCAN_ID": f"{request.can_id:03X}" if request else "",
                "ResponseCAN_ID": f"{transaction.response_id:03X}" if transaction.response_id is not None else "",
                "Service": f"{service:02X}" if service is not None else "",
                "PID": f"{pid:02X}" if pid is not None else "",
                "RequestPayloadHex": request.payload.hex().upper() if request else "",
                "ResponsePayloadHex": transaction.response_payload.hex().upper(),
                "ResponseLength": len(transaction.response_payload),
                "ResponseFrames": transaction.frame_count,
                "Latency_ms": latency,
                "Status": transaction.status,
                "MissingSequenceCount": transaction.missing_sequences,
                "FlowControlObserved": bool(request and request.flow_control_seen),
                "SafetyClass": _safety(service),
                "EvidenceGrade": definition.get("evidence_grade", "OBSERVED_ONLY") if definition else "OBSERVED_ONLY",
                "DecoderKey": definition.get("key", "") if definition else "",
                "DecodedSummary": decoded_summary,
            })
            if decoded and len(decoded["values"]) == 17 and request:
                battery_rows += 1
                row = {
                    "RequestTime_us": request.time_us,
                    "ResponseTime_us": transaction.response_start_us or "",
                    "Video_s": _video_time(request.time_us, alignment),
                    "Profile": profile_key,
                    "ServicePID": f"{service:02X}{pid:02X}",
                    "PreambleHex": decoded["preamble"].hex().upper(),
                    "PackSum_V": f"{decoded['sum']:.2f}",
                    "Average_V": f"{decoded['average']:.6f}",
                    "Minimum_V": f"{decoded['minimum']:.3f}",
                    "Maximum_V": f"{decoded['maximum']:.3f}",
                    "Difference_V": f"{decoded['difference']:.3f}",
                    "Status": transaction.status,
                    "EvidenceGrade": definition.get("evidence_grade", "CANDIDATE"),
                    "DecoderKey": definition.get("key", ""),
                    "RawResponseHex": transaction.response_payload.hex().upper(),
                }
                for index, value in enumerate(decoded["values"], 1):
                    row[f"B{index:02d}_V"] = f"{value:.3f}"
                battery.writerow(row)
    return {"transactions": len(transactions), "status_counts": counts,
            "battery_block_rows": battery_rows, "profile": profile_key}
