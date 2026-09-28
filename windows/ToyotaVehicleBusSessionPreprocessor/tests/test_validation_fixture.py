import csv
import hashlib
import json
import pathlib
import struct
import tempfile
import unittest
import zipfile

from toyota_vehicle_bus_session.packaging import expand_native_session
from toyota_vehicle_bus_session.validation_fixture import synthesize_native_fixture

HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10
RECORD = struct.Struct("<QI8sBBBB")


def raw_record(time_us, can_id, direction=0):
    return RECORD.pack(time_us, can_id, b"\0" * 8, 8, 0, 0, direction)


class ValidationFixtureTests(unittest.TestCase):
    def make_legacy(self, root, *, clean=True):
        session = root / "S0166"
        session.mkdir(parents=True)
        (session / "RAW_000.TCB").write_bytes(
            HEADER + raw_record(100, 0x100, 0) + raw_record(200, 0x7E0, 1)
        )
        (session / "MANIFEST.JSON").write_text(json.dumps({
            "session_id": "S0166",
            "firmware": "Logger",
            "firmware_version": "2.5",
            "board_profile": "E32R35T_TOUCH",
            "runtime_database": "db",
            "closed_cleanly": True,
        }), encoding="utf-8")
        (session / "CHECKPOINT.JSON").write_text(json.dumps({
            "closed_cleanly": clean,
            "session_received_frames": 1,
            "session_transmitted_frames": 1,
            "can_queue_drops": 2,
            "sd_log_dropped_frames": 3,
        }), encoding="utf-8")
        with (session / "SYNC.CSV").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Sequence", "ESP_Receive_us", "ESP_Send_us", "Source"])
            writer.writerow([7, 110, 120, "BLE"])
        with (session / "EVENTS.CSV").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Time_us", "Severity", "Event", "Details"])
            writer.writerow([130, "INFO", "LOGGING_STARTED", "free form detail"])
            writer.writerow([140, "WARNING", "UNKNOWN_EVENT", "xyz"])
        if not clean:
            (session / "SESSION.OPEN").write_text("open", encoding="utf-8")
        return session

    def test_round_trip_preserves_raw_identity_and_reports_lossy_event_detail(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            legacy = self.make_legacy(base / "legacy")
            original_hash = hashlib.sha256((legacy / "RAW_000.TCB").read_bytes()).hexdigest()

            native = synthesize_native_fixture(legacy, base / "native")
            synthetic_hash = hashlib.sha256((native.native_session_dir / "RAW_000.TCB").read_bytes()).hexdigest()
            expanded = expand_native_session(native.native_session_dir, base / "expanded")
            expanded_hash = hashlib.sha256((expanded.legacy_session_dir / "RAW_000.TCB").read_bytes()).hexdigest()
            synthesis_report = json.loads(native.report_path.read_text(encoding="utf-8"))

        self.assertEqual(original_hash, synthetic_hash)
        self.assertEqual(synthetic_hash, expanded_hash)
        self.assertEqual(native.session_id, "S0166")
        self.assertEqual(synthesis_report["raw_identity"]["RAW_000.TCB"], original_hash)
        self.assertGreaterEqual(len(synthesis_report["warnings"]), 2)
        self.assertTrue(all(
            warning["code"] == "VALIDATION_FIXTURE_LOSSY_EVENT_DETAIL"
            for warning in synthesis_report["warnings"]
        ))

    def test_zip_input_with_nested_canlog_session_is_supported(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            legacy = self.make_legacy(base / "legacy" / "CANLOG")
            archive = base / "CANLOG_fixture.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted((base / "legacy").rglob("*")):
                    if path.is_file():
                        bundle.write(path, path.relative_to(base / "legacy").as_posix())

            native = synthesize_native_fixture(archive, base / "native")
            report = json.loads(native.report_path.read_text(encoding="utf-8"))

        self.assertEqual(native.session_id, "S0166")
        self.assertEqual(report["source_kind"], "ZIP")
        self.assertEqual(report["source_archive"], str(archive.resolve()))

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            archive = base / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape/MANIFEST.JSON", "{}")
            with self.assertRaisesRegex(ValueError, "path traversal"):
                synthesize_native_fixture(archive, base / "native")

    def test_stale_manifest_or_session_open_cannot_upgrade_unclean_session(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            legacy = self.make_legacy(base / "legacy", clean=False)
            native = synthesize_native_fixture(legacy, base / "native")
            expanded = expand_native_session(native.native_session_dir, base / "expanded")
            synthesis_report = json.loads(native.report_path.read_text(encoding="utf-8"))
            expanded_manifest = json.loads(
                (expanded.legacy_session_dir / "MANIFEST.JSON").read_text(encoding="utf-8")
            )
            session_open_exists = (expanded.legacy_session_dir / "SESSION.OPEN").exists()

        self.assertFalse(synthesis_report["closed_cleanly"])
        self.assertFalse(expanded_manifest["closed_cleanly"])
        self.assertTrue(session_open_exists)


if __name__ == "__main__":
    unittest.main()
