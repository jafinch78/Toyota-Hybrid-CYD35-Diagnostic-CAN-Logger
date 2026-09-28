from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_windows_1607.py"
LAUNCHER = ROOT / "RUN_WINDOWS_1607_VALIDATION.bat"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_windows_1607", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Windows validation script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10
REC = struct.Struct("<QI8sBBBB")


def tcb_bytes(records: list[tuple[int, int]]) -> bytes:
    body = b"".join(
        REC.pack(t, 0x123, b"\x01" + b"\0" * 7, 1, 0, 0, direction)
        for t, direction in records
    )
    return HEADER + body


class Windows1607ValidationTests(unittest.TestCase):
    def test_exact_windows_10_1607_build_is_required(self) -> None:
        validator = load_validator()
        self.assertTrue(validator.is_windows_10_1607("nt", 14393))
        self.assertFalse(validator.is_windows_10_1607("nt", 14394))
        self.assertFalse(validator.is_windows_10_1607("posix", 14393))
        self.assertFalse(validator.is_windows_10_1607("nt", None))

    def test_original_canlog_raw_is_scanned_directly_from_zip(self) -> None:
        validator = load_validator()
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "CANLOG.zip"
            with zipfile.ZipFile(archive, "w") as out:
                out.writestr("S0001/RAW_000.TCB", tcb_bytes([(1, 0), (2, 1)]))
                out.writestr("S0001/RAW_001.TCB", tcb_bytes([(3, 0)]))
                out.writestr("S0001/MANIFEST.JSON", "{}")
            snapshot = validator.snapshot_legacy_canlog(archive)
        self.assertEqual(snapshot["record_count"], 3)
        self.assertEqual(snapshot["rx_count"], 2)
        self.assertEqual(snapshot["tx_count"], 1)
        self.assertEqual(sorted(snapshot["chunks"]), ["RAW_000.TCB", "RAW_001.TCB"])
        self.assertEqual(snapshot["truncated_tail_bytes"], {"RAW_000.TCB": 0, "RAW_001.TCB": 0})

    def test_original_canlog_rejects_missing_raw_zero_and_path_traversal(self) -> None:
        validator = load_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "missing.zip"
            with zipfile.ZipFile(missing, "w") as out:
                out.writestr("S0001/RAW_001.TCB", tcb_bytes([(1, 0)]))
            with self.assertRaisesRegex(ValueError, "RAW_000"):
                validator.snapshot_legacy_canlog(missing)

            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as out:
                out.writestr("../RAW_000.TCB", tcb_bytes([(1, 0)]))
            with self.assertRaisesRegex(ValueError, "path traversal"):
                validator.snapshot_legacy_canlog(traversal)

    def test_raw_identity_comparison_requires_hashes_counts_directions_and_logical_stream(self) -> None:
        validator = load_validator()
        original = {
            "logical_record_sha256": "abc",
            "record_count": 10,
            "rx_count": 8,
            "tx_count": 2,
            "chunks": {"RAW_000.TCB": "111", "RAW_001.TCB": "222"},
            "truncated_tail_bytes": {"RAW_000.TCB": 0, "RAW_001.TCB": 0},
        }
        same = dict(original)
        changed = {
            **original,
            "logical_record_sha256": "def",
            "tx_count": 3,
            "chunks": {"RAW_000.TCB": "111", "RAW_001.TCB": "999"},
        }
        self.assertEqual(validator.compare_raw_identity(original, same), [])
        failures = validator.compare_raw_identity(original, changed)
        self.assertTrue(any("logical" in item.lower() for item in failures))
        self.assertTrue(any("TX count" in item for item in failures))
        self.assertTrue(any("RAW_001.TCB" in item for item in failures))

    def test_report_status_requires_platform_and_raw_pass(self) -> None:
        validator = load_validator()
        self.assertEqual(validator.final_status(True, []), "PASS")
        self.assertEqual(validator.final_status(False, []), "FAIL")
        self.assertEqual(validator.final_status(True, ["mismatch"]), "FAIL")

    def test_windows_launcher_is_offline_observable_and_preserves_errorlevel(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8").lower()
        self.assertIn('cd /d "%~dp0"', text)
        self.assertIn('.venv\\scripts\\python.exe', text)
        self.assertIn('--no-index', text)
        self.assertIn('--no-deps', text)
        self.assertIn('validate_windows_1607.py', text)
        self.assertIn('windows_1607_validation.json', text)
        self.assertIn('set "final_rc=%errorlevel%"', text)
        self.assertLess(text.index('set "final_rc=%errorlevel%"'), text.index('pause'))
        self.assertNotIn('analyzer', text)
        self.assertNotIn('builder', text)


if __name__ == "__main__":
    unittest.main()
