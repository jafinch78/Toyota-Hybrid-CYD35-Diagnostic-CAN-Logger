import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from toyota_can_processor.graph_ocr import (Word, extract_battery_graph,
                                            parse_dr_prius_block_tsv,
                                            prepare_dr_prius_block_strip,
                                            prepare_ocr_image)


class GraphOcrTests(unittest.TestCase):
    def test_rotated_phone_band_is_cropped_without_timestamp_rule(self):
        image = Image.new("RGB", (1000, 2200), "black")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 800, 999, 1350), fill=(45, 45, 45))
        draw.text((40, 840), "Battery Monitor", fill="white")
        prepared, mode = prepare_ocr_image(image)
        self.assertEqual(mode, "LANDSCAPE_BAND")
        self.assertGreater(prepared.width / prepared.height, 1.25)

    def test_geometry_axis_and_ordered_blocks(self):
        image = Image.new("RGB", (1000, 1000), "black")
        draw = ImageDraw.Draw(image)
        words = []
        for index, y in enumerate(range(100, 701, 60)):
            value = 16.0 - y * 0.001
            draw.line((150, y, 900, y), fill=(210, 210, 210), width=2)
            words.append(Word(f"{value:.2f}", 95.0, 55, y - 10, 70, 20))
        for index in range(17):
            x0 = 170 + index * 42
            top = 240 + (index % 5) * 25
            draw.rectangle((x0, top, x0 + 20, 700), fill=(10, 240, 220))
        words.extend([
            Word("Avg=15.70", 95.0, 350, 740, 120, 25),
            Word("Diff=0.10", 95.0, 500, 740, 120, 25),
            Word("Camry", 95.0, 450, 900, 80, 25),
            Word("SOC", 95.0, 200, 820, 60, 25),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            row = extract_battery_graph(image, words, 12.0, "AUTO",
                                        "CAMRY_HYBRID_GEN1", 17, "synthetic.png",
                                        Path(temporary))
        self.assertIsNotNone(row)
        self.assertEqual(row["BlockCount"], 17)
        self.assertEqual(row["Layout"], "HYBRID_ASSISTANT_BATTERY_CHECK")
        self.assertGreater(float(row["Confidence"]), 0.70)

    def test_dr_prius_landscape_printed_block_values(self):
        image = Image.new("RGB", (1700, 700), (28, 28, 28))
        draw = ImageDraw.Draw(image)
        words = [
            Word("Battery", 95.0, 40, 30, 100, 25),
            Word("Monitor", 95.0, 150, 30, 100, 25),
            Word("Battery", 95.0, 600, 250, 90, 20),
            Word("block", 95.0, 700, 250, 70, 20),
            Word("voltage", 95.0, 780, 250, 90, 20),
        ]
        values = [16.27, 16.32, 16.29, 16.37, 16.37, 16.32, 16.32, 16.38,
                  16.29, 16.32, 16.34, 16.27, 16.37, 16.32, 16.32, 16.37, 16.24]
        for index, value in enumerate(values):
            left = index * 100 + 12
            top = 300 + int((16.40 - value) * 500)
            draw.rectangle((left, top, left + 74, 500), fill=(0, 210, 35))
            words.append(Word(f"{value:.2f}", 95.0, left + 8, 455, 58, 20))
        with tempfile.TemporaryDirectory() as temporary:
            row = extract_battery_graph(image, words, 330.0, "AUTO",
                                        "CAMRY_HYBRID_GEN1", 17, "frame.png",
                                        Path(temporary))
        self.assertIsNotNone(row)
        self.assertEqual(row["App"], "DR_PRIUS")
        self.assertEqual(row["BlockCount"], 17)
        self.assertEqual(row["ExtractedBlockCount"], 17)
        self.assertEqual(row["ReconstructedBlockCount"], 0)
        self.assertAlmostEqual(float(row["GraphPackSum_V"]), 277.48, places=2)
        self.assertAlmostEqual(float(row["GraphDifference_V"]), 0.14, places=2)

    def test_dr_prius_block_tsv_preserves_empty_cell_positions(self):
        header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
        rows = [header,
                "5\t1\t1\t1\t1\t1\t20\t20\t100\t30\t95\t16.27",
                "5\t1\t2\t1\t1\t1\t20\t540\t100\t30\t95\t16.29"]
        values = parse_dr_prius_block_tsv("\n".join(rows), 3, 260)
        self.assertEqual(values, [16.27, None, 16.29])

    def test_dr_prius_strip_detects_primary_green_chart(self):
        image = Image.new("RGB", (1700, 700), (28, 28, 28))
        draw = ImageDraw.Draw(image)
        for index in range(17):
            left = 32 + index * 96
            draw.rectangle((left, 330 + index % 4 * 8, left + 72, 470), fill=(0, 220, 20))
            draw.rectangle((left, 560, left + 72, 570), fill=(0, 220, 20))
        prepared = prepare_dr_prius_block_strip(image, 17)
        self.assertIsNotNone(prepared)
        strip, metadata = prepared
        self.assertEqual(strip.height, 17 * metadata["slot_height"])

    def test_dr_prius_rejects_values_that_do_not_reconcile_to_printed_pack(self):
        image = Image.new("RGB", (1700, 700), (28, 28, 28))
        draw = ImageDraw.Draw(image)
        words = [Word("Battery", 95.0, 40, 30, 100, 25),
                 Word("Monitor", 95.0, 150, 30, 100, 25),
                 Word("277.48", 95.0, 80, 120, 120, 25),
                 Word("8.16", 95.0, 430, 120, 80, 25),
                 Word("3.27", 95.0, 780, 120, 80, 25),
                 Word("49.50", 95.0, 1120, 120, 100, 25),
                 Word("0.00", 95.0, 1460, 120, 80, 25)]
        values = [16.30] * 16 + [14.30]
        for index, value in enumerate(values):
            left = index * 100 + 12
            draw.rectangle((left, 300, left + 74, 500), fill=(0, 210, 35))
            words.append(Word(f"{value:.2f}", 95.0, left + 8, 455, 58, 20))
        row = extract_battery_graph(image, words, 250.0, "AUTO",
                                    "CAMRY_HYBRID_GEN1", 17, "frame.png")
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
