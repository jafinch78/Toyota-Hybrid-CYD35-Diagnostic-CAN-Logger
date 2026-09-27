import unittest

from toyota_vehicle_bus_session.isotp import IsoTpAssembler


class IsoTpTests(unittest.TestCase):
    def test_single_frame(self):
        assembler = IsoTpAssembler()
        result = assembler.feed(100, 0x7E8, bytes([3, 0x41, 0x0C, 0x12, 0, 0, 0, 0]), 8)
        self.assertEqual((result.status, result.payload, result.frame_count), ("OK", bytes([0x41, 0x0C, 0x12]), 1))

    def test_first_and_consecutive_frames_and_sequence_wrap(self):
        payload = bytes(range(1, 22))
        assembler = IsoTpAssembler()
        self.assertIsNone(assembler.feed(1, 0x7E8, bytes([0x10, len(payload)]) + payload[:6], 8))
        self.assertIsNone(assembler.feed(2, 0x7E8, bytes([0x21]) + payload[6:13], 8))
        self.assertIsNone(assembler.feed(3, 0x7E8, bytes([0x22]) + payload[13:20], 8))
        result = assembler.feed(4, 0x7E8, bytes([0x23]) + payload[20:] + b"\0" * 6, 8)
        self.assertEqual(result.payload, payload)

        long_payload = bytes(i % 256 for i in range(120))
        assembler = IsoTpAssembler()
        assembler.feed(10, 0x7E8, bytes([0x10, len(long_payload)]) + long_payload[:6], 8)
        position = 6
        sequence = 1
        result = None
        while position < len(long_payload):
            chunk = long_payload[position : position + 7]
            result = assembler.feed(
                10 + position,
                0x7E8,
                bytes([0x20 | sequence]) + chunk + b"\0" * (7 - len(chunk)),
                8,
            )
            position += len(chunk)
            sequence = (sequence + 1) & 0x0F
        self.assertEqual(result.payload, long_payload)

    def test_missing_sequence(self):
        assembler = IsoTpAssembler()
        assembler.feed(1, 0x7E8, bytes([0x10, 12]) + b"abcdef", 8)
        result = assembler.feed(2, 0x7E8, bytes([0x22]) + b"ghijklm", 8)
        self.assertEqual(result.status, "INCOMPLETE_SEQUENCE")

    def test_negative_response(self):
        assembler = IsoTpAssembler()
        result = assembler.feed(1, 0x7E8, bytes([3, 0x7F, 0x21, 0x12, 0, 0, 0, 0]), 8)
        self.assertEqual(result.status, "NEGATIVE_RESPONSE")


if __name__ == "__main__":
    unittest.main()
