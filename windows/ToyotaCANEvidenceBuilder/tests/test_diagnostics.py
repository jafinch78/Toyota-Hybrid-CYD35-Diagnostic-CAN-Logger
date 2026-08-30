import csv
import json
import tempfile
import unittest
from pathlib import Path

from toyota_can_processor.database import load_database
from toyota_can_processor.diagnostics import decode_block_array, reconstruct_external_diagnostics


class DiagnosticTests(unittest.TestCase):
    def test_s0010_21ce_reassembly_and_block_decode(self):
        frames = [
            (220053350, "7E2", "0221CE0000000000", "EXTERNAL_REQUEST"),
            (220055083, "7EA", "102761CE5A810B85", "EXTERNAL_RESPONSE"),
            (220056107, "7EA", "21FB85FE85FB8600", "EXTERNAL_RESPONSE"),
            (220057093, "7EA", "22860085FB85FB85", "EXTERNAL_RESPONSE"),
            (220058127, "7EA", "23FE85FB85F985FB", "EXTERNAL_RESPONSE"),
            (220059183, "7EA", "2485FB85F985FE85", "EXTERNAL_RESPONSE"),
            (220060181, "7EA", "25FE85FB85F40000", "EXTERNAL_RESPONSE"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "EXTERNAL_DIAGNOSTICS.CSV"
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["Time_us", "CAN_ID", "DLC", "DataHex", "Classification"])
                for time_us, can_id, data, classification in frames:
                    writer.writerow([time_us, can_id, 8, data, classification])
            transactions = reconstruct_external_diagnostics(source)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].status, "OK")
        self.assertEqual(len(transactions[0].response_payload), 39)
        database, _ = load_database()
        definition = database["definitions"][0]
        decoded = decode_block_array(transactions[0].response_payload, definition)
        self.assertIsNotNone(decoded)
        self.assertEqual(len(decoded["values"]), 17)
        self.assertAlmostEqual(decoded["average"], 15.316471, places=5)
        self.assertAlmostEqual(decoded["difference"], 0.12, places=6)
        self.assertAlmostEqual(decoded["sum"], 260.38, places=2)


if __name__ == "__main__":
    unittest.main()
