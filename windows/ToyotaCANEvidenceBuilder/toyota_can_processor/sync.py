from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Alignment:
    valid: bool
    sample_count_total: int
    sample_count_used: int
    slope_android_ns_per_esp_us: float | None
    intercept_android_ns: float | None
    drift_ppm: float | None
    residual_rms_ms: float | None
    residual_max_ms: float | None
    video_anchor_android_ns: int | None
    video_anchor_uncertainty_ms: float | None
    formula: str | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def video_seconds(self, esp_us: float) -> float | None:
        if not self.valid or self.slope_android_ns_per_esp_us is None:
            return None
        if self.intercept_android_ns is None or self.video_anchor_android_ns is None:
            return None
        android_ns = self.slope_android_ns_per_esp_us * esp_us + self.intercept_android_ns
        return (android_ns - self.video_anchor_android_ns) / 1_000_000_000.0


def _median_absolute_deviation(values: list[float]) -> float:
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _regression(points: list[tuple[float, float]]) -> tuple[float, float]:
    x_mean = sum(x for x, _ in points) / len(points)
    y_mean = sum(y for _, y in points) / len(points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    if denominator == 0:
        raise ValueError("Sync samples do not span time")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator
    return slope, y_mean - slope * x_mean


def fit_alignment(capture_sync: dict[str, Any]) -> Alignment:
    warnings: list[str] = []
    samples = capture_sync.get("sync_samples") or []
    candidates: list[tuple[float, float, float]] = []
    for sample in samples:
        try:
            t1 = float(sample["t1_client_ns"] if "t1_client_ns" in sample else sample["t1_android_ns"])
            t4 = float(sample["t4_client_ns"] if "t4_client_ns" in sample else sample["t4_android_ns"])
            e2 = float(sample["e2_esp_us"])
            e3 = float(sample["e3_esp_us"])
        except (KeyError, TypeError, ValueError):
            continue
        rtt = (t4 - t1) - (e3 - e2) * 1000.0
        if rtt < 0 or t4 <= t1 or e3 < e2:
            continue
        candidates.append(((e2 + e3) / 2.0, (t1 + t4) / 2.0, rtt))

    anchor = capture_sync.get("video_anchor_ns")
    uncertainty = capture_sync.get("video_anchor_uncertainty_ns")
    if len(candidates) < 4:
        return Alignment(False, len(samples), len(candidates), None, None, None, None, None,
                         int(anchor) if anchor is not None else None,
                         float(uncertainty) / 1e6 if uncertainty is not None else None,
                         None, ["At least four valid BLE exchanges are required"])

    rtts = [item[2] for item in candidates]
    median = statistics.median(rtts)
    mad = _median_absolute_deviation(rtts)
    threshold = median + max(3.0 * mad, 2_000_000.0)
    filtered = [item for item in candidates if item[2] <= threshold]
    if len(filtered) < 4:
        filtered = sorted(candidates, key=lambda item: item[2])[:max(4, len(candidates) // 2)]
    points = [(item[0], item[1]) for item in filtered]
    slope, intercept = _regression(points)
    residuals = [y - (slope * x + intercept) for x, y in points]
    rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    maximum = max(abs(value) for value in residuals)
    drift_ppm = (slope / 1000.0 - 1.0) * 1_000_000.0
    if abs(drift_ppm) > 500:
        warnings.append(f"Clock drift estimate {drift_ppm:.1f} ppm is unusually large")
    if rms > 5_000_000:
        warnings.append(f"BLE fit residual RMS {rms / 1e6:.3f} ms is high")
    if anchor is None:
        warnings.append("Video timing anchor is missing; CAN-to-Android fit is valid but video mapping is unavailable")

    formula = None
    if anchor is not None:
        formula = (f"video_seconds = ({slope:.12f} * esp_time_us + "
                   f"{intercept:.3f} - {int(anchor)}) / 1000000000")
    return Alignment(True, len(samples), len(filtered), slope, intercept, drift_ppm,
                     rms / 1e6, maximum / 1e6, int(anchor) if anchor is not None else None,
                     float(uncertainty) / 1e6 if uncertainty is not None else None,
                     formula, warnings)


def validate_sd_sync(capture_sync: dict[str, Any], sd_rows: list[dict[str, str]]) -> dict[str, Any]:
    android = {int(item["sequence"]): item for item in capture_sync.get("sync_samples", [])
               if "sequence" in item}
    matched = 0
    mismatched = 0
    for row in sd_rows:
        try:
            sequence = int(row["Sequence"])
            sample = android.get(sequence)
            if not sample:
                continue
            matched += 1
            if (int(row["ESP_Receive_us"]) != int(sample["e2_esp_us"]) or
                    int(row["ESP_Send_us"]) != int(sample["e3_esp_us"])):
                mismatched += 1
        except (KeyError, TypeError, ValueError):
            mismatched += 1
    return {"sd_rows": len(sd_rows), "matched_sequences": matched,
            "timestamp_mismatches": mismatched, "confirmed": matched > 0 and mismatched == 0}
