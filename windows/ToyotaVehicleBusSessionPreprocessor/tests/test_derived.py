from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session.derived import LegacyDecodedProjector, write_legacy_decoded
from toyota_vehicle_bus_session.meta import MetaHeader, MetaRecord, write_meta
from toyota_vehicle_bus_session.native import load_native_session

TCB_HEADER = b"TCB1" + bytes([1, 24]) + b"\0" * 10
TCB_RECORD = struct.Struct("<QI8sBBBB")


@dataclass(frozen=True)
class Tx:
    complete_time_us: int
    service: int
    pid: int | None
    payload: bytes
    status: str = "OK"


def be16(value: int) -> bytes:
    return int(value).to_bytes(2, "big")


def event_profile(profile: int, confidence: int, sequence: int = 3) -> MetaRecord:
    payload = struct.pack("<HBB", 17, 0, 2)
    payload += struct.pack("<HHq", 5, 0, profile)
    payload += struct.pack("<HHq", 6, 0, confidence)
    return MetaRecord(0x30, 0, 0, sequence, 1, payload)


def tcb_record(time_us: int, can_id: int, data: bytes, direction: int = 0) -> bytes:
    padded = data + b"\0" * (8 - len(data))
    return TCB_RECORD.pack(time_us, can_id, padded, len(data), 0, 0, direction)


class DerivedProjectionTests(unittest.TestCase):
    def test_gen2_confirmed_diagnostic_projection(self) -> None:
        projector = LegacyDecodedProjector("PRIUS GEN 2", 85)

        ce = bytearray(31)
        ce[0] = 120  # 60% SOC
        ce[1:3] = be16(32768)  # 0 A
        for index in range(14):
            ce[3 + index * 2:5 + index * 2] = be16(34348)  # 15.80 V
        projector.observe_transaction(Tx(100_000, 0x21, 0xCE, b"\x61\xCE" + bytes(ce)))

        c3 = bytearray(28)
        c3[14:16] = be16(1500)
        c3[24:28] = bytes([70, 71, 72, 73])
        projector.observe_transaction(Tx(110_000, 0x21, 0xC3, b"\x61\xC3" + bytes(c3)))

        cf = bytearray(16)
        cf[0:2] = be16(35000)
        cf[3] = 197
        cf[6] = 25
        cf[8] = 3
        cf[10:12] = be16(35000)
        cf[12:14] = be16(35100)
        cf[14:16] = be16(35200)
        projector.observe_transaction(Tx(120_000, 0x21, 0xCF, b"\x61\xCF" + bytes(cf)))

        row = projector.row(150_000)
        self.assertAlmostEqual(float(row["SOC_pct"]), 60.0, places=2)
        self.assertAlmostEqual(float(row["Pack_V"]), 221.2, places=2)
        self.assertAlmostEqual(float(row["Pack_A"]), 0.0, places=2)
        self.assertEqual(row["Engine_RPM"], "1500")
        self.assertAlmostEqual(float(row["MG1_Inv_F"]), 68.0, places=1)
        self.assertAlmostEqual(float(row["B01_V"]), 15.8, places=2)
        self.assertEqual(row["Fan_Level"], "3")
        self.assertEqual(row["DataQuality"], "GEN2_DIAG_CONFIRMED")

    def test_gen2_passive_soc_and_freshness(self) -> None:
        projector = LegacyDecodedProjector("PRIUS GEN 2", 80)
        projector.observe_passive(100_000, 0x3CB, bytes([0, 0, 0, 100, 0, 0, 0]))
        self.assertEqual(projector.row(200_000)["SOC_pct"], "50.00")
        self.assertEqual(projector.row(200_000)["DataQuality"], "PASSIVE_SOC_CONFIRMED")
        self.assertEqual(projector.row(2_200_001)["SOC_pct"], "")

    def test_phv_projection_uses_confirmed_pack_temperature_and_power_fields(self) -> None:
        projector = LegacyDecodedProjector("PRIUS PHV G1", 100)

        d01 = bytearray(22)
        d01[2] = 50
        d01[5] = 70
        d01[6:8] = be16(4000)
        d01[21] = 65
        projector.observe_transaction(Tx(100_000, 0x21, 0x01, b"\x61\x01" + bytes(d01)))

        d81 = bytearray(22)
        for index in range(8):
            d81[index * 2:index * 2 + 2] = be16(20500)
        d81[16:18] = be16(44000)
        d81[18:20] = be16(2010)
        projector.observe_transaction(Tx(110_000, 0x21, 0x81, b"\x61\x81" + bytes(d81)))

        d98 = bytearray(8)
        d98[0:2] = be16(32912)  # +1.44 A
        d98[4] = 10
        projector.observe_transaction(Tx(120_000, 0x21, 0x98, b"\x61\x98" + bytes(d98)))

        d87 = bytearray(32)
        for pos in range(0, 32, 2):
            d87[pos:pos + 2] = be16(32000)
        projector.observe_transaction(Tx(130_000, 0x21, 0x87, b"\x61\x87" + bytes(d87)))

        row = projector.row(150_000)
        self.assertAlmostEqual(float(row["SOC_pct"]), 65 * 20 / 51, places=2)
        self.assertAlmostEqual(float(row["Pack_V"]), 201.0, places=2)
        self.assertAlmostEqual(float(row["Pack_A"]), 1.44, places=2)
        self.assertAlmostEqual(float(row["Pack_kW"]), 201.0 * 1.44 / 1000.0, places=3)
        self.assertEqual(row["Engine_RPM"], "1000")
        self.assertNotEqual(row["HV_T1_F"], "")
        self.assertNotEqual(row["B01_V"], "")
        self.assertEqual(row["B09_V"], "0.00")
        self.assertEqual(row["DataQuality"], "PHV_DIAG_CONFIRMED")

    def test_write_legacy_decoded_samples_on_deterministic_100ms_grid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "S0166"
            root.mkdir()
            start_payload = b"".join(
                struct.pack("<H", len(value)) + value
                for value in (b"Logger", b"2.6", b"E32R35T_TOUCH", b"build", b"db")
            )
            records = [
                MetaRecord(1, 0, 0, 1, 50_000, start_payload),
                MetaRecord(2, 1, 0, 2, 50_000, struct.pack("<BBBBBBHI", 1, 1, 1, 0, 3, 0, 0, 500000)),
                event_profile(1, 85),
                MetaRecord(0xFE, 0, 0, 4, 350_000, struct.pack("<HBBHH", 0, 1, 0, 1, 0)),
            ]
            write_meta(root / "SESSION.META", MetaHeader(1, 0, 166, 0, 50_000), records)
            raw = TCB_HEADER
            raw += tcb_record(50_000, 0x100, b"\0")
            raw += tcb_record(90_000, 0x3CB, bytes([0, 0, 0, 100, 0, 0, 0]))
            raw += tcb_record(250_000, 0x100, b"\0")
            raw += tcb_record(350_000, 0x100, b"\0")
            (root / "RAW_000.TCB").write_bytes(raw)
            session = load_native_session(root)
            output = Path(td) / "DECODED.CSV"
            rows = write_legacy_decoded(session, output)
            with output.open(newline="", encoding="utf-8") as handle:
                decoded = list(csv.DictReader(handle))

        self.assertEqual(rows, 3)
        self.assertEqual([row["Time_ms"] for row in decoded], ["100", "200", "300"])
        self.assertEqual([row["SOC_pct"] for row in decoded], ["50.00", "50.00", "50.00"])
        self.assertTrue(all(row["Profile"] == "PRIUS GEN 2" for row in decoded))
        self.assertTrue(all(row["ProfileConfidence"] == "85" for row in decoded))


if __name__ == "__main__":
    unittest.main()
