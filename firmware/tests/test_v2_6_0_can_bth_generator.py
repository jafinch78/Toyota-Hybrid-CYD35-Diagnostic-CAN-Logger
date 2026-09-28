from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "tools" / "build_can_bth_v2_6_0_firmware.py"
RC2_DIR = ROOT / ".ci_rc2" / "firmware" / "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0"


class CanBthV260GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GENERATOR.exists():
            raise AssertionError("CAN+BTH v2.6 generator does not exist yet")
        spec = importlib.util.spec_from_file_location("canbthgen", GENERATOR)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        cls.module = module
        cls.temp = tempfile.TemporaryDirectory()
        cls.out_root = Path(cls.temp.name)
        module.generate(RC2_DIR, cls.out_root)
        cls.sketch_dir = cls.out_root / "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0"
        cls.source = (cls.sketch_dir / "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0.ino").read_text(encoding="utf-8")
        cls.bth_h = (cls.sketch_dir / "BTH1Raw.h").read_text(encoding="utf-8")
        cls.readme = (cls.sketch_dir / "README.md").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_can_queue_is_768_and_existing_can_contract_stays_intact(self):
        self.assertIn("static_assert(sizeof(CapturedFrame) == 24", self.source)
        self.assertIn("#define CAN_TX_PIN GPIO_NUM_25", self.source)
        self.assertIn("#define CAN_RX_PIN GPIO_NUM_32", self.source)
        self.assertIn("CAN_BITRATE = 500000", self.source)
        self.assertIn("CAN_QUEUE_LENGTH = 768", self.source)
        self.assertIn("CAN_BATCH_LENGTH = 128", self.source)

    def test_bth_is_uart2_rx_only_on_gpio35_at_19200_8o1(self):
        self.assertIn("BTH_RX_PIN GPIO_NUM_35", self.source)
        self.assertIn("UART_NUM_2", self.source)
        self.assertIn("BTH_BAUD = 19200", self.source)
        self.assertIn("UART_DATA_8_BITS", self.source)
        self.assertIn("UART_PARITY_ODD", self.source)
        self.assertIn("UART_STOP_BITS_1", self.source)
        self.assertIn("UART_PIN_NO_CHANGE", self.source)
        self.assertNotIn("BTH_TX_PIN", self.source)
        self.assertNotIn("GPIO_NUM_39", self.source)

    def test_bth_rx_inversion_is_configurable_without_transmit_support(self):
        self.assertIn("BTH_RX_INVERT", self.source)
        self.assertIn("UART_SIGNAL_RXD_INV", self.source)
        for forbidden in ("uart_write_bytes", "uart_tx_chars", "BTH transmit", "BTH TX"):
            self.assertNotIn(forbidden, self.source)

    def test_bth1_raw_contract_is_explicit_and_crc_protected(self):
        self.assertIn("BTH1_MAGIC", self.bth_h)
        self.assertIn("0xB7B1", self.bth_h)
        self.assertIn("BTH1_HEADER_SIZE = 32", self.bth_h)
        self.assertIn("BTH1_MAX_PAYLOAD = 64", self.bth_h)
        self.assertIn("0xEDB88320", self.bth_h)
        self.assertIn("BTH1_STATUS_PARITY", self.bth_h)
        self.assertIn("BTH1_STATUS_FRAME", self.bth_h)
        self.assertIn("BTH1_STATUS_FIFO_OVERFLOW", self.bth_h)
        self.assertIn("BTH1_STATUS_BUFFER_FULL", self.bth_h)

    def test_bth_runtime_buffers_are_bounded_and_nonallocating_in_event_task(self):
        self.assertIn("BTH_QUEUE_LENGTH = 32", self.source)
        self.assertIn("BTH_UART_RX_BUFFER_BYTES = 1024", self.source)
        self.assertIn("BTH_UART_EVENT_QUEUE_LENGTH = 16", self.source)
        self.assertIn("struct BthChunk", self.source)
        self.assertIn("xQueueCreate(BTH_QUEUE_LENGTH, sizeof(BthChunk))", self.source)
        self.assertIn("void bthRxTask(void *parameter)", self.source)
        task = self.source.split("void bthRxTask(void *parameter)", 1)[1].split("void ", 1)[0]
        self.assertNotIn("String(", task)
        self.assertNotIn("SD.", task)
        self.assertNotIn("tft.", task)

    def test_bth_and_can_are_separate_tvm1_streams(self):
        self.assertIn("TVM1_STREAM_CAN = 1", self.source + self.bth_h)
        self.assertIn("TVM1_STREAM_BTH = 2", self.source + self.bth_h)
        self.assertIn("TVM1_STREAM_TYPE_BTH", self.source)
        self.assertIn("TVM1_RAW_FORMAT_BTH1", self.source)
        self.assertIn("emitBthStreamRegister", self.source)
        self.assertIn("BTH_000.BTH", self.source)
        self.assertIn("registered_stream_count", self.readme)

    def test_main_loop_persists_can_before_bth_and_bth_before_noncritical_work(self):
        loop = self.source.split("void loop()", 1)[1]
        can_pos = loop.index("writeRawBatch(batch, count)")
        bth_pos = loop.index("serviceBthPersistence()")
        meta_pos = loop.index("serviceMetaQueue()")
        display_pos = loop.index("updateDisplay()")
        self.assertLess(can_pos, bth_pos)
        self.assertLess(bth_pos, meta_pos)
        self.assertLess(meta_pos, display_pos)

    def test_no_page_button_and_wifi_is_retained(self):
        self.assertNotIn("CYD_PAGE_BTN", self.source)
        self.assertNotIn('"PAGE"', self.source)
        self.assertIn("CYD_WIFI_BTN", self.source)
        self.assertIn("WiFi.softAP(", self.source)
        self.assertIn("BTH_", self.source)
        self.assertIn("SESSION.META", self.source)

    def test_display_prioritizes_integrity_metrics_not_vehicle_dashboard_pages(self):
        for required in ("CAN RX", "CAN Q", "BTH RX", "BTH Q", "SD", "BLE", "DIAG"):
            self.assertIn(required, self.source)
        for forbidden in ("LIVE TEMPERATURES", "BLOCKS", "TREND", "HEALTH PAGE", "POWER PAGE"):
            self.assertNotIn(forbidden, self.source)

    def test_bth_counters_include_loss_and_uart_errors(self):
        for field in (
            "bthRxBytes", "bthPersistedBytes", "bthQueueDrops", "bthQueueHighWater",
            "bthFifoOverflow", "bthBufferFull", "bthParityErrors", "bthFrameErrors", "bthBreakErrors",
        ):
            self.assertIn(field, self.source)


if __name__ == "__main__":
    unittest.main()
