from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageOps


MAX_BLOCKS = 40
GRAPH_FIELDS = [
    "Video_s", "App", "Layout", "VehicleProfile", "BlockCount",
    "ExtractedBlockCount", "ReconstructedBlockCount", "ReconstructedBlocks",
    "ExtractionMethod", "EvidenceGrade",
    *[f"B{index:02d}_V" for index in range(1, MAX_BLOCKS + 1)],
    "GraphPackSum_V", "GraphAverage_V", "GraphMinimum_V", "GraphMaximum_V", "GraphDifference_V",
    "PrintedPackVoltage_V", "BladeVoltage_V", "PrintedAverage_V", "PrintedDifference_V",
    "PrintedVoltageDifference_V", "StartSOC_pct", "ActualSOC_pct", "CurrentDirection",
    "Current_A", "BatteryTemp1_F", "BatteryTemp2_F", "BatteryTemp3_F",
    "InstantPower_W", "ExpectedPower_W", "PowerDelta_W", "PowerPlausibility",
    "Energy_mAh", "EstimatedCapacity_Ah",
    "AxisSlope_V_per_px", "AxisIntercept_V", "AxisFitRMSE_V", "AxisTickCount",
    "BlockLabelMethod", "Confidence", "SourceFrame", "GraphCrop",
    "NearestCANVideo_s", "CANTimeDelta_s", "CANAverage_V", "CANDifference_V",
    "CANBlockRMSE_V", "CANBlockMaxAbsError_V", "AverageDelta_V", "DifferenceDelta_V",
    "CANMatch",
]


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0


def parse_tsv(tsv: str) -> list[Word]:
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t")
    words: list[Word] = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            words.append(Word(text, float(row.get("conf") or -1), int(row["left"]),
                              int(row["top"]), int(row["width"]), int(row["height"])))
        except (KeyError, TypeError, ValueError):
            continue
    return words


def ordered_text(words: list[Word]) -> str:
    return " ".join(word.text for word in sorted(words, key=lambda word: (word.top // 12, word.left)))


def prepare_ocr_image(image: Image.Image) -> tuple[Image.Image, str]:
    """Crop a recorded landscape app band from a portrait MP4 frame.

    Samsung screen recordings keep a portrait video canvas while a rotated app
    occupies a wide horizontal band.  Detecting the band from row luminance
    avoids any hard-coded video timestamps and leaves normal portrait frames
    unchanged.
    """
    source = image.convert("RGB")
    width, height = source.size
    preview_width = 96
    preview_height = max(96, int(round(height * preview_width / max(1, width))))
    preview = source.convert("L").resize((preview_width, preview_height), Image.Resampling.BILINEAR)
    pixels = list(preview.get_flattened_data() if hasattr(preview, "get_flattened_data")
                  else preview.getdata())
    row_scores = [sum(pixels[y * preview_width:(y + 1) * preview_width]) /
                  (255.0 * preview_width) for y in range(preview_height)]
    active = [index for index, score in enumerate(row_scores) if score >= 0.045]
    runs = [(start, end) for start, end in _clusters(active, maximum_gap=2)
            if end - start + 1 >= preview_height * 0.06]
    if not runs:
        return source, "FULL_FRAME"
    start, end = max(runs, key=lambda item: (item[1] - item[0] + 1) *
                     (sum(row_scores[item[0]:item[1] + 1]) /
                      max(1, item[1] - item[0] + 1)))
    fraction = (end - start + 1) / preview_height
    top = max(0, int(math.floor(start * height / preview_height)) - 16)
    bottom = min(height, int(math.ceil((end + 1) * height / preview_height)) + 16)
    if not 0.10 <= fraction <= 0.62 or bottom <= top:
        return source, "FULL_FRAME"
    cropped = source.crop((0, top, width, bottom))
    if cropped.width / max(1, cropped.height) < 1.25:
        return source, "FULL_FRAME"
    target_width = 2144 if cropped.width < 1800 else cropped.width
    if target_width != cropped.width:
        target_height = int(round(cropped.height * target_width / cropped.width))
        cropped = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return cropped, "LANDSCAPE_BAND"


def _number(text: str) -> float | None:
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text.strip().replace(",", ""))
    return float(match.group(0)) if match else None


def _search(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _neutral_bright(pixel: tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    return min(r, g, b) >= 135 and max(r, g, b) - min(r, g, b) <= 55


def _colored_bar(pixel: tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    return g >= 110 and max(r, g, b) >= 145 and max(r, g, b) - min(r, g, b) >= 32


def _clusters(indices: list[int], maximum_gap: int = 1) -> list[tuple[int, int]]:
    if not indices:
        return []
    result: list[tuple[int, int]] = []
    start = previous = indices[0]
    for value in indices[1:]:
        if value - previous > maximum_gap + 1:
            result.append((start, previous))
            start = value
        previous = value
    result.append((start, previous))
    return result


def _fit(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    if len(points) < 4:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    intercept = y_mean - slope * x_mean
    residual = math.sqrt(sum((slope * x + intercept - y) ** 2 for x, y in points) / len(points))
    return slope, intercept, residual


def _axis(image: Image.Image, words: list[Word]) -> tuple[int, int, int, int, float, float, float, int] | None:
    width, height = image.size
    candidates: list[tuple[Word, float]] = []
    for word in words:
        value = _number(word.text)
        if value is None or not 5.0 <= value <= 30.0:
            continue
        if word.left >= width * 0.22 or word.top >= height * 0.48:
            continue
        candidates.append((word, value))
    if len(candidates) < 6:
        return None
    pixels = image.convert("RGB").load()
    grid_points: list[tuple[float, float]] = []
    bounds: list[tuple[int, int]] = []
    scan_left = int(width * 0.135)
    scan_right = int(width * 0.96)
    for word, value in candidates:
        center = int(round(word.center_y))
        best_y = center
        best_xs: list[int] = []
        for y in range(max(0, center - 14), min(height, center + 15)):
            xs = [x for x in range(scan_left, scan_right) if _neutral_bright(pixels[x, y])]
            if len(xs) > len(best_xs):
                best_y, best_xs = y, xs
        if len(best_xs) < width * 0.30:
            continue
        grid_points.append((float(best_y), value))
        bounds.append((min(best_xs), max(best_xs)))
    fitted = _fit(grid_points)
    if fitted is None or len(grid_points) < 6:
        return None
    slope, intercept, residual = fitted
    if slope >= 0 or not 0.00002 <= abs(slope) <= 0.01:
        return None
    left = int(round(median([item[0] for item in bounds])))
    right = int(round(median([item[1] for item in bounds])))
    top = min(int(point[0]) for point in grid_points)
    bottom = max(int(point[0]) for point in grid_points)
    if right - left < width * 0.45 or bottom - top < height * 0.12:
        return None
    return left, top, right, bottom, slope, intercept, residual, len(grid_points)


def _bars(image: Image.Image, left: int, top: int, right: int, bottom: int) -> list[tuple[float, int]]:
    pixels = image.convert("RGB").load()
    columns: list[int] = []
    for x in range(left + 3, right - 2):
        count = sum(1 for y in range(top, bottom + 1) if _colored_bar(pixels[x, y]))
        if count >= 8:
            columns.append(x)
    groups = [(start, end) for start, end in _clusters(columns, maximum_gap=2)
              if 5 <= end - start + 1 <= max(100, int((right - left) * 0.15))]
    result: list[tuple[float, int]] = []
    for start, end in groups:
        group_width = end - start + 1
        threshold = max(3, int(group_width * 0.30))
        top_y = None
        for y in range(top, bottom + 1):
            if sum(1 for x in range(start, end + 1) if _colored_bar(pixels[x, y])) >= threshold:
                top_y = y
                break
        if top_y is not None:
            result.append(((start + end) / 2.0, top_y))
    return result


def _word_rows(words: list[Word], tolerance: float) -> list[list[Word]]:
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda item: (item.center_y, item.left)):
        if rows:
            center = sum(item.center_y for item in rows[-1]) / len(rows[-1])
            if abs(word.center_y - center) <= tolerance:
                rows[-1].append(word)
                continue
        rows.append([word])
    return rows


def _numeric_fragment(text: str) -> str | None:
    cleaned = text.strip().replace(",", ".")
    if not re.search(r"\d", cleaned):
        return None
    cleaned = cleaned.replace("O", "0").replace("o", "0")
    match = re.search(r"[-+]?\d+(?:\.\d*)?", cleaned)
    return match.group(0) if match else None


def _dr_block_value(texts: list[str], base: int) -> float | None:
    candidates = list(texts)
    if len(texts) > 1:
        candidates.insert(0, "".join(texts))
    for text in candidates:
        fragment = _numeric_fragment(text)
        if fragment is None:
            continue
        sign = -1 if fragment.startswith("-") else 1
        fragment = fragment.lstrip("+-")
        if "." in fragment:
            integer, decimal = fragment.split(".", 1)
            if len(decimal) < 2:
                continue
            integer_value = int(integer or "0")
            if 5 <= integer_value <= 9 and 15 <= base <= 19:
                integer_value += 10
            if 12 <= integer_value <= 20:
                value = sign * (integer_value + int(decimal[:2]) / 100.0)
                if 10.0 <= value <= 25.0:
                    return value
            continue
        digits = re.sub(r"\D", "", fragment)
        if len(digits) == 2:
            value = base + int(digits) / 100.0
        elif len(digits) >= 4:
            value = int(digits[:2]) + int(digits[2:4]) / 100.0
        else:
            continue
        if 10.0 <= value <= 25.0:
            return value
    return None


def _dr_green(pixel: tuple[int, ...]) -> bool:
    red, green, blue = pixel[:3]
    return green >= 75 and green >= red * 1.25 and green >= blue * 1.15


def _dr_graph_bounds(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Locate the large Dr. Prius block-voltage bar chart.

    The rotated Samsung capture is already cropped to its landscape app band.
    The voltage chart is the tallest wide green row cluster; the shorter green
    cluster below it is the cumulative-delta chart and must not be selected.
    """
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    sample_step = 4 if width >= 1200 else 2
    sampled_width = math.ceil(width / sample_step)
    row_counts = [sum(1 for x in range(0, width, sample_step) if _dr_green(pixels[x, y]))
                  for y in range(height)]
    rows = [y for y, count in enumerate(row_counts) if count >= sampled_width * 0.05]
    candidates = []
    for start, end in _clusters(rows, maximum_gap=2):
        span = end - start + 1
        if not height * 0.30 <= start <= height * 0.78:
            continue
        if span < height * 0.045 or max(row_counts[start:end + 1]) < sampled_width * 0.25:
            continue
        candidates.append((span, max(row_counts[start:end + 1]), start, end))
    if not candidates:
        return None
    _, _, top, bottom = max(candidates)
    margin = int(round(width * 0.018))
    return margin, top, width - margin, bottom


def prepare_dr_prius_block_strip(image: Image.Image, block_count: int = 17) \
        -> tuple[Image.Image, dict[str, int]] | None:
    """Build one vertically stacked OCR image from the printed block labels.

    One Tesseract call can then read all cells while TSV y-coordinates preserve
    the block ordering.  Dense bar borders are removed without changing the
    source frame.
    """
    if not 8 <= block_count <= MAX_BLOCKS:
        return None
    bounds = _dr_graph_bounds(image)
    if bounds is None:
        return None
    left, graph_top, right, graph_bottom = bounds
    width, height = image.size
    pitch = (right - left) / block_count
    label_top = max(graph_top, graph_bottom - int(round(height * 0.060)))
    label_bottom = min(height, graph_bottom - int(round(height * 0.018)) + 1)
    if label_bottom - label_top < 12:
        return None
    source = image.convert("RGB")
    cell_width, cell_height, slot_height = 500, 240, 260
    cells: list[Image.Image] = []
    for index in range(block_count):
        center = left + (index + 0.5) * pitch
        cell_left = max(0, int(round(center - pitch * 0.43)))
        cell_right = min(width, int(round(center + pitch * 0.43)))
        gray = source.crop((cell_left, label_top, cell_right, label_bottom)).convert("L")
        flat = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data")
                    else gray.getdata())
        background = sorted(flat)[int(len(flat) * 0.75)] if flat else 255
        threshold = max(12, min(100, background * 0.55))
        cleaned = gray.point(lambda value: 0 if value < threshold else 255)
        clean_pixels = cleaned.load()
        clean_width, clean_height = cleaned.size
        for y in range(clean_height):
            if sum(clean_pixels[x, y] == 0 for x in range(clean_width)) > clean_width * 0.72:
                for x in range(clean_width):
                    clean_pixels[x, y] = 255
        for x in range(clean_width):
            if sum(clean_pixels[x, y] == 0 for y in range(clean_height)) > clean_height * 0.88:
                for y in range(clean_height):
                    clean_pixels[x, y] = 255
        cleaned = ImageOps.expand(cleaned, border=10, fill=255).resize(
            (cell_width, cell_height), Image.Resampling.NEAREST)
        cells.append(cleaned)
    stacked = Image.new("L", (cell_width + 20, block_count * slot_height), 255)
    for index, cell in enumerate(cells):
        stacked.paste(cell, (10, index * slot_height))
    return stacked, {
        "slot_height": slot_height,
        "graph_top": graph_top,
        "graph_bottom": graph_bottom,
        "chart_left": left,
        "chart_right": right,
    }


def parse_dr_prius_block_tsv(tsv: str, block_count: int, slot_height: int) \
        -> list[float | None]:
    words = parse_tsv(tsv)
    cell_text: list[list[tuple[float, str]]] = [[] for _ in range(block_count)]
    for word in words:
        index = int(word.center_y / max(1, slot_height))
        if 0 <= index < block_count:
            cell_text[index].append((word.center_x, word.text))
    values = [_dr_block_value([text for _, text in sorted(items)], 16)
              for items in cell_text]
    return values


def _complete_dr_prius_values(image: Image.Image, values: list[float | None],
                              graph_bounds: tuple[int, int, int, int] | None = None) \
        -> tuple[list[float | None], list[bool], float | None]:
    block_count = len(values)
    direct_mask = [value is not None for value in values]
    bounds = graph_bounds or _dr_graph_bounds(image)
    if bounds is None or sum(direct_mask) < max(8, block_count // 2):
        return values, direct_mask, None
    left, graph_top, right, graph_bottom = bounds
    pixels = image.convert("RGB").load()
    pitch = (right - left) / block_count
    tops: list[int | None] = []
    for index in range(block_count):
        cell_left = max(0, int(left + (index + 0.15) * pitch))
        cell_right = min(image.width, int(left + (index + 0.85) * pitch))
        threshold = max(2, int((cell_right - cell_left) * 0.08))
        found = None
        for y in range(max(0, graph_top - 3), min(image.height, graph_bottom + 1)):
            if sum(1 for x in range(cell_left, cell_right) if _dr_green(pixels[x, y])) >= threshold:
                found = y
                break
        tops.append(found)
    fitted = _fit([(float(top), float(value)) for top, value in zip(tops, values)
                   if top is not None and value is not None])
    if fitted is None:
        return values, direct_mask, None
    slope, intercept, residual = fitted
    if slope >= 0 or residual > 0.020:
        return values, direct_mask, residual
    completed = list(values)
    for index, (top, value) in enumerate(zip(tops, values)):
        if value is None and top is not None:
            predicted = round(slope * top + intercept, 2)
            if 10.0 <= predicted <= 25.0:
                completed[index] = predicted
    return completed, direct_mask, residual


def _dr_bar_tops(image: Image.Image, block_count: int, value_row_y: float) -> list[int | None]:
    pixels = image.convert("RGB").load()
    width, height = image.size
    cell_width = width / block_count
    top_limit = max(0, int(value_row_y - height * 0.34))
    bottom_limit = min(height - 1, int(value_row_y + height * 0.07))
    result: list[int | None] = []
    for index in range(block_count):
        left = max(0, int((index + 0.16) * cell_width))
        right = min(width, int((index + 0.84) * cell_width))
        threshold = max(2, int((right - left) * 0.08))
        found = None
        for y in range(top_limit, bottom_limit + 1):
            if sum(1 for x in range(left, right) if _dr_green(pixels[x, y])) >= threshold:
                found = y
                break
        result.append(found)
    return result


def _dr_direct_values(image: Image.Image, words: list[Word], block_count: int) \
        -> tuple[list[float | None], float, list[int | None], float | None, list[bool]]:
    width, height = image.size
    candidates: list[tuple[int, float, list[Word]]] = []
    for row in _word_rows(words, min(18.0, max(7.0, height * 0.018))):
        center_y = sum(word.center_y for word in row) / len(row)
        if not height * 0.28 <= center_y <= height * 0.74:
            continue
        strong = 0
        numeric = []
        for word in row:
            fragment = _numeric_fragment(word.text)
            if fragment is None:
                continue
            numeric.append(word)
            try:
                value = float(fragment.rstrip("."))
            except ValueError:
                continue
            if 5.0 <= value <= 20.999 and "." in fragment:
                strong += 1
        if strong >= max(5, block_count // 3) and numeric:
            spread = max(word.center_x for word in numeric) - min(word.center_x for word in numeric)
            if spread >= width * 0.50:
                candidates.append((strong, center_y, numeric))
    if not candidates:
        return ([None] * block_count, 0.0, [None] * block_count, None,
                [False] * block_count)
    _, row_y, numeric_words = max(candidates, key=lambda item: (item[0], -item[1]))
    bases = []
    for word in numeric_words:
        fragment = _numeric_fragment(word.text)
        if fragment and "." in fragment:
            try:
                value = float(fragment.rstrip("."))
                if 12.0 <= value <= 20.999:
                    bases.append(int(value))
            except ValueError:
                pass
    base = int(round(median(bases))) if bases else 16
    cell_text: list[list[tuple[float, str]]] = [[] for _ in range(block_count)]
    for word in numeric_words:
        index = min(block_count - 1, max(0, int(word.center_x * block_count / width)))
        cell_text[index].append((word.center_x, word.text))
    values: list[float | None] = []
    for items in cell_text:
        texts = [text for _, text in sorted(items)]
        values.append(_dr_block_value(texts, base))
    direct_mask = [value is not None for value in values]

    tops = _dr_bar_tops(image, block_count, row_y)
    fitted_points = [(float(top), float(value)) for top, value in zip(tops, values)
                     if top is not None and value is not None]
    fitted = _fit(fitted_points)
    residual = None
    if fitted is not None:
        slope, intercept, residual = fitted
        if slope < 0 and residual <= 0.035:
            for index, (top, value) in enumerate(zip(tops, values)):
                if value is None and top is not None:
                    predicted = round(slope * top + intercept, 2)
                    if 10.0 <= predicted <= 25.0:
                        values[index] = predicted
    return values, row_y, tops, residual, direct_mask


def _dr_scaled_value(text: str, decimals: int, minimum: float, maximum: float) -> float | None:
    fragment = _numeric_fragment(text)
    if fragment is None:
        return None
    try:
        literal = float(fragment.rstrip("."))
    except ValueError:
        return None
    if minimum <= literal <= maximum and "." in fragment:
        return literal
    digits = re.sub(r"\D", "", fragment)
    if not digits:
        return None
    scaled = int(digits) / (10 ** decimals)
    return scaled if minimum <= scaled <= maximum else None


def _dr_top_metrics(image: Image.Image, words: list[Word], value_row_y: float) -> dict[str, Any]:
    width, height = image.size
    numeric_rows = []
    for row in _word_rows(words, min(18.0, max(7.0, height * 0.018))):
        center_y = sum(word.center_y for word in row) / len(row)
        numeric = [word for word in row if _numeric_fragment(word.text) is not None
                   and not re.search(r"[A-Za-z]+\s*\d", word.text)
                   and word.text.strip().upper() != "12V"]
        if height * 0.10 <= center_y < value_row_y and len(numeric) >= 4:
            numeric_rows.append((center_y, numeric))
    numeric_rows.sort(key=lambda item: item[0])
    result: dict[str, Any] = {}
    if numeric_rows:
        _, first = numeric_rows[0]
        specs = [
            ("pack", 2, 200.0, 400.0), ("blade", 2, 5.0, 12.0),
            ("current", 2, 0.0, 200.0), ("soc", 2, 0.0, 100.0),
            ("delta_soc", 2, 0.0, 100.0),
        ]
        for word in first:
            index = min(4, max(0, int(word.center_x * 5 / width)))
            name, decimals, minimum, maximum = specs[index]
            value = _dr_scaled_value(word.text, decimals, minimum, maximum)
            if value is not None and name not in result:
                result[name] = value
    if len(numeric_rows) >= 2:
        _, second = numeric_rows[1]
        specs = [
            ("volt_diff", 2, 0.0, 5.0), ("max_charge", 1, 0.0, 200.0),
            ("max_discharge", 1, 0.0, 200.0), ("aux_voltage", 1, 8.0, 18.0),
            ("temp1", 1, -100.0, 250.0), ("temp2", 1, -100.0, 250.0),
            ("temp3", 1, -100.0, 250.0),
        ]
        for word in second:
            index = min(6, max(0, int(word.center_x * 7 / width)))
            name, decimals, minimum, maximum = specs[index]
            value = _dr_scaled_value(word.text, decimals, minimum, maximum)
            if value is not None and name not in result:
                result[name] = value
    text = ordered_text(words).upper()
    result["direction"] = "CHARGING" if "CHARGING" in text and "DISCHARGING" not in text \
        else "DISCHARGING" if "DISCHARGING" in text else ""
    if "current" in result and result["direction"] == "CHARGING":
        result["current"] = -abs(result["current"])
    return result


def _save_graph_crop(image: Image.Image, crop_dir: Path | None, video_s: float) -> str:
    if crop_dir is None:
        return ""
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_name = f"graph_{video_s:010.3f}".replace(".", "_") + ".jpg"
    image.convert("RGB").save(crop_dir / crop_name, "JPEG", quality=90, optimize=True)
    return str(Path("GRAPH_KEYFRAMES") / crop_name)


def _extract_dr_prius(image: Image.Image, words: list[Word], video_s: float,
                      vehicle_profile: str, expected_blocks: int | None,
                      source_frame: str, crop_dir: Path | None,
                      detail_image: Image.Image | None = None,
                      detail_words: list[Word] | None = None,
                      direct_block_values: list[float | None] | None = None,
                      dr_graph_bounds: tuple[int, int, int, int] | None = None) -> dict[str, Any] | None:
    text = ordered_text(words)
    lowered = text.lower()
    if image.width / max(1, image.height) < 1.25:
        return None
    if "special features" in lowered or "active apps" in lowered or "close all" in lowered:
        return None
    if "battery monitor" not in lowered and "battery block voltage" not in lowered:
        return None
    block_count = expected_blocks if expected_blocks and 8 <= expected_blocks <= MAX_BLOCKS else 17
    block_image = detail_image or image
    block_words = detail_words or words
    if direct_block_values is not None and len(direct_block_values) == block_count:
        values, direct_mask, fit_residual = _complete_dr_prius_values(
            image, list(direct_block_values), dr_graph_bounds)
    else:
        values, _, _, fit_residual, direct_mask = _dr_direct_values(
            block_image, block_words, block_count)
    extracted_count = sum(value is not None for value in values)
    if extracted_count != block_count:
        return None
    metrics = _dr_top_metrics(image, words, image.height * 0.78)
    if detail_image is not None and detail_words:
        detail_bounds = dr_graph_bounds if detail_image is image else _dr_graph_bounds(detail_image)
        if detail_bounds is not None:
            detail_value_row = float(detail_bounds[3])
            detail_metrics = _dr_top_metrics(detail_image, detail_words, detail_value_row)
            for key, value in detail_metrics.items():
                if key not in metrics or metrics[key] in (None, ""):
                    metrics[key] = value
    reconstructed = [index + 1 for index, direct in enumerate(direct_mask) if not direct]
    numeric_values = [float(value) for value in values if value is not None]
    average = sum(numeric_values) / block_count
    difference = max(numeric_values) - min(numeric_values)
    confidence = 0.72 if not reconstructed else 0.62
    if fit_residual is not None and fit_residual <= 0.02:
        confidence += 0.06
    printed_difference = metrics.get("volt_diff")
    if printed_difference is not None and abs(printed_difference - difference) <= 0.04:
        confidence += 0.06
    printed_pack = metrics.get("pack")
    if printed_pack is not None and abs(printed_pack - sum(numeric_values)) > 0.25:
        return None
    if reconstructed and (fit_residual is None or fit_residual > 0.020
                          or printed_pack is None
                          or abs(printed_pack - sum(numeric_values)) > 0.25):
        return None
    if printed_pack is not None and abs(printed_pack - sum(numeric_values)) <= 0.25:
        confidence += 0.06
    row: dict[str, Any] = {
        "Video_s": f"{video_s:.3f}", "App": "DR_PRIUS",
        "Layout": "DR_PRIUS_BATTERY_MONITOR_LANDSCAPE",
        "VehicleProfile": vehicle_profile, "BlockCount": block_count,
        "ExtractedBlockCount": block_count - len(reconstructed),
        "ReconstructedBlockCount": len(reconstructed),
        "ReconstructedBlocks": ";".join(str(index) for index in reconstructed),
        "ExtractionMethod": "PRINTED_BLOCK_LABELS" if not reconstructed
                            else "PRINTED_LABELS_PLUS_BAR_FIT",
        "EvidenceGrade": "CANDIDATE",
        "GraphPackSum_V": f"{sum(numeric_values):.6f}",
        "GraphAverage_V": f"{average:.6f}",
        "GraphMinimum_V": f"{min(numeric_values):.6f}",
        "GraphMaximum_V": f"{max(numeric_values):.6f}",
        "GraphDifference_V": f"{difference:.6f}",
        "PrintedPackVoltage_V": "" if printed_pack is None else f"{printed_pack:.6f}",
        "BladeVoltage_V": metrics.get("blade", ""),
        "PrintedAverage_V": "",
        "PrintedDifference_V": "" if printed_difference is None else f"{printed_difference:.6f}",
        "PrintedVoltageDifference_V": "" if printed_difference is None else f"{printed_difference:.6f}",
        "StartSOC_pct": "", "ActualSOC_pct": metrics.get("soc", ""),
        "CurrentDirection": metrics.get("direction", ""), "Current_A": metrics.get("current", ""),
        "BatteryTemp1_F": metrics.get("temp1", ""), "BatteryTemp2_F": metrics.get("temp2", ""),
        "BatteryTemp3_F": metrics.get("temp3", ""),
        "AxisSlope_V_per_px": "", "AxisIntercept_V": "",
        "AxisFitRMSE_V": "" if fit_residual is None else f"{fit_residual:.6f}",
        "AxisTickCount": 0, "BlockLabelMethod": "DR_PRIUS_ORDERED_EQUAL_COLUMNS",
        "Confidence": f"{min(0.94, confidence):.3f}", "SourceFrame": source_frame,
        "GraphCrop": _save_graph_crop(image, crop_dir, video_s),
    }
    for index, value in enumerate(numeric_values, 1):
        row[f"B{index:02d}_V"] = f"{value:.6f}"
    return row


def _classify(text: str, requested: str) -> tuple[str, str]:
    requested = requested.upper().replace(" ", "_")
    lowered = text.lower()
    if "avg=" in lowered and "diff=" in lowered and ("camry" in lowered or "soc" in lowered):
        return "HYBRID_ASSISTANT", "HYBRID_ASSISTANT_BATTERY_CHECK"
    if ("dr. prius" in lowered or "dr prius" in lowered
            or ("battery monitor" in lowered and "battery block voltage" in lowered)
            or requested.startswith("DR_PRIUS")):
        return "DR_PRIUS", "DR_PRIUS_BATTERY_MONITOR"
    if requested.startswith("HYBRID_ASSISTANT"):
        return "HYBRID_ASSISTANT", "HYBRID_ASSISTANT_BATTERY_CHECK"
    return "UNKNOWN", "BATTERY_GRAPH_GENERIC"


def extract_battery_graph(image: Image.Image, words: list[Word], video_s: float,
                          requested_profile: str, vehicle_profile: str,
                          expected_blocks: int | None, source_frame: str,
                          crop_dir: Path | None = None,
                          detail_image: Image.Image | None = None,
                          detail_words: list[Word] | None = None,
                          direct_block_values: list[float | None] | None = None,
                          dr_graph_bounds: tuple[int, int, int, int] | None = None) -> dict[str, Any] | None:
    text = ordered_text(words)
    app, layout = _classify(text, requested_profile)
    if app == "DR_PRIUS" or requested_profile.upper().replace(" ", "_").startswith("DR_PRIUS"):
        return _extract_dr_prius(image, words, video_s, vehicle_profile,
                                 expected_blocks, source_frame, crop_dir,
                                 detail_image, detail_words, direct_block_values,
                                 dr_graph_bounds)
    axis = _axis(image, words)
    if axis is None:
        return None
    left, top, right, bottom, slope, intercept, residual, tick_count = axis
    bars = _bars(image, left, top, right, bottom)
    if not 8 <= len(bars) <= MAX_BLOCKS:
        return None
    if expected_blocks is not None and len(bars) != expected_blocks:
        return None
    values = [slope * top_y + intercept for _, top_y in bars]
    if any(not 5.0 <= value <= 30.0 for value in values):
        return None
    printed_average = _search(text, r"Avg\s*=\s*([0-9]+(?:\.[0-9]+)?)")
    printed_difference = _search(text, r"Diff\s*=\s*([0-9]+(?:\.[0-9]+)?)")
    average = sum(values) / len(values)
    minimum = min(values)
    maximum = max(values)
    difference = maximum - minimum
    confidence = 0.45
    confidence += min(0.15, tick_count * 0.015)
    confidence += 0.20 if expected_blocks and len(values) == expected_blocks else 0.08
    if printed_average is not None and abs(printed_average - average) <= 0.025:
        confidence += 0.10
    if printed_difference is not None and abs(printed_difference - difference) <= 0.025:
        confidence += 0.10
    confidence = min(0.98, confidence)
    crop_name = ""
    if crop_dir is not None:
        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_name = f"graph_{video_s:010.3f}".replace(".", "_") + ".jpg"
        crop_bottom = min(image.height, bottom + int(image.height * 0.07))
        image.crop((max(0, left - int(image.width * 0.13)), max(0, top - 20),
                    min(image.width, right + 15), crop_bottom)).convert("RGB").save(
                        crop_dir / crop_name, "JPEG", quality=90, optimize=True)
    current = _search(text, r"Current\s+([-+]?[0-9]+(?:\.[0-9]+)?)\s*A")
    power = _search(text, r"(?:Inst\.?\s+Power|Power)\s+([-+]?[0-9]+(?:\.[0-9]+)?)\s*W")
    expected_power = sum(values) * current if current is not None else None
    power_delta = power - expected_power if power is not None and expected_power is not None else None
    power_plausibility = ""
    if power_delta is not None:
        tolerance = max(50.0, abs(expected_power) * 0.25)
        power_plausibility = "CONSISTENT" if abs(power_delta) <= tolerance else "REVIEW_OCR"
    row: dict[str, Any] = {
        "Video_s": f"{video_s:.3f}",
        "App": app,
        "Layout": layout,
        "VehicleProfile": vehicle_profile,
        "BlockCount": len(values),
        "ExtractedBlockCount": len(values),
        "ReconstructedBlockCount": 0,
        "ReconstructedBlocks": "",
        "ExtractionMethod": "NUMERIC_Y_AXIS_AND_BAR_GEOMETRY",
        "EvidenceGrade": "CANDIDATE",
        "GraphPackSum_V": f"{sum(values):.6f}",
        "GraphAverage_V": f"{average:.6f}",
        "GraphMinimum_V": f"{minimum:.6f}",
        "GraphMaximum_V": f"{maximum:.6f}",
        "GraphDifference_V": f"{difference:.6f}",
        "PrintedAverage_V": "" if printed_average is None else f"{printed_average:.6f}",
        "PrintedDifference_V": "" if printed_difference is None else f"{printed_difference:.6f}",
        "PrintedPackVoltage_V": "",
        "BladeVoltage_V": "",
        "PrintedVoltageDifference_V": "" if printed_difference is None else f"{printed_difference:.6f}",
        "StartSOC_pct": _search(text, r"Start\s+SOC\s+([0-9]+(?:\.[0-9]+)?)\s*%") or "",
        "ActualSOC_pct": _search(text, r"Actual\s+SOC\s+([0-9]+(?:\.[0-9]+)?)\s*%") or "",
        "Current_A": "" if current is None else current,
        "CurrentDirection": "",
        "BatteryTemp1_F": "", "BatteryTemp2_F": "", "BatteryTemp3_F": "",
        "InstantPower_W": "" if power is None else power,
        "ExpectedPower_W": "" if expected_power is None else f"{expected_power:.3f}",
        "PowerDelta_W": "" if power_delta is None else f"{power_delta:.3f}",
        "PowerPlausibility": power_plausibility,
        "Energy_mAh": _search(text, r"Energy\s+([-+]?[0-9]+(?:\.[0-9]+)?)\s*mAh") or "",
        "EstimatedCapacity_Ah": _search(text, r"Est\.?\s+Capacity\s+([-+]?[0-9]+(?:\.[0-9]+)?)\s*Ah") or "",
        "AxisSlope_V_per_px": f"{slope:.10f}",
        "AxisIntercept_V": f"{intercept:.8f}",
        "AxisFitRMSE_V": f"{residual:.6f}",
        "AxisTickCount": tick_count,
        "BlockLabelMethod": "ORDERED_BAR_POSITION_EXPECTED_COUNT" if expected_blocks else "ORDERED_BAR_POSITION",
        "Confidence": f"{confidence:.3f}",
        "SourceFrame": source_frame,
        "GraphCrop": str(Path("GRAPH_KEYFRAMES") / crop_name) if crop_name else "",
    }
    for index, value in enumerate(values, 1):
        row[f"B{index:02d}_V"] = f"{value:.6f}"
    return row


def load_can_battery(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def correlate_with_can(row: dict[str, Any], can_rows: list[dict[str, str]]) -> None:
    try:
        graph_time = float(row["Video_s"])
    except (KeyError, TypeError, ValueError):
        return
    candidates = []
    for candidate in can_rows:
        try:
            candidates.append((abs(float(candidate["Video_s"]) - graph_time), candidate))
        except (KeyError, TypeError, ValueError):
            continue
    if not candidates:
        row["CANMatch"] = "NO_ALIGNED_CAN_DATA"
        return
    delta, nearest = min(candidates, key=lambda item: item[0])
    row["NearestCANVideo_s"] = nearest.get("Video_s", "")
    row["CANTimeDelta_s"] = f"{delta:.6f}"
    row["CANAverage_V"] = nearest.get("Average_V", "")
    row["CANDifference_V"] = nearest.get("Difference_V", "")
    differences: list[float] = []
    for index in range(1, min(int(row.get("BlockCount", 0)), 17) + 1):
        try:
            differences.append(float(row[f"B{index:02d}_V"]) - float(nearest[f"B{index:02d}_V"]))
        except (KeyError, TypeError, ValueError):
            continue
    if differences:
        rmse = math.sqrt(sum(value * value for value in differences) / len(differences))
        maximum_error = max(abs(value) for value in differences)
        row["CANBlockRMSE_V"] = f"{rmse:.6f}"
        row["CANBlockMaxAbsError_V"] = f"{maximum_error:.6f}"
    try:
        row["AverageDelta_V"] = f"{float(row['GraphAverage_V']) - float(nearest['Average_V']):.6f}"
        row["DifferenceDelta_V"] = f"{float(row['GraphDifference_V']) - float(nearest['Difference_V']):.6f}"
    except (KeyError, TypeError, ValueError):
        pass
    if delta > 2.5:
        row["CANMatch"] = "NEAREST_OUTSIDE_2.5S"
    elif differences and rmse <= 0.08 and maximum_error <= 0.20:
        row["CANMatch"] = "MATCHED"
        if row.get("EvidenceGrade") == "CANDIDATE":
            row["EvidenceGrade"] = "PROBABLE"
        try:
            row["Confidence"] = f"{min(0.98, float(row.get('Confidence', 0)) + 0.05):.3f}"
        except (TypeError, ValueError):
            pass
    elif differences:
        row["CANMatch"] = "TIME_MATCH_VALUE_REVIEW"
    else:
        row["CANMatch"] = "TIME_MATCHED_NO_BLOCK_COMPARISON"


def write_graph_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=GRAPH_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
