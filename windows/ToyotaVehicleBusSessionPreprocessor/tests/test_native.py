import pathlib
import struct
import tempfile
import unittest
import zipfile

from toyota_vehicle_bus_session.meta import MetaHeader, MetaRecord, write_meta
from toyota_vehicle_bus_session.native import load_native_session

HEADER = b"TCB1" + bytes([1,24]) + b"\0"*10

def rec(t=1):
    return struct.pack("<QI8sBBBB", t, 0x100, b"\0"*8, 8, 0, 0, 0)


def make_meta(path, session=166):
    write_meta(path, MetaHeader(1,0,session,0,10), [
        MetaRecord(0x0002,1,0,1,10,struct.pack("<BBBBBBHI",1,1,1,0,3,0,0,500000)),
        MetaRecord(0x0003,1,0,2,10,b""),
    ])


class NativeSessionTests(unittest.TestCase):
    def test_folder_load_discovers_can_stream_and_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)/"S0166"; root.mkdir()
            make_meta(root/"SESSION.META")
            (root/"RAW_000.TCB").write_bytes(HEADER+rec())
            session=load_native_session(root)
        self.assertEqual(session.session_id,"S0166")
        self.assertEqual(session.can_stream.record_count,1)
        self.assertEqual([p.name for p in session.can_paths],["RAW_000.TCB"])

    def test_missing_raw_zero_and_noncontiguous_suffixes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)/"S0166"; root.mkdir(); make_meta(root/"SESSION.META")
            (root/"RAW_001.TCB").write_bytes(HEADER+rec())
            with self.assertRaisesRegex(ValueError,"RAW_000"):
                load_native_session(root)
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)/"S0166"; root.mkdir(); make_meta(root/"SESSION.META")
            (root/"RAW_000.TCB").write_bytes(HEADER+rec()); (root/"RAW_002.TCB").write_bytes(HEADER+rec(2))
            with self.assertRaisesRegex(ValueError,"noncontiguous"):
                load_native_session(root)

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            z=pathlib.Path(td)/"bad.zip"
            with zipfile.ZipFile(z,"w") as out:
                out.writestr("../escape.txt","bad")
                out.writestr("S0166/SESSION.META",b"x")
            with self.assertRaisesRegex(ValueError,"path traversal"):
                load_native_session(z)

    def test_zip_must_contain_exactly_one_session_meta(self):
        with tempfile.TemporaryDirectory() as td:
            z=pathlib.Path(td)/"multi.zip"
            with zipfile.ZipFile(z,"w") as out:
                out.writestr("S0001/SESSION.META",b"x")
                out.writestr("S0002/SESSION.META",b"x")
            with self.assertRaisesRegex(ValueError,"exactly one"):
                load_native_session(z)


if __name__ == "__main__": unittest.main()
