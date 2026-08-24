#!/usr/bin/env python3
"""Convert Toyota CAN Binary (TCB1) raw logs to portable CSV.

Usage: python tcb_to_csv.py RAW_000.TCB [RAW_001.TCB ...] -o RAW.csv
"""
import argparse
import csv
import struct
from pathlib import Path

HEADER_SIZE = 16
RECORD = struct.Struct("<QI8sBBBB")


def records(path):
    with path.open("rb") as stream:
        header = stream.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE or header[:4] != b"TCB1":
            raise ValueError(f"{path}: not a TCB1 file")
        if header[5] != RECORD.size:
            raise ValueError(f"{path}: record size {header[5]}, expected {RECORD.size}")
        while True:
            raw = stream.read(RECORD.size)
            if not raw:
                return
            if len(raw) != RECORD.size:
                raise ValueError(f"{path}: truncated final record")
            yield RECORD.unpack(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("RAW.csv"))
    args = parser.parse_args()
    with args.output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["Sequence", "Time_us", "Direction", "Bus", "ID_Hex",
                         "Extended", "RTR", "DLC", *[f"D{i}" for i in range(8)]])
        sequence = 0
        for path in args.inputs:
            for time_us, can_id, data, dlc, extended, rtr, direction in records(path):
                sequence += 1
                width = 8 if extended else 3
                cells = [f"{value:02X}" if i < dlc else "" for i, value in enumerate(data)]
                writer.writerow([sequence, time_us, "TX" if direction else "RX", "HS_CAN",
                                 f"{can_id:0{width}X}", extended, rtr, dlc, *cells])
    print(f"Wrote {sequence} records to {args.output}")


if __name__ == "__main__":
    main()
