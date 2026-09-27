from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterable
import zlib

MAGIC = b"TVM1"
SYNC_WORD = 0xA55A
HEADER_SIZE = 32
MIN_RECORD_SIZE = 24
MAX_RECORD_SIZE = 4096
KNOWN_RECORD_TYPES = {
    0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006,
    0x0010, 0x0011, 0x0020, 0x0021, 0x0022,
    0x0030, 0x0031, 0x0032, 0x00FE,
}


@dataclass(frozen=True)
class MetaHeader:
    major: int
    minor: int
    session_number: int
    header_flags: int
    session_create_us: int


@dataclass(frozen=True)
class MetaRecord:
    record_type: int
    stream_id: int
    flags: int
    sequence: int
    time_us: int
    payload: bytes


@dataclass(frozen=True)
class MetaRecovery:
    truncated_tail_bytes: int
    crc_error_offsets: tuple[int, ...]
    resynchronized_records: int
    sequence_gaps: tuple[tuple[int, int], ...]
    unknown_record_types: tuple[int, ...]


@dataclass(frozen=True)
class MetaReadResult:
    header: MetaHeader
    records: tuple[MetaRecord, ...]
    recovery: MetaRecovery
    clean_close: bool


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _encode_header(header: MetaHeader) -> bytes:
    prefix = struct.pack(
        "<4sBBHIIQ",
        MAGIC,
        header.major,
        header.minor,
        HEADER_SIZE,
        header.session_number,
        header.header_flags,
        header.session_create_us,
    )
    return prefix + struct.pack("<II", _crc32(prefix), 0)


def encode_record(record: MetaRecord) -> bytes:
    payload = bytes(record.payload)
    total_length = MIN_RECORD_SIZE + len(payload)
    if not MIN_RECORD_SIZE <= total_length <= MAX_RECORD_SIZE:
        raise ValueError("record length outside TVM1 v1 bounds")
    prefix = struct.pack(
        "<HHHBBIQ",
        SYNC_WORD,
        total_length,
        record.record_type,
        record.stream_id,
        record.flags,
        record.sequence,
        record.time_us,
    ) + payload
    return prefix + struct.pack("<I", _crc32(prefix))


def write_meta(path: Path, header: MetaHeader, records: Iterable[MetaRecord]) -> None:
    with Path(path).open("wb") as f:
        f.write(_encode_header(header))
        for record in records:
            f.write(encode_record(record))


def _parse_header(raw: bytes) -> MetaHeader:
    if len(raw) < HEADER_SIZE:
        raise ValueError("truncated TVM1 header")
    magic, major, minor, header_size, session_number, header_flags, session_create_us = struct.unpack_from(
        "<4sBBHIIQ", raw, 0
    )
    if magic != MAGIC:
        raise ValueError("bad TVM1 magic")
    if major != 1:
        raise ValueError("unsupported TVM1 major version")
    if header_size < HEADER_SIZE:
        raise ValueError("invalid TVM1 header size")
    stored_crc = struct.unpack_from("<I", raw, 24)[0]
    if stored_crc != _crc32(raw[:24]):
        raise ValueError("invalid TVM1 header CRC")
    return MetaHeader(major, minor, session_number, header_flags, session_create_us)


def _find_next_valid_record(raw: bytes, start: int) -> int | None:
    marker = struct.pack("<H", SYNC_WORD)
    pos = raw.find(marker, start)
    while pos >= 0:
        if len(raw) - pos >= MIN_RECORD_SIZE:
            total_length = struct.unpack_from("<H", raw, pos + 2)[0]
            if MIN_RECORD_SIZE <= total_length <= MAX_RECORD_SIZE and pos + total_length <= len(raw):
                candidate = raw[pos : pos + total_length]
                stored_crc = struct.unpack_from("<I", candidate, total_length - 4)[0]
                if stored_crc == _crc32(candidate[:-4]):
                    return pos
        pos = raw.find(marker, pos + 1)
    return None


def read_meta(path: Path) -> MetaReadResult:
    raw = Path(path).read_bytes()
    header = _parse_header(raw)
    records: list[MetaRecord] = []
    crc_errors: list[int] = []
    gaps: list[tuple[int, int]] = []
    unknown: list[int] = []
    resync_count = 0
    truncated = 0
    offset = HEADER_SIZE
    previous_sequence: int | None = None

    while offset < len(raw):
        remaining = len(raw) - offset
        if remaining < MIN_RECORD_SIZE:
            truncated = remaining
            break
        sync, total_length = struct.unpack_from("<HH", raw, offset)
        if sync != SYNC_WORD or total_length < MIN_RECORD_SIZE or total_length > MAX_RECORD_SIZE:
            next_offset = _find_next_valid_record(raw, offset + 1)
            if next_offset is None:
                truncated = remaining
                break
            crc_errors.append(offset)
            resync_count += 1
            offset = next_offset
            continue
        if offset + total_length > len(raw):
            truncated = remaining
            break
        chunk = raw[offset : offset + total_length]
        stored_crc = struct.unpack_from("<I", chunk, total_length - 4)[0]
        if stored_crc != _crc32(chunk[:-4]):
            crc_errors.append(offset)
            next_offset = _find_next_valid_record(raw, offset + 1)
            if next_offset is None:
                truncated = remaining
                break
            resync_count += 1
            offset = next_offset
            continue
        record_type, stream_id, flags, sequence, time_us = struct.unpack_from("<HBBIQ", chunk, 4)
        payload = bytes(chunk[20:-4])
        record = MetaRecord(record_type, stream_id, flags, sequence, time_us, payload)
        if previous_sequence is not None and sequence != previous_sequence + 1:
            gaps.append((previous_sequence, sequence))
        previous_sequence = sequence
        if record_type not in KNOWN_RECORD_TYPES:
            unknown.append(record_type)
        records.append(record)
        offset += total_length

    clean_close = False
    if records and records[-1].record_type == 0x00FE:
        try:
            clean_close = decode_record_payload(records[-1]).get("clean") == 1
        except (ValueError, struct.error):
            clean_close = False

    return MetaReadResult(
        header=header,
        records=tuple(records),
        recovery=MetaRecovery(
            truncated_tail_bytes=truncated,
            crc_error_offsets=tuple(crc_errors),
            resynchronized_records=resync_count,
            sequence_gaps=tuple(gaps),
            unknown_record_types=tuple(unknown),
        ),
        clean_close=clean_close,
    )


def _read_string(payload: bytes, offset: int) -> tuple[str, int]:
    if offset + 2 > len(payload):
        raise ValueError("truncated TVM1 string length")
    length = struct.unpack_from("<H", payload, offset)[0]
    offset += 2
    if length > 255:
        raise ValueError("TVM1 string exceeds v1 maximum")
    end = offset + length
    if end > len(payload):
        raise ValueError("truncated TVM1 string")
    try:
        value = payload[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid TVM1 UTF-8 string") from exc
    return value, end


def _require_exact(payload: bytes, size: int) -> None:
    if len(payload) != size:
        raise ValueError(f"invalid TVM1 payload length: expected {size}, got {len(payload)}")


def _decode_metrics(payload: bytes) -> dict[str, object]:
    if len(payload) < 4:
        raise ValueError("truncated metric vector")
    schema_version, count = struct.unpack_from("<HH", payload, 0)
    expected = 4 + count * 12
    if len(payload) != expected:
        raise ValueError("invalid metric vector length")
    metrics = []
    offset = 4
    for _ in range(count):
        metric_id, metric_flags, value = struct.unpack_from("<HHQ", payload, offset)
        metrics.append((metric_id, metric_flags, value))
        offset += 12
    return {"schema_version": schema_version, "metrics": tuple(metrics)}


def decode_record_payload(record: MetaRecord) -> dict[str, object]:
    p = record.payload
    t = record.record_type
    if t == 0x0001:
        names = ("logger_name", "firmware_version", "board_profile", "build_id", "runtime_database")
        result: dict[str, object] = {}
        offset = 0
        for name in names:
            result[name], offset = _read_string(p, offset)
        if offset != len(p):
            raise ValueError("trailing bytes in SESSION_START")
        return result
    if t == 0x0002:
        if len(p) < 12:
            raise ValueError("truncated STREAM_REGISTER")
        stream_type, raw_format_id, raw_major, raw_minor, direction_caps, config_version, config_length, nominal_rate = struct.unpack_from(
            "<BBBBBBHI", p, 0
        )
        if len(p) != 12 + config_length:
            raise ValueError("invalid STREAM_REGISTER config length")
        return {
            "stream_type": stream_type,
            "raw_format_id": raw_format_id,
            "raw_format_major": raw_major,
            "raw_format_minor": raw_minor,
            "direction_caps": direction_caps,
            "config_version": config_version,
            "nominal_rate": nominal_rate,
            "config": bytes(p[12:]),
        }
    if t == 0x0003:
        _require_exact(p, 0)
        return {"stream_start": True}
    if t == 0x0004:
        _require_exact(p, 2)
        return {"reason_code": struct.unpack("<H", p)[0]}
    if t == 0x0005:
        if len(p) < 4:
            raise ValueError("truncated STREAM_FILE_OPEN")
        file_index = struct.unpack_from("<H", p, 0)[0]
        filename, offset = _read_string(p, 2)
        if offset != len(p):
            raise ValueError("trailing bytes in STREAM_FILE_OPEN")
        return {"file_index": file_index, "filename": filename}
    if t == 0x0006:
        _require_exact(p, 20)
        file_index, reason_code, records_persisted, bytes_persisted = struct.unpack("<HHQQ", p)
        return {
            "file_index": file_index,
            "reason_code": reason_code,
            "records_persisted": records_persisted,
            "bytes_persisted": bytes_persisted,
        }
    if t == 0x0010:
        _require_exact(p, 12)
        sequence, source, reserved, esp_send_us = struct.unpack("<HBBQ", p)
        return {"sequence": sequence, "source": source, "reserved": reserved, "esp_send_us": esp_send_us}
    if t == 0x0011:
        _require_exact(p, 8)
        sequence, source, marker = struct.unpack("<HHI", p)
        return {"sequence": sequence, "source": source, "marker": marker}
    if t in (0x0020, 0x0022):
        return _decode_metrics(p)
    if t == 0x0021:
        _require_exact(p, 48)
        rx_records, tx_records, persisted_records, queue_drops, storage_dropped_records, queue_high_water, protocol_errors = struct.unpack(
            "<QQQQQII", p
        )
        return {
            "rx_records": rx_records,
            "tx_records": tx_records,
            "persisted_records": persisted_records,
            "queue_drops": queue_drops,
            "storage_dropped_records": storage_dropped_records,
            "queue_high_water": queue_high_water,
            "protocol_errors": protocol_errors,
        }
    if t == 0x0030:
        if len(p) < 4:
            raise ValueError("truncated EVENT")
        event_code, severity, arg_count = struct.unpack_from("<HBB", p, 0)
        expected = 4 + arg_count * 12
        if len(p) != expected:
            raise ValueError("invalid EVENT argument length")
        args = []
        offset = 4
        for _ in range(arg_count):
            arg_id, arg_flags, value = struct.unpack_from("<HHq", p, offset)
            args.append((arg_id, arg_flags, value))
            offset += 12
        return {"event_code": event_code, "severity": severity, "args": tuple(args)}
    if t in (0x0031, 0x0032):
        _require_exact(p, 12)
        state_code, reason_code, value0, value1 = struct.unpack("<HHII", p)
        return {"state_code": state_code, "reason_code": reason_code, "value0": value0, "value1": value1}
    if t == 0x00FE:
        _require_exact(p, 8)
        reason_code, clean, reserved, registered_stream_count, reserved2 = struct.unpack("<HBBHH", p)
        return {
            "reason_code": reason_code,
            "clean": clean,
            "reserved": reserved,
            "registered_stream_count": registered_stream_count,
            "reserved2": reserved2,
        }
    return {"raw": bytes(p)}
