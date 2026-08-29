import json
import struct
import tempfile
import unittest
from pathlib import Path

from toyota_can_processor.processor import ProcessingOptions, process


class ProcessorTests(unittest.TestCase):
    def test_v23_session_and_ble_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "CANLOG" / "S0034"
            session.mkdir(parents=True)
            manifest = {"format": "ToyotaHybridCAN-Capture", "format_version": "1.3",
                        "firmware_version": "v2.3", "raw_format": "TCB1_24_byte_records",
                        "vehicle_profile": "PRIUS GEN 2", "profile_confidence_pct": 85,
                        "extra_future_field": {"preserved": True}}
            (session / "MANIFEST.JSON").write_text(json.dumps(manifest), encoding="utf-8")
            header = b"TCB1" + bytes([1, 24]) + bytes(10)
            record = struct.pack("<QI8sBBBB", 1_000_000, 0x3CB, bytes(8), 8, 0, 0, 0)
            (session / "RAW_000.TCB").write_bytes(header + record)
            (session / "EVENTS.CSV").write_text("Time_us,Severity,Event,Details\n1000000,INFO,TEST,x\n", encoding="utf-8")
            (session / "DECODED.CSV").write_text("Time_ms,Profile\n1000,PRIUS GEN 2\n", encoding="utf-8")
            (session / "DIAGNOSTICS.CSV").write_text(
                "Transaction,RequestTime_us,Status\n1,1000000,UNEXPECTED_RESPONSE\n", encoding="utf-8")
            companion = root / "companion"
            companion.mkdir()
            samples = []
            for i in range(8):
                esp = 1_000_000 + i * 1_000_000
                android = esp * 1000 + 9_000_000_000
                samples.append({"sequence": i, "t1_android_ns": android - 500_000,
                                "t4_android_ns": android + 500_000,
                                "e2_esp_us": esp - 10, "e3_esp_us": esp + 10})
            capture = {"format": "ToyotaCANSync-AndroidCapture", "format_version": "1.0",
                       "video_anchor_ns": 10_000_000_000, "video_anchor_uncertainty_ns": 33_333_334,
                       "sync_samples": samples,
                       "control_events": [{"operation": "START_PASSIVE", "status": 0, "cyd_session": 34}]}
            (companion / "CAPTURE_SYNC.json").write_text(json.dumps(capture), encoding="utf-8")
            result = process(root / "CANLOG", root / "out", companion, options=ProcessingOptions())
            output = Path(result["output"]) / "S0034"
            self.assertTrue((output / "REPORT.html").exists())
            normalized = (output / "DIAGNOSTICS_NORMALIZED.csv").read_text(encoding="utf-8")
            self.assertIn("LEGACY_POSSIBLE_EXTERNAL_DIAGNOSTIC_TRAFFIC", normalized)
            summary = json.loads((output / "SESSION_SUMMARY.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["alignment"]["valid"])
            self.assertTrue(summary["manifest"]["extra_future_field"]["preserved"])

    def test_malformed_manifest_produces_report_without_guessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = root / "S0001"
            session.mkdir()
            (session / "MANIFEST.JSON").write_text("{not-json", encoding="utf-8")
            result = process(root, root / "out", options=ProcessingOptions())
            report = json.loads((Path(result["output"]) / "S0001" /
                                 "COMPATIBILITY_REPORT.json").read_text(encoding="utf-8"))
            self.assertFalse(report["supported"])
            self.assertIn("Malformed MANIFEST.JSON", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
