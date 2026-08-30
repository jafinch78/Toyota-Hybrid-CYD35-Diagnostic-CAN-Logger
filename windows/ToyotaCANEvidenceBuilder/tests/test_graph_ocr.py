import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from toyota_can_processor.graph_ocr import Word, extract_battery_graph


class GraphOcrTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
