from __future__ import annotations

import csv
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


CORRELATION_COLUMNS = [
    "Session", "Profile", "DecoderKey", "Field", "ArrayIndex", "Unit",
    "CANVideo_s", "OCRVideo_s", "Lag_s", "CANValue", "OCRValue", "Error",
    "AbsoluteError", "Tolerance", "Agreement", "OCRLabel", "OCRFrame",
    "DetectedApp", "DetectedLayout", "PairingMethod", "SelectedFixedLag_s", "TimeBucket",
]

GRADE_COLUMNS = [
    "Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "DecodedSamples",
    "OCRPairs", "UniqueOCRFrames", "EffectiveIndependentSamples", "Agreements",
    "AgreementRate", "RMSE", "MedianAbsoluteError", "MedianLag_s", "TimeSpan_s",
    "DynamicRange", "BoundsFailures", "ExpectedMismatches", "UnitCheckFailures",
    "Outliers", "IndependentSessions", "DatabaseEvidenceGrade",
    "PreliminaryLocalGrade", "DecisionReason",
]

REJECTED_COLUMNS = [
    "Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "OCRVideo_s",
    "OCRFrame", "OCRLabel", "DetectedApp", "DetectedLayout", "Reason",
]


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        return list(csv.DictReader(stream))


def _label_match(text: str, label: str) -> re.Match[str] | None:
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])", text,
        flags=re.IGNORECASE)


def _number_after_label(text: str, label: str, unit: str = "") -> float | None:
    label_match = _label_match(text, label)
    if not label_match:
        return None
    tail_limit = 18 if unit in {"", "1-based block"} else 48
    tail = text[label_match.end():label_match.end() + tail_limit]
    indexed_label = re.match(r"^(.*?)(\d+)$", label)
    if indexed_label:
        next_index = re.search(
            rf"{re.escape(indexed_label.group(1))}\d+", tail, flags=re.IGNORECASE)
        if next_index:
            tail = tail[:next_index.start()]
    unit_patterns = {
        "V": r"[vV]", "A": r"[aA]", "ohm": r"(?:[oO]hm|[oO]hms?)",
        "%": r"%", "degC": r"(?:°?\s*[cC]|deg\s*[cC])",
        "kW": r"[kK]\s*[wW]", "rpm": r"[rR][pP][mM]",
        "Nm": r"[nN]\s*[mM]", "km/h": r"[kK][mM]\s*/\s*[hH]",
        "s": r"(?:sec(?:ond)?s?|[sS])",
    }
    number = r"(?:[-+]?\d+(?:\.\d+)?|[Oo])"
    if unit in unit_patterns:
        after = re.search(rf"(?P<value>{number})\s*{unit_patterns[unit]}", tail)
        before = re.search(rf"{unit_patterns[unit]}\s*(?P<value>{number})", tail)
        matches = [item for item in (after, before) if item]
        match = min(matches, key=lambda item: item.start()) if matches else None
    else:
        match = re.search(rf"(?P<value>{number})", tail)
    if not match:
        return None
    prefix = tail[:match.start()]
    if "save" in prefix.lower() or re.search(r"[A-Za-z]{3,}", prefix):
        return None
    try:
        token = match.group("value")
        return 0.0 if token.lower() == "o" else float(token)
    except ValueError:
        return None


def _default_tolerance(unit: str) -> float:
    return {
        "V": 0.06, "A": 0.25, "ohm": 0.0011, "%": 0.6,
        "degC": 0.8, "kW": 0.8, "rpm": 150.0, "s": 2.0,
        "1-based block": 0.1,
    }.get(unit, 0.1)


def _minimum_dynamic_range(unit: str, tolerance: float) -> float:
    return {
        "V": 0.20, "A": 2.0, "ohm": 0.002, "%": 3.0,
        "degC": 3.0, "kW": 2.0, "rpm": 300.0, "s": 5.0,
        "1-based block": 1.0,
    }.get(unit, max(0.1, tolerance * 4.0))


def _decision(*, pairs: int, unique_frames: int, effective_samples: int,
              agreements: int, bounds_failures: int, expected_mismatches: int,
              unit_failures: int, rmse: float | None, median_absolute_error: float | None,
              tolerance: float, time_span: float, dynamic_range: float, unit: str) -> tuple[str, str]:
    rate = agreements / pairs if pairs else 0.0
    blockers = []
    if pairs < 20:
        blockers.append("fewer than 20 one-to-one pairs")
    if unique_frames < 20:
        blockers.append("fewer than 20 unique OCR frames")
    if effective_samples < 12:
        blockers.append("fewer than 12 independent time buckets")
    if time_span < 30.0:
        blockers.append("time span below 30 seconds")
    required_range = _minimum_dynamic_range(unit, tolerance)
    if dynamic_range < required_range:
        blockers.append(f"dynamic range below {required_range:g} {unit}".rstrip())
    if rate < 0.90:
        blockers.append("agreement rate below 90%")
    if rmse is None or rmse > tolerance * 0.50:
        blockers.append("RMSE exceeds half the field tolerance")
    if median_absolute_error is None or median_absolute_error > tolerance * 0.35:
        blockers.append("median absolute error exceeds 35% of tolerance")
    if bounds_failures:
        blockers.append("decoded bounds failures present")
    if expected_mismatches:
        blockers.append("expected-value mismatches present")
    if unit_failures > max(1, pairs * 0.20):
        blockers.append("OCR unit/semantic failure rate exceeds 20%")
    if not blockers:
        return "CONFIRMATION_READY", "All strengthened local confirmation gates passed"
    if pairs >= 5 and effective_samples >= 3 and rate >= 0.70 and not bounds_failures:
        return "PROBABLE", "; ".join(blockers)
    if pairs >= 3 and rate < 0.20 and (bounds_failures or expected_mismatches or unit_failures):
        return "REJECTED", "; ".join(blockers)
    return "CANDIDATE", "; ".join(blockers) if blockers else "Insufficient independent evidence"


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def grade_session(decoded_path: Path, ocr_path: Path | None, correlation_path: Path,
                  grade_csv_path: Path, grade_json_path: Path, session: str,
                  *, max_lag_seconds: float = 5.0,
                  independence_bucket_seconds: float = 2.0) -> dict[str, Any]:
    decoded = _rows(decoded_path)
    ocr = _rows(ocr_path) if ocr_path else []
    ocr_times: list[tuple[float, dict[str, str]]] = []
    for row in ocr:
        try:
            ocr_times.append((float(row.get("Video_s", "")), row))
        except ValueError:
            continue

    grouped_decoded: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in decoded:
        key = (row.get("Profile", ""), row.get("DecoderKey", ""), row.get("Field", ""),
               row.get("ArrayIndex", ""), row.get("Unit", ""))
        grouped_decoded[key].append(row)

    correlations: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    unit_failures_by_key: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for key, samples in grouped_decoded.items():
        usable_can = []
        labels: list[str] = []
        for row in samples:
            labels.extend(value for value in row.get("OCRLabels", "").split(";") if value)
            try:
                usable_can.append((float(row["Video_s"]), float(row["Value"]), row))
            except (KeyError, ValueError):
                continue
        labels = list(dict.fromkeys(labels))
        if not labels or not usable_can:
            continue

        observations: list[tuple[float, dict[str, str], str, float]] = []
        seen_observations: set[tuple[str, str]] = set()
        for ocr_time, ocr_row in ocr_times:
            text = ocr_row.get("Text", "")
            for label in labels:
                if not _label_match(text, label):
                    continue
                value = _number_after_label(text, label, key[4])
                if value is None:
                    unit_failures_by_key[key] += 1
                    rejected.append({
                        "Profile": key[0], "DecoderKey": key[1], "Field": key[2],
                        "ArrayIndex": key[3], "Unit": key[4], "OCRVideo_s": f"{ocr_time:.6f}",
                        "OCRFrame": ocr_row.get("Frame", ""), "OCRLabel": label,
                        "DetectedApp": ocr_row.get("DetectedApp", ""),
                        "DetectedLayout": ocr_row.get("DetectedLayout", ""),
                        "Reason": "Label present but expected numeric value/unit was not safely parsed",
                    })
                    continue
                observation_key = (ocr_row.get("Frame", f"{ocr_time:.6f}"), label)
                if observation_key not in seen_observations:
                    observations.append((ocr_time, ocr_row, label, value))
                    seen_observations.add(observation_key)

        def assign(fixed_lag: float) -> list[tuple[int, int]]:
            available = set(range(len(usable_can)))
            result = []
            pairing_window = min(1.25, max_lag_seconds)
            for observation_index, (ocr_time, _, _, _) in enumerate(observations):
                target = ocr_time + fixed_lag
                candidates = [
                    (abs(usable_can[index][0] - target), index) for index in available
                    if abs(usable_can[index][0] - target) <= pairing_window]
                if candidates:
                    _, can_index = min(candidates)
                    available.remove(can_index)
                    result.append((observation_index, can_index))
            return result

        lag_limit_steps = int(min(3.0, max_lag_seconds) / 0.05)
        selection_tolerance = next((
            float(row["OCRTolerance"]) for _, _, row in usable_can
            if row.get("OCRTolerance")), _default_tolerance(key[4]))
        lag_candidates = []
        for step in range(-lag_limit_steps, lag_limit_steps + 1):
            fixed_lag = step * 0.05
            candidate_assignments = assign(fixed_lag)
            candidate_errors = [
                abs(usable_can[can_index][1] - observations[observation_index][3])
                for observation_index, can_index in candidate_assignments]
            agreement_rate = (sum(value <= selection_tolerance for value in candidate_errors)
                              / len(candidate_errors) if candidate_errors else 0.0)
            score = ((statistics.median(candidate_errors) if candidate_errors else math.inf),
                     -agreement_rate,
                     (math.sqrt(sum(value * value for value in candidate_errors)
                                / len(candidate_errors)) if candidate_errors else math.inf),
                     -len(candidate_assignments), abs(fixed_lag))
            lag_candidates.append((score, fixed_lag, candidate_assignments))
        _, selected_fixed_lag, assignments = min(lag_candidates, key=lambda item: item[0])

        for observation_index, can_index in sorted(assignments):
            ocr_time, ocr_row, label, ocr_value = observations[observation_index]
            can_time, can_value, can_row = usable_can[can_index]
            tolerance = (float(can_row["OCRTolerance"]) if can_row.get("OCRTolerance")
                         else _default_tolerance(key[4]))
            error = can_value - ocr_value
            correlations.append({
                "Session": session, "Profile": key[0], "DecoderKey": key[1],
                "Field": key[2], "ArrayIndex": key[3], "Unit": key[4],
                "CANVideo_s": f"{can_time:.6f}", "OCRVideo_s": f"{ocr_time:.6f}",
                "Lag_s": f"{ocr_time - can_time:.6f}", "CANValue": f"{can_value:.9g}",
                "OCRValue": f"{ocr_value:.9g}", "Error": f"{error:.9g}",
                "AbsoluteError": f"{abs(error):.9g}", "Tolerance": f"{tolerance:.9g}",
                "Agreement": abs(error) <= tolerance, "OCRLabel": label,
                "OCRFrame": ocr_row.get("Frame", ""),
                "DetectedApp": ocr_row.get("DetectedApp", ""),
                "DetectedLayout": ocr_row.get("DetectedLayout", ""),
                "PairingMethod": "FIXED_LAG_ONE_TO_ONE",
                "SelectedFixedLag_s": f"{selected_fixed_lag:.3f}",
                "TimeBucket": int(ocr_time // independence_bucket_seconds),
            })

    correlations.sort(key=lambda row: (
        row["Profile"], row["DecoderKey"], row["Field"], row["ArrayIndex"],
        float(row["OCRVideo_s"])))
    _write_csv(correlation_path, CORRELATION_COLUMNS, correlations)
    _write_csv(grade_csv_path.parent / "OCR_REJECTED_SEMANTICS.csv", REJECTED_COLUMNS, rejected)
    _write_csv(grade_csv_path.parent / "CAN_OCR_OUTLIERS.csv", CORRELATION_COLUMNS,
               [row for row in correlations if not row["Agreement"]])

    grouped_correlations: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in correlations:
        grouped_correlations[(row["Profile"], row["DecoderKey"], row["Field"],
                              row["ArrayIndex"], row["Unit"])].append(row)

    grades = []
    grade_rank = {"REJECTED": 0, "CANDIDATE": 1, "PROBABLE": 2, "CONFIRMED": 3}
    for key, samples in sorted(grouped_decoded.items()):
        matched = grouped_correlations.get(key, [])
        errors = [float(row["Error"]) for row in matched]
        abs_errors = [abs(value) for value in errors]
        lags = [float(row["Lag_s"]) for row in matched]
        can_values = [float(row["CANValue"]) for row in matched]
        ocr_times_for_field = [float(row["OCRVideo_s"]) for row in matched]
        agreements = sum(str(row["Agreement"]).lower() == "true" for row in matched)
        bounds_failures = sum(row.get("BoundsStatus", "").startswith("FAIL") for row in samples)
        expected_mismatches = sum(row.get("ExpectedStatus") == "MISMATCH" for row in samples)
        tolerance = (statistics.median([float(row["Tolerance"]) for row in matched])
                     if matched else _default_tolerance(key[4]))
        rmse = math.sqrt(sum(value * value for value in errors) / len(errors)) if errors else None
        median_error = statistics.median(abs_errors) if abs_errors else None
        frames = {row["OCRFrame"] or row["OCRVideo_s"] for row in matched}
        buckets = {row["TimeBucket"] for row in matched}
        time_span = ((max(ocr_times_for_field) - min(ocr_times_for_field))
                     if len(ocr_times_for_field) > 1 else 0.0)
        dynamic_range = max(can_values) - min(can_values) if len(can_values) > 1 else 0.0
        sessions = {row.get("SourceSession", "") for row in samples if row.get("SourceSession")}
        local_grade, reason = _decision(
            pairs=len(matched), unique_frames=len(frames), effective_samples=len(buckets),
            agreements=agreements, bounds_failures=bounds_failures,
            expected_mismatches=expected_mismatches,
            unit_failures=unit_failures_by_key[key], rmse=rmse,
            median_absolute_error=median_error, tolerance=tolerance, time_span=time_span,
            dynamic_range=dynamic_range, unit=key[4])
        grade = {
            "Profile": key[0], "DecoderKey": key[1], "Field": key[2],
            "ArrayIndex": key[3], "Unit": key[4], "DecodedSamples": len(samples),
            "OCRPairs": len(matched), "UniqueOCRFrames": len(frames),
            "EffectiveIndependentSamples": len(buckets), "Agreements": agreements,
            "AgreementRate": f"{agreements / len(matched):.6f}" if matched else "",
            "RMSE": f"{rmse:.9g}" if rmse is not None else "",
            "MedianAbsoluteError": f"{median_error:.9g}" if median_error is not None else "",
            "MedianLag_s": f"{statistics.median(lags):.6f}" if lags else "",
            "TimeSpan_s": f"{time_span:.6f}", "DynamicRange": f"{dynamic_range:.9g}",
            "BoundsFailures": bounds_failures, "ExpectedMismatches": expected_mismatches,
            "UnitCheckFailures": unit_failures_by_key[key],
            "Outliers": len(matched) - agreements, "IndependentSessions": len(sessions),
            "DatabaseEvidenceGrade": max(
                (row.get("EvidenceGrade", "CANDIDATE") for row in samples),
                key=lambda value: grade_rank.get(value, 0)),
            "PreliminaryLocalGrade": local_grade, "DecisionReason": reason,
        }
        grades.append(grade)

    _write_csv(grade_csv_path, GRADE_COLUMNS, grades)
    _write_csv(grade_csv_path.parent / "DATABASE_FIELD_DECISIONS.csv", GRADE_COLUMNS, grades)
    labeled_decoded_rows = sum(bool(row.get("OCRLabels")) for row in decoded)
    if correlations:
        zero_pair_diagnosis = "NOT_APPLICABLE"
    elif not decoded:
        zero_pair_diagnosis = "NO_DECODED_FIELD_ROWS"
    elif not ocr:
        zero_pair_diagnosis = "NO_OCR_ROWS"
    elif not labeled_decoded_rows:
        zero_pair_diagnosis = "NO_DATABASE_OCR_LABELS_FOR_DECODED_FIELDS"
    elif rejected:
        zero_pair_diagnosis = "LABELS_FOUND_BUT_VALUES_OR_UNITS_REJECTED"
    else:
        zero_pair_diagnosis = "NO_SAFE_LABEL_VALUE_OVERLAP_WITHIN_TIME_WINDOW"
    summary = {
        "session": session, "decoded_rows": len(decoded), "ocr_rows": len(ocr),
        "matching_method": "PER_FIELD_FIXED_LAG_ONE_TO_ONE",
        "max_lag_seconds": max_lag_seconds,
        "independence_bucket_seconds": independence_bucket_seconds,
        "can_ocr_pairs": len(correlations),
        "decoded_rows_with_ocr_labels": labeled_decoded_rows,
        "zero_pair_diagnosis": zero_pair_diagnosis,
        "unique_ocr_frames": len({row["OCRFrame"] or row["OCRVideo_s"] for row in correlations}),
        "effective_independent_samples": len({
            (row["DecoderKey"], row["Field"], row["ArrayIndex"], row["TimeBucket"])
            for row in correlations}),
        "agreements": sum(str(row["Agreement"]).lower() == "true" for row in correlations),
        "outliers": sum(str(row["Agreement"]).lower() != "true" for row in correlations),
        "rejected_semantic_observations": len(rejected),
        "bounds_failures": sum(int(row["BoundsFailures"]) for row in grades),
        "expected_mismatches": sum(int(row["ExpectedMismatches"]) for row in grades),
        "grade_rows": len(grades),
        "confirmation_ready_rows": sum(
            row["PreliminaryLocalGrade"] == "CONFIRMATION_READY" for row in grades),
        "confirmation_policy": {
            "minimum_pairs": 20, "minimum_unique_ocr_frames": 20,
            "minimum_independent_time_buckets": 12, "minimum_time_span_seconds": 30,
            "minimum_agreement_rate": 0.90,
            "rmse_maximum_fraction_of_tolerance": 0.50,
            "median_absolute_error_maximum_fraction_of_tolerance": 0.35,
            "dynamic_range_required": True,
        },
        "policy": (
            "Preliminary local grades never modify the versioned decoder database or promote a "
            "definition to CONFIRMED. Independent evidence review remains required."
        ),
    }
    grade_json_path.write_text(json.dumps({"summary": summary, "grades": grades}, indent=2),
                               encoding="utf-8")
    return summary
