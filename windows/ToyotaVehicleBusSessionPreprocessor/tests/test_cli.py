from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session import cli
from toyota_vehicle_bus_session.meta import MetaHeader, MetaRecord, write_meta

TCB_HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10
TCB_FRAME = struct.pack(
    "<QI8sBBBB",
    100,
    0x123,
    b"\x01\x02" + b"\0" * 6,
    2,
    0,
    0,
    0,
)


def lp(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def make_native(root: Path) -> Path:
    root.mkdir()
    write_meta(root / "SESSION.META", MetaHeader(1, 0, 1, 0, 1), [
        MetaRecord(0x0001, 0, 0, 1, 1,
                   lp("Logger") + lp("2.6.0") + lp("E32R35T_TOUCH") + lp("build") + lp("db")),
        MetaRecord(0x0002, 1, 0, 2, 1,
                   struct.pack("<BBBBBBHI", 1, 1, 1, 0, 3, 0, 0, 500000)),
        MetaRecord(0x0003, 1, 0, 3, 1, b""),
        MetaRecord(0x0021, 1, 0, 4, 100,
                   struct.pack("<QQQQQII", 1, 0, 1, 0, 0, 1, 0)),
        MetaRecord(0x0004, 1, 0, 5, 100, struct.pack("<H", 1)),
        MetaRecord(0x00FE, 0, 0, 6, 100, struct.pack("<HBBHH", 0, 1, 0, 1, 0)),
    ])
    (root / "RAW_000.TCB").write_bytes(TCB_HEADER + TCB_FRAME)
    return root


def invoke(arguments: list[str]) -> tuple[int, dict[str, object]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(arguments)
    return code, json.loads(stream.getvalue())


class CliTests(unittest.TestCase):
    def test_validate_success_reports_exact_input_and_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_native(root / "native")
            code, payload = invoke(["validate", str(source)])
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["input"], str(source.resolve()))
            self.assertEqual(payload["session_id"], "S0001")
            self.assertEqual(payload["raw_record_count"], 1)
            self.assertIs(payload["closed_cleanly"], True)

    def test_processing_failure_returns_one_and_json_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "bad"
            bad.mkdir()
            code, payload = invoke(["validate", str(bad)])
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(payload["error"])

    def test_expand_no_zip_reports_exact_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_native(root / "native")
            output = root / "out"
            code, payload = invoke(["expand", str(source), "-o", str(output), "--no-zip"])
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["output_root"], str((output / "CANLOG_TVM1_S0001").resolve()))
            self.assertEqual(payload["legacy_session_dir"],
                             str((output / "CANLOG_TVM1_S0001" / "S0001").resolve()))
            self.assertIsNone(payload["zip_path"])
            self.assertTrue(Path(str(payload["validation_report"])).is_file())

    def test_usage_error_is_exit_two(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            cli.main([])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
