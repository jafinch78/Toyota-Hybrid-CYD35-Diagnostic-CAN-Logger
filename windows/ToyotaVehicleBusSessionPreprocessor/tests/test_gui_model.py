from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session.gui import GuiModel
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


class GuiModelTests(unittest.TestCase):
    def test_validate_updates_visible_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = make_native(Path(temp) / "native")
            model = GuiModel()
            self.assertTrue(model.validate(source))
            self.assertEqual(model.status, "PASS")
            self.assertEqual(model.stage, "Validation complete")
            self.assertEqual(model.session_id, "S0001")
            self.assertEqual(model.raw_record_count, 1)
            self.assertIs(model.closed_cleanly, True)
            self.assertEqual(model.warnings, [])

    def test_validation_failure_is_visible_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "bad"
            bad.mkdir()
            model = GuiModel()
            self.assertFalse(model.validate(bad))
            self.assertEqual(model.status, "FAIL")
            self.assertEqual(model.stage, "Validation failed")
            self.assertTrue(model.warnings)

    def test_expand_sets_openable_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_native(root / "native")
            output = root / "out"
            model = GuiModel()
            self.assertTrue(model.expand(source, output, make_zip=False))
            expected = (output / "CANLOG_TVM1_S0001").resolve()
            self.assertEqual(model.status, "PASS")
            self.assertEqual(model.stage, "Expansion complete")
            self.assertEqual(model.output_folder, str(expected))
            self.assertTrue(expected.is_dir())


if __name__ == "__main__":
    unittest.main()
