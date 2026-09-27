from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
from typing import Iterator, Sequence

HEADER_SIZE = 16
RECORD_SIZE = 24
HEADER_MAGIC = b"TCB1"
HEADER_VERSION = 1
_RECORD = struct.Struct("<QI8sBBBB")
_CHUNK_INDEX = re.compile(r"(?:^|_)RAW_(\d+)\.TCB$", re.IGNORECASE)


@dataclass(frozen=True)
class TcbFrame:
    time_us: int
    can_id: int
    data: bytes
    dlc: int
    extended: int
    rtr: int
    direction: int


@dataclass(frozen=True)
class TcbChunkReport:
    path: Path
    records: int
    truncated_tail_bytes: int
    first_time_us: int | None
    last_time_us: int | None
    sha256: str


@dataclass(frozen=True)
class CanStreamReport:
    chunks: tuple[TcbChunkReport, ...]
    record_count: int
    logical_record_sha256: str
    rx_count: int
    tx_count: int
    first_time_us: int | None
    last_time_us: int | None


def _validate_header(header: bytes, path: Path) -> None:
    if len(header) != HEADER_SIZE or header[:4] != HEADER_MAGIC:
        raise ValueError(f"invalid TCB1 header: {path}")
    if header[4] != HEADER_VERSION:
        raise ValueError(f"unsupported TCB1 version: {header[4]}")
    if header[5] != RECORD_SIZE:
        raise ValueError(f"unsupported TCB1 record size: {header[5]}")


def _decode_record(raw: bytes, path: Path) -> TcbFrame:
    time_us, can_id, data, dlc, extended, rtr, direction = _RECORD.unpack(raw)
    if dlc > 8:
        raise ValueError(f"invalid TCB1 DLC {dlc} in {path}")
    if extended not in (0, 1) or rtr not in (0, 1) or direction not in (0, 1):
        raise ValueError(f"invalid TCB1 flag in {path}")
    return TcbFrame(time_us, can_id, data, dlc, extended, rtr, direction)


def iter_tcb_frames(paths: Sequence[Path]) -> Iterator[TcbFrame]:
    for raw_path in paths:
        path = Path(raw_path)
        with path.open("rb") as f:
            _validate_header(f.read(HEADER_SIZE), path)
            while True:
                raw = f.read(RECORD_SIZE)
                if not raw:
                    break
                if len(raw) < RECORD_SIZE:
                    break
                yield _decode_record(raw, path)


def _chunk_index(path: Path) -> int | None:
    m = _CHUNK_INDEX.search(path.name)
    return int(m.group(1)) if m else None


def scan_tcb_stream(paths: Sequence[Path]) -> CanStreamReport:
    if not paths:
        raise ValueError("TCB1 stream has no chunks")
    path_list = [Path(p) for p in paths]
    indexes = [_chunk_index(p) for p in path_list]
    if all(index is not None for index in indexes):
        numeric = [int(index) for index in indexes if index is not None]
        if len(set(numeric)) != len(numeric):
            raise ValueError("duplicate TCB1 chunk index")
        order = sorted(range(len(path_list)), key=lambda i: numeric[i])
        path_list = [path_list[i] for i in order]

    logical = hashlib.sha256()
    chunks: list[TcbChunkReport] = []
    total = rx_count = tx_count = 0
    stream_first: int | None = None
    stream_last: int | None = None

    for path in path_list:
        file_hash = hashlib.sha256()
        chunk_records = 0
        chunk_first: int | None = None
        chunk_last: int | None = None
        with path.open("rb") as f:
            header = f.read(HEADER_SIZE)
            file_hash.update(header)
            _validate_header(header, path)
            while True:
                raw = f.read(RECORD_SIZE)
                if not raw:
                    tail = 0
                    break
                file_hash.update(raw)
                if len(raw) < RECORD_SIZE:
                    tail = len(raw)
                    break
                frame = _decode_record(raw, path)
                if stream_last is not None and frame.time_us < stream_last:
                    raise ValueError(f"TCB1 timestamp reversal across stream at {path}")
                logical.update(raw)
                chunk_records += 1
                total += 1
                if frame.direction == 0:
                    rx_count += 1
                else:
                    tx_count += 1
                if chunk_first is None:
                    chunk_first = frame.time_us
                chunk_last = frame.time_us
                if stream_first is None:
                    stream_first = frame.time_us
                stream_last = frame.time_us
        chunks.append(
            TcbChunkReport(path, chunk_records, tail, chunk_first, chunk_last, file_hash.hexdigest())
        )

    return CanStreamReport(
        chunks=tuple(chunks),
        record_count=total,
        logical_record_sha256=logical.hexdigest(),
        rx_count=rx_count,
        tx_count=tx_count,
        first_time_us=stream_first,
        last_time_us=stream_last,
    )
