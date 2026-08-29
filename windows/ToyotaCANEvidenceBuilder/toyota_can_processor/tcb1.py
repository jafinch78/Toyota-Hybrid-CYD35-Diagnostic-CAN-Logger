from __future__ import annotations

import csv
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import BinaryIO, Iterator


HEADER_SIZE = 16
RECORD_SIZE = 24
RECORD = struct.Struct("<QI8sBBBB")


@dataclass(frozen=True)
class Frame:
    time_us: int
    can_id: int
    data: bytes
    dlc: int
    extended: int
    rtr: int
    direction: int


@dataclass
class TcbFileReport:
    path: str
    records: int
    truncated_tail_bytes: int
    first_time_us: int | None
    last_time_us: int | None


def validate_header(stream: BinaryIO, path: Path) -> None:
    header = stream.read(HEADER_SIZE)
    if len(header) != HEADER_SIZE:
        raise ValueError(f"{path}: file is shorter than the TCB1 header")
    if header[:4] != b"TCB1":
        raise ValueError(f"{path}: unsupported raw magic {header[:4]!r}")
    if header[4] != 1 or header[5] != RECORD_SIZE:
        raise ValueError(f"{path}: unsupported TCB1 version/record size {header[4]}/{header[5]}")


def iter_frames(path: Path) -> Iterator[Frame]:
    with path.open("rb") as stream:
        validate_header(stream, path)
        while True:
            raw = stream.read(RECORD_SIZE)
            if len(raw) < RECORD_SIZE:
                return
            time_us, can_id, data, dlc, extended, rtr, direction = RECORD.unpack(raw)
            if dlc > 8:
                raise ValueError(f"{path}: invalid DLC {dlc}")
            yield Frame(time_us, can_id, data[:dlc], dlc, extended, rtr, direction)


def process_tcb_files(paths: list[Path], raw_csv: Path | None, inventory_csv: Path) -> dict:
    counts: Counter[tuple[int, int]] = Counter()
    dlcs: dict[tuple[int, int], Counter[int]] = defaultdict(Counter)
    byte_min: dict[tuple[int, int], list[int]] = {}
    byte_max: dict[tuple[int, int], list[int]] = {}
    first: dict[tuple[int, int], int] = {}
    last: dict[tuple[int, int], int] = {}
    reports: list[TcbFileReport] = []
    total = 0
    writer = None
    output = None
    if raw_csv is not None:
        output = raw_csv.open("w", newline="", encoding="utf-8")
        writer = csv.writer(output)
        writer.writerow(["Time_us", "CAN_ID", "DLC", "DataHex", "Extended", "RTR", "Direction"])
    try:
        for path in sorted(paths):
            size = path.stat().st_size
            usable = max(0, size - HEADER_SIZE)
            tail = usable % RECORD_SIZE
            file_count = 0
            file_first = None
            file_last = None
            for frame in iter_frames(path):
                total += 1
                file_count += 1
                file_first = frame.time_us if file_first is None else file_first
                file_last = frame.time_us
                key = (frame.can_id, frame.direction)
                counts[key] += 1
                dlcs[key][frame.dlc] += 1
                first.setdefault(key, frame.time_us)
                last[key] = frame.time_us
                if key not in byte_min:
                    byte_min[key] = [255] * 8
                    byte_max[key] = [0] * 8
                for index, value in enumerate(frame.data):
                    byte_min[key][index] = min(byte_min[key][index], value)
                    byte_max[key][index] = max(byte_max[key][index], value)
                if writer:
                    writer.writerow([frame.time_us, f"{frame.can_id:03X}", frame.dlc,
                                     frame.data.hex().upper(), frame.extended, frame.rtr,
                                     "TX" if frame.direction else "RX"])
            reports.append(TcbFileReport(path.name, file_count, tail, file_first, file_last))
    finally:
        if output:
            output.close()

    with inventory_csv.open("w", newline="", encoding="utf-8") as output_inventory:
        inventory = csv.writer(output_inventory)
        inventory.writerow(["CAN_ID", "Direction", "Frames", "First_us", "Last_us",
                            "Duration_s", "Mean_rate_Hz", "DLC_counts", "Variable_byte_mask"])
        for key in sorted(counts):
            can_id, direction = key
            duration_s = max(0.0, (last[key] - first[key]) / 1_000_000.0)
            rate = counts[key] / duration_s if duration_s else 0.0
            variable_mask = 0
            for index in range(8):
                if byte_min[key][index] != byte_max[key][index]:
                    variable_mask |= 1 << index
            inventory.writerow([f"{can_id:03X}", "TX" if direction else "RX", counts[key],
                                first[key], last[key], f"{duration_s:.6f}", f"{rate:.3f}",
                                ";".join(f"{dlc}:{count}" for dlc, count in sorted(dlcs[key].items())),
                                f"0x{variable_mask:02X}"])

    return {
        "raw_record_count": total,
        "arbitration_id_direction_pairs": len(counts),
        "files": [asdict(report) for report in reports],
        "truncated_tail_bytes_total": sum(report.truncated_tail_bytes for report in reports),
    }
