import pathlib
import struct
import tempfile
import unittest
import zlib

from toyota_vehicle_bus_session.meta import (
    MetaHeader,
    MetaRecord,
    decode_record_payload,
    encode_record,
    read_meta,
    write_meta,
)


def lp(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


class MetaCodecTests(unittest.TestCase):
    def setUp(self):
        self.header = MetaHeader(1, 0, 166, 0, 123456)

    def test_header_is_exact_32_bytes_with_crc_over_first_24(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "SESSION.META"
            write_meta(path, self.header, [])
            raw = path.read_bytes()
        self.assertEqual(len(raw), 32)
        self.assertEqual(raw[:4], b"TVM1")
        major, minor, header_size = struct.unpack_from("<BBH", raw, 4)
        self.assertEqual((major, minor, header_size), (1, 0, 32))
        self.assertEqual(struct.unpack_from("<I", raw, 8)[0], 166)
        self.assertEqual(struct.unpack_from("<Q", raw, 16)[0], 123456)
        self.assertEqual(struct.unpack_from("<I", raw, 24)[0], zlib.crc32(raw[:24]) & 0xFFFFFFFF)
        self.assertEqual(struct.unpack_from("<I", raw, 28)[0], 0)

    def test_record_envelope_and_crc_match_spec(self):
        rec = MetaRecord(0x0004, 1, 0, 7, 999, struct.pack("<H", 3))
        raw = encode_record(rec)
        self.assertEqual(len(raw), 26)
        self.assertEqual(struct.unpack_from("<H", raw, 0)[0], 0xA55A)
        self.assertEqual(struct.unpack_from("<H", raw, 2)[0], 26)
        self.assertEqual(struct.unpack_from("<HBBIQ", raw, 4), (0x0004, 1, 0, 7, 999))
        self.assertEqual(struct.unpack_from("<I", raw, len(raw) - 4)[0], zlib.crc32(raw[:-4]) & 0xFFFFFFFF)

    def test_round_trip_preserves_unknown_valid_record_and_reports_unknown_type(self):
        records = (
            MetaRecord(0x0003, 1, 0, 1, 100, b""),
            MetaRecord(0x7777, 9, 0, 2, 101, b"abc"),
            MetaRecord(0x00FE, 0, 0, 3, 102, struct.pack("<HBBHH", 0, 1, 0, 1, 0)),
        )
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "SESSION.META"
            write_meta(path, self.header, records)
            result = read_meta(path)
        self.assertEqual(result.header, self.header)
        self.assertEqual(result.records, records)
        self.assertEqual(result.recovery.unknown_record_types, (0x7777,))
        self.assertTrue(result.clean_close)

    def test_truncated_final_record_is_ignored_and_reported(self):
        records = (
            MetaRecord(0x0003, 1, 0, 1, 100, b""),
            MetaRecord(0x0004, 1, 0, 2, 200, struct.pack("<H", 0)),
        )
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "SESSION.META"
            write_meta(path, self.header, records)
            raw = path.read_bytes()
            path.write_bytes(raw[:-5])
            result = read_meta(path)
        self.assertEqual(result.records, records[:1])
        self.assertGreater(result.recovery.truncated_tail_bytes, 0)
        self.assertFalse(result.clean_close)

    def test_crc_error_resynchronizes_at_next_valid_record(self):
        a = encode_record(MetaRecord(0x0003, 1, 0, 1, 100, b""))
        bad = bytearray(encode_record(MetaRecord(0x0011, 0, 0, 2, 150, struct.pack("<HHI", 2, 0, 42))))
        bad[21] ^= 0x80
        c = encode_record(MetaRecord(0x0004, 1, 0, 3, 200, struct.pack("<H", 0)))
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "SESSION.META"
            write_meta(path, self.header, [])
            path.write_bytes(path.read_bytes() + a + bytes(bad) + c)
            result = read_meta(path)
        self.assertEqual([r.sequence for r in result.records], [1, 3])
        self.assertEqual(len(result.recovery.crc_error_offsets), 1)
        self.assertEqual(result.recovery.resynchronized_records, 1)
        self.assertEqual(result.recovery.sequence_gaps, ((1, 3),))

    def test_bad_header_crc_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "SESSION.META"
            write_meta(path, self.header, [])
            raw = bytearray(path.read_bytes())
            raw[8] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "header CRC"):
                read_meta(path)

    def test_string_over_255_bytes_is_rejected_by_session_start_decoder(self):
        payload = struct.pack("<H", 256) + b"a" * 256
        rec = MetaRecord(0x0001, 0, 0, 1, 0, payload)
        with self.assertRaises(ValueError):
            decode_record_payload(rec)

    def test_defined_payload_decoders(self):
        cases = [
            (0x0001, 0, lp("logger") + lp("2.6") + lp("E32R35T_TOUCH") + lp("abc") + lp("db"), "logger_name", "logger"),
            (0x0002, 1, struct.pack("<BBBBBBHI", 1, 1, 1, 0, 3, 0, 0, 500000), "nominal_rate", 500000),
            (0x0003, 1, b"", "stream_start", True),
            (0x0004, 1, struct.pack("<H", 3), "reason_code", 3),
            (0x0005, 1, struct.pack("<H", 2) + lp("RAW_002.TCB"), "filename", "RAW_002.TCB"),
            (0x0006, 1, struct.pack("<HHQQ", 2, 0, 100, 2400), "records_persisted", 100),
            (0x0010, 0, struct.pack("<HBBQ", 9, 0, 0, 1234), "esp_send_us", 1234),
            (0x0011, 0, struct.pack("<HHI", 9, 0, 44), "marker", 44),
            (0x0020, 0, struct.pack("<HHHHQ", 1, 1, 9, 1, 321), "metrics", ((9, 1, 321),)),
            (0x0021, 1, struct.pack("<QQQQQII", 10, 1, 11, 2, 3, 4, 5), "queue_high_water", 4),
            (0x0022, 0, struct.pack("<HHHHQ", 1, 1, 4, 0, 2), "metrics", ((4, 0, 2),)),
            (0x0030, 1, struct.pack("<HBBHHq", 6, 1, 1, 3, 0, 0x7E0), "event_code", 6),
            (0x0031, 1, struct.pack("<HHII", 6, 0, 1, 2), "state_code", 6),
            (0x0032, 1, struct.pack("<HHII", 3, 0, 1, 2), "state_code", 3),
            (0x00FE, 0, struct.pack("<HBBHH", 0, 1, 0, 1, 0), "clean", 1),
        ]
        for record_type, stream_id, payload, key, expected in cases:
            with self.subTest(record_type=record_type):
                decoded = decode_record_payload(MetaRecord(record_type, stream_id, 0, 1, 1, payload))
                self.assertEqual(decoded[key], expected)


if __name__ == "__main__":
    unittest.main()
