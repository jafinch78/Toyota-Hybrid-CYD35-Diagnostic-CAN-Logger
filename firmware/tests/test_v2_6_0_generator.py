from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tools" / "generate_v2_6_0_firmware.py"
RC2_DIR = ROOT / ".ci_rc2" / "firmware" / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0"


class V260GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GENERATOR.exists():
            raise AssertionError("v2.6 generator does not exist yet")
        spec = importlib.util.spec_from_file_location("v260gen", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        cls.module = module
        cls.temp = tempfile.TemporaryDirectory()
        cls.out_root = Path(cls.temp.name)
        module.generate(RC2_DIR, cls.out_root)
        cls.sketch_dir = cls.out_root / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0"
        cls.source = (cls.sketch_dir / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino").read_text(encoding="utf-8")
        cls.meta_h = (cls.sketch_dir / "TVM1Meta.h").read_text(encoding="utf-8")
        cls.setup_h = (cls.sketch_dir / "TFT_eSPI_User_Setup_CYD35.h").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def function_body(self, signature: str) -> str:
        start = self.source.index(signature)
        open_brace = self.source.index("{", start)
        depth = 0
        in_string = None
        escape = False
        line_comment = False
        block_comment = False
        i = open_brace
        while i < len(self.source):
            c = self.source[i]
            n = self.source[i + 1] if i + 1 < len(self.source) else ""
            if line_comment:
                if c == "\n": line_comment = False
                i += 1; continue
            if block_comment:
                if c == "*" and n == "/": block_comment = False; i += 2; continue
                i += 1; continue
            if in_string:
                if escape: escape = False
                elif c == "\\": escape = True
                elif c == in_string: in_string = None
                i += 1; continue
            if c == "/" and n == "/": line_comment = True; i += 2; continue
            if c == "/" and n == "*": block_comment = True; i += 2; continue
            if c in ('"', "'"): in_string = c; i += 1; continue
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return self.source[open_brace + 1:i]
            i += 1
        self.fail(f"unterminated function {signature}")

    def test_exact_capture_contract_is_preserved(self):
        self.assertIn("static_assert(sizeof(CapturedFrame) == 24", self.source)
        self.assertIn("#define CAN_TX_PIN GPIO_NUM_25", self.source)
        self.assertIn("#define CAN_RX_PIN GPIO_NUM_32", self.source)
        self.assertRegex(self.source, r"CAN_BITRATE\s*=\s*500000")
        self.assertIn("25UL * 1024UL * 1024UL", self.source)
        self.assertRegex(self.source, r"CAN_QUEUE_LENGTH\s*=\s*1024")

    def test_only_e32r35t_and_dorhea_are_active_targets(self):
        self.assertIn("E32R35T_TOUCH", self.source)
        self.assertIn("DORHEA_B0DLNJSSFW_TOUCH", self.source)
        self.assertNotIn("E32N35T", self.source)
        self.assertIn("#define SPI_FREQUENCY  80000000", self.setup_h)

    def test_read_only_diagnostic_whitelist_is_unchanged(self):
        table = self.source.split("const DiagnosticRequest DIAGNOSTIC_REQUESTS[]", 1)[1].split("// ------------------------------- Global state", 1)[0]
        services = {int(x, 16) for x in re.findall(r"\{0x[0-9A-F]+,\s*0x([0-9A-F]+),", table)}
        self.assertEqual(services, {0x01, 0x21})
        for forbidden in ("0x2E", "SD.format", "HTTP_PUT", "HTTP_PATCH", "handleWifiCan"):
            self.assertNotIn(forbidden, self.source)

    def test_native_session_is_raw_plus_tvm1_only(self):
        self.assertIn("File rawFile;", self.source)
        self.assertIn("File metaFile;", self.source)
        for forbidden in (
            "File decodedFile;", "File diagnosticFile;", "File eventFile;",
            "File syncFile;", "File externalDiagnosticFile;", "DECODED.CSV",
            "DIAGNOSTICS.CSV", "EXTERNAL_DIAGNOSTICS.CSV", "EVENTS.CSV",
            "SYNC.CSV", "SIGNALS.CSV", "README.TXT", "MANIFEST.JSON",
            "CHECKPOINT.JSON", "PLOT.CSV",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('"SESSION.META"', self.source)
        self.assertNotIn("SESSION.OPEN", self.function_body("bool startLogging()"))
        self.assertRegex(self.source, r"SD_MAX_OPEN_FILES\s*=\s*5")

    def test_tvm1_contract_constants_exist(self):
        self.assertIn('TVM1_MAGIC[4] = {\'T\', \'V\', \'M\', \'1\'}', self.meta_h)
        self.assertIn("TVM1_RECORD_SYNC = 0xA55A", self.meta_h)
        self.assertIn("TVM1_HEADER_SIZE = 32", self.meta_h)
        self.assertIn("TVM1_MAX_RECORD_SIZE = 4096", self.meta_h)
        self.assertIn("0xEDB88320", self.meta_h)
        self.assertNotIn("TCM1", self.meta_h + self.source)
        for record_id in ("0x0001", "0x0002", "0x0003", "0x0004", "0x0005", "0x0006", "0x0010", "0x0011", "0x0020", "0x0021", "0x0022", "0x0030", "0x0031", "0x0032", "0x00FE"):
            self.assertIn(record_id, self.meta_h)

    def test_raw_is_committed_before_derived_processing(self):
        body = self.function_body("void loop()")
        self.assertLess(body.index("writeRawBatch(batch, count)"), body.index("processCapturedFrame(batch[i])"))
        self.assertLess(body.index("writeRawBatch(batch, count)"), body.index("serviceMetaQueue()"))

    def test_stop_is_pending_until_after_raw_drain(self):
        self.assertIn("stopPending", self.source)
        stop_body = self.function_body("void stopLogging(bool closedCleanly)")
        self.assertIn("stopPending = true", stop_body)
        loop_body = self.function_body("void loop()")
        self.assertLess(loop_body.index("writeRawBatch(batch, count)"), loop_body.index("finalizePendingStop()"))

    def test_external_tester_is_hard_interlocked(self):
        tx = self.function_body("bool transmitCAN(")
        scheduler = self.function_body("void serviceDiagnosticScheduler()")
        self.assertIn("externalTesterInterlockActive()", tx)
        self.assertIn("externalTesterInterlockActive()", scheduler)
        self.assertIn("EXTERNAL_TESTER_HOLD_MS = 5000", self.source)

    def test_display_does_not_periodically_clear_full_content_area(self):
        update = self.function_body("void updateDisplay()")
        self.assertNotIn("fillRect(2, 2, 476, 241", update)
        self.assertIn("drawDirtyField", self.source)
        self.assertIn("displayPageChanged", self.source)

    def test_wifi_remains_exclusive_and_restart_only(self):
        shutdown = self.source.index("void shutdownLoggerServicesForWifi()")
        start = self.source.index("bool startWifiFileMode()")
        ap = self.source.index("WiFi.softAP(", start)
        self.assertLess(self.source.index("twai_driver_uninstall();", shutdown), ap)
        self.assertLess(self.source.index("BLEDevice::deinit(true);", shutdown), ap)
        self.assertIn("ESP.restart();", self.source)
        self.assertIn("isNativeTvm1SessionClean", self.source)
        self.assertIn("SESSION.OPEN", self.source)  # legacy sessions remain supported


if __name__ == "__main__":
    unittest.main()
