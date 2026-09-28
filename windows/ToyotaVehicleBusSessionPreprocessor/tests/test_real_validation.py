from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from toyota_vehicle_bus_session.tcb1 import scan_tcb_stream

# The production validation campaign script is imported by path so it remains
# usable as a standalone script without making scripts/ a runtime package.
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_real_sessions.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_real_sessions", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load validation script")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10
REC = struct.Struct("<QI8sBBBB")


def write_tcb(path: Path, times: list[int]) -> None:
    body = b"".join(REC.pack(t, 0x123, b"\x01" + b"\0" * 7, 1, 0, 0, 0) for t in times)
    path.write_bytes(HEADER + body)


class RealValidationGateTests(unittest.TestCase):
    def test_raw_snapshot_records_chunk_hashes_and_logical_stream(self) -> None:
        validator = load_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_tcb(root / "RAW_000.TCB", [1, 2])
            write_tcb(root / "RAW_001.TCB", [3])
            snapshot = validator.raw_snapshot(root)
            expected = scan_tcb_stream([root / "RAW_000.TCB", root / "RAW_001.TCB"])
            first_chunk_bytes = HEADER + b"".join(
                REC.pack(t, 0x123, b"\x01" + b"\0" * 7, 1, 0, 0, 0)
                for t in [1, 2]
            )
        self.assertEqual(snapshot["record_count"], 3)
        self.assertEqual(snapshot["logical_record_sha256"], expected.logical_record_sha256)
        self.assertEqual([item["name"] for item in snapshot["chunks"]], ["RAW_000.TCB", "RAW_001.TCB"])
        self.assertEqual(
            snapshot["chunks"][0]["sha256"],
            hashlib.sha256(first_chunk_bytes).hexdigest(),
        )

    def test_compare_raw_snapshots_blocks_record_or_hash_change(self) -> None:
        validator = load_validator()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a"; b = root / "b"
            a.mkdir(); b.mkdir()
            write_tcb(a / "RAW_000.TCB", [1, 2])
            write_tcb(b / "RAW_000.TCB", [1, 3])
            failures = validator.compare_raw_snapshots(
                validator.raw_snapshot(a), validator.raw_snapshot(b), "native")
        self.assertTrue(any("logical CAN" in item for item in failures))
        self.assertTrue(any("RAW_000.TCB SHA-256" in item for item in failures))

    def test_gate_is_fail_closed_when_builder_or_platform_evidence_missing(self) -> None:
        validator = load_validator()
        cases = [
            {"session_id": "S0141", "raw_gate": "PASS", "builder_gate": "NOT_RUN"},
            {"session_id": "S0149", "raw_gate": "PASS", "builder_gate": "PASS"},
            {"session_id": "S0128", "raw_gate": "PASS", "builder_gate": "PASS"},
        ]
        self.assertEqual(validator.final_gate_status(cases, "PASS"), "FAIL")
        cases[0]["builder_gate"] = "PASS"
        self.assertEqual(validator.final_gate_status(cases, "NOT_RUN"), "FAIL")

    def test_gate_requires_exact_three_builder_sessions_and_windows_1607(self) -> None:
        validator = load_validator()
        self.assertEqual(
            validator.REQUIRED_BUILDER_SESSIONS,
            ("S0141", "S0149", "S0128"),
        )
        cases = [
            {"session_id": "S0141", "raw_gate": "PASS", "builder_gate": "PASS"},
            {"session_id": "S0149", "raw_gate": "PASS", "builder_gate": "PASS"},
            {"session_id": "S0128", "raw_gate": "PASS", "builder_gate": "PASS"},
        ]
        self.assertEqual(validator.final_gate_status(cases, "PASS"), "PASS")

        self.assertEqual(validator.final_gate_status(cases[:2], "PASS"), "FAIL")

        wrong = [dict(item) for item in cases]
        wrong[2]["session_id"] = "S0999"
        self.assertEqual(validator.final_gate_status(wrong, "PASS"), "FAIL")

        duplicate = [dict(cases[0]), dict(cases[0]), dict(cases[2])]
        self.assertEqual(validator.final_gate_status(duplicate, "PASS"), "FAIL")

        extra = cases + [
            {"session_id": "S0999", "raw_gate": "FAIL", "builder_gate": "FAIL"},
        ]
        self.assertEqual(validator.final_gate_status(extra, "PASS"), "FAIL")

        failed = [dict(item) for item in cases]
        failed[1]["builder_gate"] = "FAIL"
        self.assertEqual(validator.final_gate_status(failed, "PASS"), "FAIL")
        self.assertEqual(validator.final_gate_status(cases, "FAIL"), "FAIL")

    def test_parser_has_no_analyzer_smoke_report_gate(self) -> None:
        validator = load_validator()
        option_names = {action.dest for action in validator.build_parser()._actions}
        self.assertNotIn("analyzer_smoke_report", option_names)


if __name__ == "__main__":
    unittest.main()
