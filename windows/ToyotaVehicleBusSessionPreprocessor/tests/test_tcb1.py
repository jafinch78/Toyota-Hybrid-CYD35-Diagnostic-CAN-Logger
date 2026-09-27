import hashlib
import pathlib
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session.tcb1 import iter_tcb_frames, scan_tcb_stream

HEADER = b"TCB1" + bytes([1, 24]) + b"\x00" * 10


def rec(t, can_id, data=b"\x00"*8, dlc=8, ext=0, rtr=0, direction=0):
    return struct.pack("<QI8sBBBB", t, can_id, data, dlc, ext, rtr, direction)


class Tcb1Tests(unittest.TestCase):
    def _write(self, path, records, tail=b""):
        path.write_bytes(HEADER + b"".join(records) + tail)

    def test_rotation_boundaries_do_not_change_logical_hash_or_sequence(self):
        records = [rec(100, 0x100), rec(200, 0x101), rec(300, 0x102), rec(400, 0x103)]
        expected_hash = hashlib.sha256(b"".join(records)).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            a0, a1 = root/"RAW_000.TCB", root/"RAW_001.TCB"
            b0, b1 = root/"B_RAW_000.TCB", root/"B_RAW_001.TCB"
            self._write(a0, records[:2]); self._write(a1, records[2:])
            self._write(b0, records[:1]); self._write(b1, records[1:])
            ra = scan_tcb_stream([a0, a1])
            rb = scan_tcb_stream([b0, b1])
            fa = list(iter_tcb_frames([a0, a1]))
            fb = list(iter_tcb_frames([b0, b1]))
        self.assertEqual(ra.logical_record_sha256, expected_hash)
        self.assertEqual(rb.logical_record_sha256, expected_hash)
        self.assertEqual(fa, fb)
        self.assertEqual((ra.record_count, ra.rx_count, ra.tx_count), (4, 4, 0))

    def test_truncated_final_record_is_reported_not_yielded(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)/"RAW_000.TCB"
            self._write(path, [rec(1, 0x100)], rec(2, 0x101)[:7])
            report = scan_tcb_stream([path])
            frames = list(iter_tcb_frames([path]))
        self.assertEqual(report.record_count, 1)
        self.assertEqual(report.chunks[0].truncated_tail_bytes, 7)
        self.assertEqual(len(frames), 1)

    def test_invalid_dlc_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)/"RAW_000.TCB"
            self._write(path, [rec(1, 0x100, dlc=9)])
            with self.assertRaisesRegex(ValueError, "DLC"):
                list(iter_tcb_frames([path]))

    def test_bad_header_or_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            bad_magic = root/"RAW_000.TCB"; bad_magic.write_bytes(b"BAD!" + HEADER[4:] + rec(1,0x100))
            with self.assertRaisesRegex(ValueError, "header"):
                list(iter_tcb_frames([bad_magic]))
            bad_ver = root/"RAW_001.TCB"; bad_ver.write_bytes(b"TCB1" + bytes([2,24]) + b"\0"*10 + rec(1,0x100))
            with self.assertRaisesRegex(ValueError, "version"):
                list(iter_tcb_frames([bad_ver]))

    def test_timestamp_reversal_across_chunks_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            a=root/"RAW_000.TCB"; b=root/"RAW_001.TCB"
            self._write(a,[rec(200,0x100)]); self._write(b,[rec(100,0x101)])
            with self.assertRaisesRegex(ValueError, "timestamp reversal"):
                scan_tcb_stream([a,b])


if __name__ == "__main__": unittest.main()
