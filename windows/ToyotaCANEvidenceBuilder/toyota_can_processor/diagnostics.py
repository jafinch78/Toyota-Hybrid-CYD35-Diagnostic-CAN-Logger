from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .database import canonical_profile, find_definition
from .decoding import decode_definition, decoded_summary as generic_decoded_summary


READ_ONLY_SERVICES = {0x01, 0x09, 0x13, 0x21, 0x22}
POSITIVE_RESPONSE_WITHOUT_PID_ECHO = {0x13}


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
    if request.pid is None or request.service in POSITIVE_RESPONSE_WITHOUT_PID_ECHO:
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
    "Profile", "OriginalProfile", "ProfileSelection", "EvidenceGrade",
    "DecoderKey", "DecoderType", "DecodedSummary", "DecodeWarnings",
]


BATTERY_FIELDS = [
    "RequestTime_us", "ResponseTime_us", "Video_s", "Profile", "ServicePID",
    "PreambleHex", *[f"B{index:02d}_V" for index in range(1, 18)],
    "PackSum_V", "Average_V", "Minimum_V", "Maximum_V", "Difference_V",
    "Status", "EvidenceGrade", "DecoderKey", "RawResponseHex",
]


ACTION_FIELDS = [
    "StartVideo_s", "EndVideo_s", "StartRequestTime_us", "EndRequestTime_us",
    "Profile", "ECU", "Operation", "RequestCAN_ID", "ResponseCAN_ID",
    "RequestPayloads", "ResponsePayloads", "AttemptCount", "SuccessfulResponses",
    "Result", "SafetyClass", "EvidenceGrade", "DecoderKeys", "CorrelationBasis",
]


DECODED_FIELD_COLUMNS = [
    "RequestTime_us", "ResponseTime_us", "Video_s", "Profile", "OriginalProfile",
    "ProfileSelection", "RequestCAN_ID", "ResponseCAN_ID", "Service", "PID",
    "DecoderKey", "DecoderType", "Field", "ArrayIndex", "Value", "Unit",
    "RawHex", "Formula", "BoundsStatus", "ExpectedStatus", "EvidenceGrade",
    "SemanticStatus", "OCRLabels", "OCRTolerance", "SafetyClass", "Status",
    "SourceSession", "RawResponseHex",
]


RESISTANCE_COLUMNS = [
    "RequestTime_us", "ResponseTime_us", "Video_s", "Profile", "ServicePID",
    "ResistanceCount", *[f"R{index:02d}_Ohm" for index in range(1, 18)],
    "Average_Ohm", "Minimum_Ohm", "Maximum_Ohm", "Status", "EvidenceGrade",
    "DecoderKey", "RawResponseHex",
]


IDENTITY_COLUMNS = [
    "RequestTime_us", "ResponseTime_us", "Video_s", "Profile", "ServicePID",
    "IdentityType", "Value", "MaskedByDefault", "EvidenceGrade", "DecoderKey",
]


def _diagnostic_operation(request: Request | None) -> str | None:
    if request is None:
        return None
    if request.service == 0x13:
        return "READ_DTC_BY_STATUS"
    if request.service == 0x04:
        return "CLEAR_DTC"
    return None


def _ecu_name(request_id: int) -> str:
    return {0x7E0: "ENGINE_ECU", 0x7E2: "HYBRID_VEHICLE_ECU",
            0x7E3: "BATTERY_ECU"}.get(request_id, f"ECU_{request_id:03X}")


def _action_result(operation: str, transactions: list[Transaction]) -> str:
    payloads = [transaction.response_payload for transaction in transactions
                if transaction.status == "OK"]
    if operation == "READ_DTC_BY_STATUS":
        if payloads and all(payload.startswith(b"\x53\x00") for payload in payloads):
            return "NO_DTC_PRESENT"
        return "DTC_RESPONSE_PRESENT_REVIEW" if payloads else "NO_CONFIRMED_RESPONSE"
    if operation == "CLEAR_DTC":
        return "ACKNOWLEDGED" if payloads and all(payload.startswith(b"\x44") for payload in payloads) \
            else "NO_CONFIRMED_ACKNOWLEDGEMENT"
    return "REVIEW"


def write_diagnostic_actions(path: Path, transactions: list[Transaction], profile: str,
                             database: dict[str, Any], alignment: Any | None) -> int:
    """Write grouped read/clear-code actions observed on the bus.

    Groups repeated requests from one app operation when the gap is no more than
    eight seconds.  Clear operations remain explicitly quarantined.
    """
    candidates = [transaction for transaction in transactions
                  if _diagnostic_operation(transaction.request) is not None]
    candidates.sort(key=lambda item: item.request.time_us if item.request else 0)
    groups: list[list[Transaction]] = []
    for transaction in candidates:
        request = transaction.request
        assert request is not None
        operation = _diagnostic_operation(request)
        if groups:
            prior = groups[-1][-1].request
            assert prior is not None
            if (_diagnostic_operation(prior) == operation and prior.can_id == request.can_id
                    and request.time_us - prior.time_us <= 8_000_000):
                groups[-1].append(transaction)
                continue
        groups.append([transaction])

    profile_key = canonical_profile(profile)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ACTION_FIELDS)
        writer.writeheader()
        for group in groups:
            first = group[0].request
            last = group[-1].request
            assert first is not None and last is not None
            operation = _diagnostic_operation(first) or "UNKNOWN"
            definitions = [find_definition(database, profile_key, item.request.can_id,
                                           item.request.service, item.request.pid)
                           for item in group if item.request]
            definitions = [definition for definition in definitions if definition]
            responses = [item.response_payload.hex().upper() for item in group
                         if item.response_payload]
            response_ids = sorted({f"{item.response_id:03X}" for item in group
                                   if item.response_id is not None})
            writer.writerow({
                "StartVideo_s": _video_time(first.time_us, alignment),
                "EndVideo_s": _video_time(last.time_us, alignment),
                "StartRequestTime_us": first.time_us,
                "EndRequestTime_us": last.time_us,
                "Profile": profile_key,
                "ECU": _ecu_name(first.can_id),
                "Operation": operation,
                "RequestCAN_ID": f"{first.can_id:03X}",
                "ResponseCAN_ID": ";".join(response_ids),
                "RequestPayloads": ";".join(sorted({item.request.payload.hex().upper()
                                                     for item in group if item.request})),
                "ResponsePayloads": ";".join(sorted(set(responses))),
                "AttemptCount": len(group),
                "SuccessfulResponses": sum(1 for item in group if item.status == "OK"),
                "Result": _action_result(operation, group),
                "SafetyClass": "READ_ONLY_DIAGNOSTIC" if operation.startswith("READ_")
                               else "CONTROL_WRITE_QUARANTINED",
                "EvidenceGrade": "PROBABLE" if definitions else "OBSERVED_ONLY",
                "DecoderKeys": ";".join(sorted({str(item.get("key", ""))
                                                 for item in definitions if item.get("key")})),
                "CorrelationBasis": "BLE_ALIGNED_PASSIVE_CAN_OBSERVATION",
            })
    return len(groups)


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


def _write_decoded_item(writer: csv.DictWriter, *, item: dict[str, Any],
                        transaction: Transaction, definition: dict[str, Any],
                        profile_key: str, original_profile: str, profile_selection: str,
                        service: int, pid: int | None, alignment: Any | None,
                        source_session: str, array_index: int | str = "") -> None:
    request = transaction.request
    assert request is not None
    writer.writerow({
        "RequestTime_us": request.time_us,
        "ResponseTime_us": transaction.response_start_us or "",
        "Video_s": _video_time(request.time_us, alignment),
        "Profile": profile_key,
        "OriginalProfile": original_profile,
        "ProfileSelection": profile_selection,
        "RequestCAN_ID": f"{request.can_id:03X}",
        "ResponseCAN_ID": f"{transaction.response_id:03X}" if transaction.response_id is not None else "",
        "Service": f"{service:02X}",
        "PID": f"{pid:02X}" if pid is not None else "",
        "DecoderKey": definition.get("key", ""),
        "DecoderType": definition.get("decoder", ""),
        "Field": item.get("name", ""),
        "ArrayIndex": array_index,
        "Value": item.get("value", ""),
        "Unit": item.get("unit", ""),
        "RawHex": item.get("raw_hex", ""),
        "Formula": item.get("formula", ""),
        "BoundsStatus": item.get("bounds_status", ""),
        "ExpectedStatus": item.get("expected_status", ""),
        "EvidenceGrade": item.get("evidence_grade", definition.get("evidence_grade", "CANDIDATE")),
        "SemanticStatus": item.get("semantic_status", ""),
        "OCRLabels": ";".join(item.get("ocr_labels", [])),
        "OCRTolerance": item.get("ocr_tolerance", "") if item.get("ocr_tolerance") is not None else "",
        "SafetyClass": definition.get("safety_class", "READ_ONLY_DIAGNOSTIC"),
        "Status": transaction.status,
        "SourceSession": source_session,
        "RawResponseHex": transaction.response_payload.hex().upper(),
    })


def write_external_diagnostics(source: Path, normalized_target: Path, battery_target: Path,
                               action_target: Path, profile: str, database: dict[str, Any],
                               alignment: Any | None, decoded_target: Path | None = None,
                               resistance_target: Path | None = None,
                               identity_target: Path | None = None,
                               original_profile: str | None = None,
                               profile_selection: str = "MANIFEST_RETAINED",
                               source_session: str = "",
                               transactions: list[Transaction] | None = None) -> dict[str, Any]:
    transactions = transactions if transactions is not None else reconstruct_external_diagnostics(source)
    profile_key = canonical_profile(profile)
    original_profile_key = canonical_profile(original_profile or profile)
    counts: dict[str, int] = {}
    battery_rows = 0
    decoded_field_rows = 0
    resistance_rows = 0
    identity_rows = 0
    decode_warning_count = 0
    decoded_target = decoded_target or normalized_target.with_name("DECODED_FIELDS_ALIGNED.csv")
    resistance_target = resistance_target or normalized_target.with_name("RESISTANCE_ARRAYS_ALIGNED.csv")
    identity_target = identity_target or normalized_target.with_name("IDENTITY_ALIGNED.csv")
    with normalized_target.open("w", newline="", encoding="utf-8") as normalized_stream, \
            battery_target.open("w", newline="", encoding="utf-8") as battery_stream, \
            decoded_target.open("w", newline="", encoding="utf-8") as decoded_stream, \
            resistance_target.open("w", newline="", encoding="utf-8") as resistance_stream, \
            identity_target.open("w", newline="", encoding="utf-8") as identity_stream:
        normalized = csv.DictWriter(normalized_stream, fieldnames=NORMALIZED_FIELDS)
        battery = csv.DictWriter(battery_stream, fieldnames=BATTERY_FIELDS)
        decoded_writer = csv.DictWriter(decoded_stream, fieldnames=DECODED_FIELD_COLUMNS)
        resistance_writer = csv.DictWriter(resistance_stream, fieldnames=RESISTANCE_COLUMNS)
        identity_writer = csv.DictWriter(identity_stream, fieldnames=IDENTITY_COLUMNS)
        normalized.writeheader()
        battery.writeheader()
        decoded_writer.writeheader()
        resistance_writer.writeheader()
        identity_writer.writeheader()
        for transaction in transactions:
            request = transaction.request
            service = request.service if request else None
            pid = request.pid if request else None
            definition = find_definition(database, profile_key, request.can_id, service, pid) \
                if request and service is not None else None
            decoded: dict[str, Any] | None = None
            summary_text = ""
            if definition and transaction.status == "OK":
                decoded = decode_definition(transaction.response_payload, definition)
                if decoded and decoded.get("matched"):
                    summary_text = generic_decoded_summary(decoded)
                    decode_warning_count += len(decoded.get("warnings", []))
                else:
                    decoded = None
            if not summary_text and service == 0x13 and transaction.response_payload.startswith(b"\x53\x00"):
                summary_text = "dtc_count=0"
            elif not summary_text and service == 0x04 and transaction.response_payload.startswith(b"\x44"):
                summary_text = "clear_acknowledged"
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
                "Profile": profile_key,
                "OriginalProfile": original_profile_key,
                "ProfileSelection": profile_selection,
                "EvidenceGrade": definition.get("evidence_grade", "OBSERVED_ONLY") if definition else "OBSERVED_ONLY",
                "DecoderKey": definition.get("key", "") if definition else "",
                "DecoderType": definition.get("decoder", "") if definition else "",
                "DecodedSummary": summary_text,
                "DecodeWarnings": ";".join(decoded.get("warnings", [])) if decoded else "",
            })

            if decoded and request and definition:
                for item in decoded.get("fields", []):
                    _write_decoded_item(
                        decoded_writer, item=item, transaction=transaction, definition=definition,
                        profile_key=profile_key, original_profile=original_profile_key,
                        profile_selection=profile_selection, service=service or 0, pid=pid,
                        alignment=alignment, source_session=source_session)
                    decoded_field_rows += 1
                for item in decoded.get("arrays", []):
                    _write_decoded_item(
                        decoded_writer, item=item, transaction=transaction, definition=definition,
                        profile_key=profile_key, original_profile=original_profile_key,
                        profile_selection=profile_selection, service=service or 0, pid=pid,
                        alignment=alignment, source_session=source_session,
                        array_index=int(item.get("index", 0)) or "")
                    decoded_field_rows += 1

                identity = decoded.get("identity", {})
                for name, value in identity.items():
                    if name == "vin":
                        continue
                    identity_rows += 1
                    identity_writer.writerow({
                        "RequestTime_us": request.time_us,
                        "ResponseTime_us": transaction.response_start_us or "",
                        "Video_s": _video_time(request.time_us, alignment),
                        "Profile": profile_key,
                        "ServicePID": f"{service:02X}{pid:02X}" if pid is not None else f"{service:02X}",
                        "IdentityType": name,
                        "Value": value,
                        "MaskedByDefault": name == "vin_masked",
                        "EvidenceGrade": definition.get("evidence_grade", "CANDIDATE"),
                        "DecoderKey": definition.get("key", ""),
                    })

            arrays = decoded.get("arrays", []) if decoded else []
            decoder_type = str(definition.get("decoder", "")) if definition else ""
            if arrays and decoder_type == "block_array" and request:
                battery_rows += 1
                values = [float(item["value"]) for item in arrays]
                data = transaction.response_payload[len(bytes.fromhex(str(definition.get("response_prefix", "")))):]
                preamble_length = int(definition.get("preamble_bytes", 0))
                row = {
                    "RequestTime_us": request.time_us,
                    "ResponseTime_us": transaction.response_start_us or "",
                    "Video_s": _video_time(request.time_us, alignment),
                    "Profile": profile_key,
                    "ServicePID": f"{service:02X}{pid:02X}",
                    "PreambleHex": data[:preamble_length].hex().upper(),
                    "PackSum_V": f"{sum(values):.2f}",
                    "Average_V": f"{sum(values) / len(values):.6f}",
                    "Minimum_V": f"{min(values):.3f}",
                    "Maximum_V": f"{max(values):.3f}",
                    "Difference_V": f"{max(values) - min(values):.3f}",
                    "Status": transaction.status,
                    "EvidenceGrade": definition.get("evidence_grade", "CANDIDATE"),
                    "DecoderKey": definition.get("key", ""),
                    "RawResponseHex": transaction.response_payload.hex().upper(),
                }
                for index, value in enumerate(values, 1):
                    row[f"B{index:02d}_V"] = f"{value:.3f}"
                battery.writerow(row)

            if arrays and decoder_type in {"resistance_array", "block_health_array"} and request:
                values = [float(item["value"]) for item in arrays]
                if "resistance" in str(arrays[0].get("name", "")).lower():
                    resistance_rows += 1
                    row = {
                        "RequestTime_us": request.time_us,
                        "ResponseTime_us": transaction.response_start_us or "",
                        "Video_s": _video_time(request.time_us, alignment),
                        "Profile": profile_key,
                        "ServicePID": f"{service:02X}{pid:02X}",
                        "ResistanceCount": len(values),
                        "Average_Ohm": f"{sum(values) / len(values):.6f}",
                        "Minimum_Ohm": f"{min(values):.6f}",
                        "Maximum_Ohm": f"{max(values):.6f}",
                        "Status": transaction.status,
                        "EvidenceGrade": definition.get("evidence_grade", "CANDIDATE"),
                        "DecoderKey": definition.get("key", ""),
                        "RawResponseHex": transaction.response_payload.hex().upper(),
                    }
                    for index, value in enumerate(values, 1):
                        row[f"R{index:02d}_Ohm"] = f"{value:.6f}"
                    resistance_writer.writerow(row)
    action_rows = write_diagnostic_actions(action_target, transactions, profile_key,
                                           database, alignment)
    return {"transactions": len(transactions), "status_counts": counts,
            "battery_block_rows": battery_rows, "decoded_field_rows": decoded_field_rows,
            "resistance_rows": resistance_rows, "identity_rows": identity_rows,
            "decode_warning_count": decode_warning_count,
            "diagnostic_action_rows": action_rows, "profile": profile_key,
            "original_profile": original_profile_key, "profile_selection": profile_selection}
