import hashlib
import pathlib
import struct
import tempfile
import unittest
import zipfile

from toyota_vehicle_bus_session.meta import MetaHeader, MetaRecord, write_meta
from toyota_vehicle_bus_session.packaging import expand_native_session

HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10


def lp(text):
    raw = text.encode()
    return struct.pack("<H", len(raw)) + raw


def make(root):
    root.mkdir()
    write_meta(root / "SESSION.META", MetaHeader(1, 0, 1, 0, 1), [
        MetaRecord(1, 0, 0, 1, 1, lp("L") + lp("V") + lp("B") + lp("I") + lp("")),
        MetaRecord(2, 1, 0, 2, 1, struct.pack("<BBBBBBHI", 1, 1, 1, 0, 3, 0, 0, 500000)),
        MetaRecord(0xFE, 0, 0, 3, 2, struct.pack("<HBBHH", 0, 1, 0, 1, 0)),
    ])
    (root / "RAW_000.TCB").write_bytes(HEADER)
    return root


class PackagingTests(unittest.TestCase):
    def test_zip_is_deterministic_sorted_and_fixed_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            src = make(root / "src")
            first = expand_native_session(src, root / "a")
            second = expand_native_session(src, root / "b")
            self.assertEqual(hashlib.sha256(first.zip_path.read_bytes()).hexdigest(), hashlib.sha256(second.zip_path.read_bytes()).hexdigest())
            with zipfile.ZipFile(first.zip_path) as archive:
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))


if __name__ == "__main__":
    unittest.main()
