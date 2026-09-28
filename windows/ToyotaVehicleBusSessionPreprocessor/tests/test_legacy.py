import csv
import hashlib
import json
import pathlib
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session.legacy import build_legacy_checkpoint, build_legacy_manifest, write_legacy_events, write_legacy_sync
from toyota_vehicle_bus_session.meta import MetaHeader, MetaRecord, write_meta
from toyota_vehicle_bus_session.model import ExpansionOptions
from toyota_vehicle_bus_session.native import load_native_session
from toyota_vehicle_bus_session.packaging import expand_native_session

HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10


def rec(t, can_id=0x100, direction=0):
    return struct.pack("<QI8sBBBB", t, can_id, b"\0" * 8, 8, 0, 0, direction)


def lp(text):
    raw = text.encode()
    return struct.pack("<H", len(raw)) + raw


def make(root, clean=True):
    root.mkdir(parents=True, exist_ok=True)
    records = [
        MetaRecord(1, 0, 0, 1, 10, lp("Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger") + lp("2.6.0") + lp("E32R35T_TOUCH") + lp("abc123") + lp("ToyotaHybridCAN-Canonical-v1")),
        MetaRecord(2, 1, 0, 2, 10, struct.pack("<BBBBBBHI", 1, 1, 1, 0, 3, 0, 0, 500000)),
        MetaRecord(0x10, 0, 0, 3, 110, struct.pack("<HBBQ", 7, 0, 0, 120)),
        MetaRecord(0x20, 0, 0, 4, 200, struct.pack("<HHHHQ", 1, 1, 1, 0, 123456)),
        MetaRecord(0x21, 1, 0, 5, 200, struct.pack("<QQQQQII", 2, 1, 3, 4, 5, 6, 7)),
        MetaRecord(0x30, 1, 0, 6, 210, struct.pack("<HBBHHq", 6, 1, 1, 3, 0, 0x7E0)),
    ]
    if clean:
        records.append(MetaRecord(0xFE, 0, 0, 7, 300000, struct.pack("<HBBHH", 0, 1, 0, 1, 0)))
    write_meta(root / "SESSION.META", MetaHeader(1, 0, 166, 0, 10), records)
    (root / "RAW_000.TCB").write_bytes(HEADER + rec(100000, 0x100, 0) + rec(250000, 0x7E0, 1))
    return root


class LegacyTests(unittest.TestCase):
    def test_schema_headers_and_manifest_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = make(pathlib.Path(td) / "S0166")
            session = load_native_session(root)
            manifest = build_legacy_manifest(session)
            checkpoint = build_legacy_checkpoint(session)
            self.assertEqual((manifest["format"], manifest["format_version"], manifest["raw_format"]), ("ToyotaHybridCAN-Capture", "1.4", "TCB1_24_byte_records"))
            self.assertEqual((manifest["firmware"], manifest["firmware_version"], manifest["board_profile"]), ("Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger", "2.6.0", "E32R35T_TOUCH"))
            self.assertEqual((manifest["first_can_time_us"], manifest["last_can_time_us"]), (100000, 250000))
            self.assertEqual((manifest["rx_records"], manifest["tx_records"], manifest["persisted_records"], manifest["queue_drops"]), (2, 1, 3, 4))
            self.assertEqual(manifest["native_capture_format"], "TVM1")
            self.assertEqual(manifest["native_capture_version"], "1.0")
            self.assertEqual(manifest["runtime_database"], "ToyotaHybridCAN-Canonical-v1")
            self.assertEqual(checkpoint["actual_raw_records"], 2)
            self.assertEqual(checkpoint["queue_drops"], 4)
            self.assertTrue(manifest["closed_cleanly"])

    def test_sync_and_events_headers_and_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = make(pathlib.Path(td) / "S0166")
            session = load_native_session(root)
            out = pathlib.Path(td) / "out"
            out.mkdir()
            self.assertEqual(write_legacy_sync(session, out / "SYNC.CSV"), 1)
            self.assertEqual(write_legacy_events(session, out / "EVENTS.CSV"), 1)
            with (out / "SYNC.CSV").open(newline="", encoding="utf-8") as f:
                sync_rows = list(csv.reader(f))
            with (out / "EVENTS.CSV").open(newline="", encoding="utf-8") as f:
                event_rows = list(csv.reader(f))
            self.assertEqual(sync_rows[0], ["Sequence", "ESP_Receive_us", "ESP_Send_us", "Source"])
            self.assertEqual(sync_rows[1], ["7", "110", "120", "BLE"])
            self.assertEqual(event_rows[0], ["Time_us", "Severity", "Event", "Details"])
            self.assertEqual(event_rows[1][2], "EXTERNAL_TESTER_DETECTED")

    def test_unclean_session_stays_unclean_and_emits_open_marker(self):
        with tempfile.TemporaryDirectory() as td:
            src = make(pathlib.Path(td) / "src", False)
            result = expand_native_session(src, pathlib.Path(td) / "out", options=ExpansionOptions(make_zip=False))
            manifest = json.loads((result.legacy_session_dir / "MANIFEST.JSON").read_text())
            self.assertFalse(manifest["closed_cleanly"])
            self.assertTrue((result.legacy_session_dir / "SESSION.OPEN").exists())

    def test_expansion_copies_raw_and_generates_offline_decoded_compatibility_product(self):
        with tempfile.TemporaryDirectory() as td:
            src = make(pathlib.Path(td) / "src")
            raw = (src / "RAW_000.TCB").read_bytes()
            result = expand_native_session(src, pathlib.Path(td) / "out", options=ExpansionOptions(make_zip=False))
            copied = (result.legacy_session_dir / "RAW_000.TCB").read_bytes()
            self.assertEqual(copied, raw)
            self.assertEqual(hashlib.sha256(copied).hexdigest(), hashlib.sha256(raw).hexdigest())
            report = json.loads(result.validation_report.read_text())
            self.assertEqual(report["products"]["DECODED.CSV"], "GENERATED_DERIVED_FROM_RAW_META")
            self.assertEqual(report["products"]["SIGNALS.CSV"], "NOT_GENERATED_DERIVED")
            self.assertEqual(report["products"]["PLOT.CSV"], "NOT_GENERATED_DERIVED")
            self.assertGreater(report["decoded_projection"]["rows"], 0)
            self.assertEqual(report["decoded_projection"]["source"], "RAW_TCB1_PLUS_TVM1")
            self.assertEqual(report["decoded_projection"]["algorithm"], "legacy_live_projection_v1")
            decoded_path = result.legacy_session_dir / "DECODED.CSV"
            self.assertTrue(decoded_path.is_file())
            with decoded_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertGreater(len(rows), 1)
            self.assertEqual(rows[0][0:3], ["Time_ms", "Profile", "ProfileConfidence"])
            self.assertTrue((result.legacy_session_dir / "DIAGNOSTICS.CSV").read_text().startswith("Transaction,RequestTime_us,"))
            self.assertTrue((result.legacy_session_dir / "EXTERNAL_DIAGNOSTICS.CSV").read_text().startswith("Time_us,CAN_ID,DLC,DataHex,Classification"))


if __name__ == "__main__":
    unittest.main()
