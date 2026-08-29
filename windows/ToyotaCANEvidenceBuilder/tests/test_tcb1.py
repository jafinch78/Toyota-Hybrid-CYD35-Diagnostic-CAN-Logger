import csv
import struct
import tempfile
import unittest
from pathlib import Path

from toyota_can_processor.tcb1 import process_tcb_files


class TcbTests(unittest.TestCase):
    def test_complete_records_and_truncated_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "RAW_000.TCB"
            header = bytes([ord("T"), ord("C"), ord("B"), ord("1"), 1, 24, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
            record = struct.pack("<QI8sBBBB", 123456, 0x3CB, bytes.fromhex("0102030405060708"), 8, 0, 0, 0)
            raw.write_bytes(header + record + b"TAIL")
            summary = process_tcb_files([raw], root / "RAW.csv", root / "INVENTORY.csv")
            self.assertEqual(summary["raw_record_count"], 1)
            self.assertEqual(summary["truncated_tail_bytes_total"], 4)
            with (root / "RAW.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["CAN_ID"], "3CB")


if __name__ == "__main__":
    unittest.main()
