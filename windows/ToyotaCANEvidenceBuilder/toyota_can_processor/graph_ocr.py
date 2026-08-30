from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image


MAX_BLOCKS = 40
GRAPH_FIELDS = [
    "Video_s", "App", "Layout", "VehicleProfile", "BlockCount",
    *[f"B{index:02d}_V" for index in range(1, MAX_BLOCKS + 1)],
    "GraphPackSum_V", "GraphAverage_V", "GraphMinimum_V", "GraphMaximum_V", "GraphDifference_V",
    "PrintedAverage_V", "PrintedDifference_V", "StartSOC_pct", "ActualSOC_pct",
    "Current_A", "InstantPower_W", "ExpectedPower_W", "PowerDelta_W", "PowerPlausibility",
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


def _classify(text: str, requested: str) -> tuple[str, str]:
    requested = requested.upper().replace(" ", "_")
    lowered = text.lower()
    if "avg=" in lowered and "diff=" in lowered and ("camry" in lowered or "soc" in lowered):
        return "HYBRID_ASSISTANT", "HYBRID_ASSISTANT_BATTERY_CHECK"
    if "dr. prius" in lowered or "dr prius" in lowered or requested.startswith("DR_PRIUS"):
        return "DR_PRIUS", "DR_PRIUS_BATTERY_MONITOR"
    if requested.startswith("HYBRID_ASSISTANT"):
        return "HYBRID_ASSISTANT", "HYBRID_ASSISTANT_BATTERY_CHECK"
    return "UNKNOWN", "BATTERY_GRAPH_GENERIC"


def extract_battery_graph(image: Image.Image, words: list[Word], video_s: float,
                          requested_profile: str, vehicle_profile: str,
                          expected_blocks: int | None, source_frame: str,
                          crop_dir: Path | None = None) -> dict[str, Any] | None:
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
    text = ordered_text(words)
    app, layout = _classify(text, requested_profile)
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
        "GraphPackSum_V": f"{sum(values):.6f}",
        "GraphAverage_V": f"{average:.6f}",
        "GraphMinimum_V": f"{minimum:.6f}",
        "GraphMaximum_V": f"{maximum:.6f}",
        "GraphDifference_V": f"{difference:.6f}",
        "PrintedAverage_V": "" if printed_average is None else f"{printed_average:.6f}",
        "PrintedDifference_V": "" if printed_difference is None else f"{printed_difference:.6f}",
        "StartSOC_pct": _search(text, r"Start\s+SOC\s+([0-9]+(?:\.[0-9]+)?)\s*%") or "",
        "ActualSOC_pct": _search(text, r"Actual\s+SOC\s+([0-9]+(?:\.[0-9]+)?)\s*%") or "",
        "Current_A": "" if current is None else current,
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
        row["CANBlockRMSE_V"] = f"{math.sqrt(sum(value * value for value in differences) / len(differences)):.6f}"
        row["CANBlockMaxAbsError_V"] = f"{max(abs(value) for value in differences):.6f}"
    try:
        row["AverageDelta_V"] = f"{float(row['GraphAverage_V']) - float(nearest['Average_V']):.6f}"
        row["DifferenceDelta_V"] = f"{float(row['GraphDifference_V']) - float(nearest['Difference_V']):.6f}"
    except (KeyError, TypeError, ValueError):
        pass
    row["CANMatch"] = "MATCHED" if delta <= 2.5 else "NEAREST_OUTSIDE_2.5S"


def write_graph_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=GRAPH_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
