from __future__ import annotations

import io
import re
import struct
import unittest
import zipfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKETCH = ROOT / "firmware" / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0" / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0.ino"
SOURCE = SKETCH.read_text(encoding="utf-8")


def crc32_like_firmware(crc: int, data: bytes) -> int:
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1) & 0xFFFFFFFF))
    return crc & 0xFFFFFFFF


def make_reference_stored_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    central: list[tuple[bytes, int, int, int]] = []
    for name, data in files.items():
        encoded = name.encode("ascii")
        offset = output.tell()
        output.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 8, 0, 0, 0, 0, 0, 0, len(encoded), 0))
        output.write(encoded)
        output.write(data)
        crc = crc32_like_firmware(0xFFFFFFFF, data) ^ 0xFFFFFFFF
        output.write(struct.pack("<IIII", 0x08074B50, crc, len(data), len(data)))
        central.append((encoded, crc, len(data), offset))

    central_offset = output.tell()
    for name, crc, size, offset in central:
        output.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 8, 0, 0, 0,
                                 crc, size, size, len(name), 0, 0, 0, 0, 0, offset))
        output.write(name)
    central_size = output.tell() - central_offset
    output.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central),
                             central_size, central_offset, 0))
    return output.getvalue()


class FirmwareSourceTests(unittest.TestCase):
    def test_capture_and_pin_contract_is_unchanged(self):
        self.assertIn("static_assert(sizeof(CapturedFrame) == 24", SOURCE)
        self.assertIn('\\"format_version\\": \\"1.4\\"', SOURCE)
        self.assertIn("#define CAN_TX_PIN GPIO_NUM_25", SOURCE)
        self.assertIn("#define CAN_RX_PIN GPIO_NUM_32", SOURCE)
        self.assertIn("#define CYD_BOARD_DORHEA_B0DLNJSSFW 1", SOURCE)
        self.assertIn("{295, 3524, 310, 3487, 3}", SOURCE)
        self.assertIn("{295, 3524, 310, 3487, 7}", SOURCE)
        self.assertIn("digitalWrite(4, HIGH);", SOURCE)
        self.assertEqual(SOURCE.count('\\"touch_calibration\\":'), 1)

    def test_diagnostic_table_remains_read_only(self):
        table = SOURCE.split("const DiagnosticRequest DIAGNOSTIC_REQUESTS[]", 1)[1].split("// ------------------------------- Global state", 1)[0]
        services = {int(value, 16) for value in re.findall(r"\{0x[0-9A-F]+,\s*0x([0-9A-F]+),", table)}
        self.assertEqual(services, {0x01, 0x21})
        for forbidden in ("0x2E", "SD.format", "HTTP_PUT", "HTTP_PATCH", "handleWifiCan"):
            self.assertNotIn(forbidden, SOURCE)

    def test_wifi_is_exclusive_and_restart_only(self):
        shutdown = SOURCE.index("void shutdownLoggerServicesForWifi()")
        start = SOURCE.index("bool startWifiFileMode()")
        ap = SOURCE.index("WiFi.softAP(", start)
        self.assertLess(SOURCE.index("twai_driver_uninstall();", shutdown), ap)
        self.assertLess(SOURCE.index("BLEDevice::deinit(true);", shutdown), ap)
        self.assertIn("if (loggingActive || !sdReady) return false;", SOURCE[start:ap])
        self.assertIn("ESP.restart();", SOURCE)

    def test_http_surface_is_files_only(self):
        expected = {
            "/api/v1/info", "/api/v1/sessions", "/api/v1/files",
            "/api/v1/file", "/api/v1/canlog.zip", "/api/v1/session.zip",
            "/api/v1/delete",
        }
        routes = set(re.findall(r'wifiServer->on\("([^\"]+)"', SOURCE))
        self.assertTrue(expected.issubset(routes))
        self.assertIn('wifiServer->arg("token") != wifiDeleteToken', SOURCE)
        self.assertIn('SD.exists(openMarker.c_str())', SOURCE)
        self.assertIn("Download CANLOG ZIP", SOURCE)
        self.assertIn('"CANLOG/%s/%s"', SOURCE)
        self.assertIn('filename=\\"CANLOG_%s.zip\\"', SOURCE)

    def test_allocator_has_all_recovery_inputs(self):
        for text in ("scanHighestSessionNumber()", "NEXT_SESSION.TXT", "NEXT_SESSION.NEW",
                     'SESSION_NVS_KEY[] = "nextsess"', "reserveSessionNumber(candidate)",
                     '\\"session_allocator_policy\\": \\"MONOTONIC_V1\\"'):
            self.assertIn(text, SOURCE)

    def test_crc_and_zip_layout_extract(self):
        data = bytes(range(251)) * 17
        self.assertEqual(crc32_like_firmware(0xFFFFFFFF, data) ^ 0xFFFFFFFF, zlib.crc32(data))
        files = {
            "S0012/RAW_000.TCB": b"TCB1" + data,
            "S0012/MANIFEST.JSON": b'{"firmware_version":"2.5.0-rc.2"}\n',
        }
        archive = make_reference_stored_zip(files)
        with zipfile.ZipFile(io.BytesIO(archive)) as loaded:
            self.assertIsNone(loaded.testzip())
            self.assertEqual({name: loaded.read(name) for name in loaded.namelist()}, files)


if __name__ == "__main__":
    unittest.main()
