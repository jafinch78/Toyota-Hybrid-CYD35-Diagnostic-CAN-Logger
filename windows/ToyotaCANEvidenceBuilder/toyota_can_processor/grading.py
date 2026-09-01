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
]

GRADE_COLUMNS = [
    "Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "DecodedSamples",
    "OCRPairs", "Agreements", "AgreementRate", "RMSE", "MedianAbsoluteError",
    "MedianLag_s", "BoundsFailures", "ExpectedMismatches", "IndependentSessions",
    "DatabaseEvidenceGrade", "PreliminaryLocalGrade",
]


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        return list(csv.DictReader(stream))


def _number_after_label(text: str, label: str, unit: str = "") -> float | None:
    label_match = re.search(
        rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])",
        text,
        flags=re.IGNORECASE,
    )
    if not label_match:
        return None
    # AP200 list OCR often captures the row label while the value is still blank.
    # Keep the search local to that row and, when possible, require the displayed
    # unit.  This prevents GUI text such as ``Save ESC [1`` from becoming a false
    # block-voltage value after a label ending in V01/V02/etc.
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
        "s": r"(?:sec(?:ond)?s?|[sS])",
    }
    number = r"[-+]?\d+(?:\.\d+)?"
    if unit in unit_patterns:
        after = re.search(rf"(?P<value>{number})\s*{unit_patterns[unit]}", tail)
        before = re.search(rf"{unit_patterns[unit]}\s*(?P<value>{number})", tail)
        matches = [item for item in (after, before) if item]
        match = min(matches, key=lambda item: item.start()) if matches else None
    else:
        match = re.search(rf"(?P<value>{number})", tail)
    if not match:
        return None
    if "save" in tail[:match.start()].lower():
        return None
    try:
        return float(match.group("value"))
    except ValueError:
        return None


def _default_tolerance(unit: str) -> float:
    return {
        "V": 0.06, "A": 0.25, "ohm": 0.0011, "%": 0.6,
        "degC": 0.8, "kW": 0.8, "rpm": 150.0, "s": 2.0,
        "1-based block": 0.1,
    }.get(unit, 0.1)


def _preliminary(pairs: int, agreements: int, bounds_failures: int,
                 rmse: float | None, tolerance: float) -> str:
    rate = agreements / pairs if pairs else 0.0
    if bounds_failures and pairs >= 3 and rate < 0.2:
        return "REJECTED"
    if pairs >= 3 and rate >= 0.8 and bounds_failures == 0 and rmse is not None and rmse <= tolerance:
        return "CONFIRMATION_READY"
    if pairs >= 1 and rate >= 0.5:
        return "PROBABLE"
    return "CANDIDATE"


def grade_session(decoded_path: Path, ocr_path: Path | None, correlation_path: Path,
                  grade_csv_path: Path, grade_json_path: Path, session: str,
                  *, max_lag_seconds: float = 5.0) -> dict[str, Any]:
    decoded = _rows(decoded_path)
    ocr = _rows(ocr_path) if ocr_path else []
    ocr_times = []
    for row in ocr:
        try:
            ocr_times.append((float(row.get("Video_s", "")), row))
        except ValueError:
            continue

    correlations: list[dict[str, Any]] = []
    grouped_decoded: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in decoded:
        key = (row.get("Profile", ""), row.get("DecoderKey", ""), row.get("Field", ""),
               row.get("ArrayIndex", ""), row.get("Unit", ""))
        grouped_decoded[key].append(row)
        labels = [value for value in row.get("OCRLabels", "").split(";") if value]
        if not labels:
            continue
        try:
            can_time = float(row["Video_s"])
            can_value = float(row["Value"])
        except (KeyError, ValueError):
            continue
        candidates: list[tuple[float, dict[str, str], str, float]] = []
        for ocr_time, ocr_row in ocr_times:
            lag = ocr_time - can_time
            if abs(lag) > max_lag_seconds:
                continue
            text = ocr_row.get("Text", "")
            for label in labels:
                value = _number_after_label(text, label, row.get("Unit", ""))
                if value is not None:
                    candidates.append((abs(lag), ocr_row, label, value))
        if not candidates:
            continue
        _, ocr_row, label, ocr_value = min(candidates, key=lambda item: item[0])
        ocr_time = float(ocr_row["Video_s"])
        tolerance = float(row["OCRTolerance"]) if row.get("OCRTolerance") else _default_tolerance(row.get("Unit", ""))
        error = can_value - ocr_value
        correlations.append({
            "Session": session, "Profile": row.get("Profile", ""),
            "DecoderKey": row.get("DecoderKey", ""), "Field": row.get("Field", ""),
            "ArrayIndex": row.get("ArrayIndex", ""), "Unit": row.get("Unit", ""),
            "CANVideo_s": f"{can_time:.6f}", "OCRVideo_s": f"{ocr_time:.6f}",
            "Lag_s": f"{ocr_time - can_time:.6f}", "CANValue": f"{can_value:.9g}",
            "OCRValue": f"{ocr_value:.9g}", "Error": f"{error:.9g}",
            "AbsoluteError": f"{abs(error):.9g}", "Tolerance": f"{tolerance:.9g}",
            "Agreement": abs(error) <= tolerance, "OCRLabel": label,
            "OCRFrame": ocr_row.get("Frame", ""),
        })

    with correlation_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CORRELATION_COLUMNS)
        writer.writeheader()
        writer.writerows(correlations)

    grouped_correlations: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in correlations:
        key = (row["Profile"], row["DecoderKey"], row["Field"], row["ArrayIndex"], row["Unit"])
        grouped_correlations[key].append(row)

    grades = []
    for key, samples in sorted(grouped_decoded.items()):
        matched = grouped_correlations.get(key, [])
        errors = [float(row["Error"]) for row in matched]
        abs_errors = [abs(value) for value in errors]
        lags = [float(row["Lag_s"]) for row in matched]
        agreements = sum(str(row["Agreement"]).lower() == "true" for row in matched)
        bounds_failures = sum(row.get("BoundsStatus", "").startswith("FAIL") for row in samples)
        expected_mismatches = sum(row.get("ExpectedStatus") == "MISMATCH" for row in samples)
        tolerance = statistics.median([float(row["Tolerance"]) for row in matched]) \
            if matched else _default_tolerance(key[4])
        rmse = math.sqrt(sum(value * value for value in errors) / len(errors)) if errors else None
        sessions = {row.get("SourceSession", "") for row in samples if row.get("SourceSession")}
        database_grades = [row.get("EvidenceGrade", "CANDIDATE") for row in samples]
        grade = {
            "Profile": key[0], "DecoderKey": key[1], "Field": key[2],
            "ArrayIndex": key[3], "Unit": key[4], "DecodedSamples": len(samples),
            "OCRPairs": len(matched), "Agreements": agreements,
            "AgreementRate": f"{agreements / len(matched):.6f}" if matched else "",
            "RMSE": f"{rmse:.9g}" if rmse is not None else "",
            "MedianAbsoluteError": f"{statistics.median(abs_errors):.9g}" if abs_errors else "",
            "MedianLag_s": f"{statistics.median(lags):.6f}" if lags else "",
            "BoundsFailures": bounds_failures, "ExpectedMismatches": expected_mismatches,
            "IndependentSessions": len(sessions),
            "DatabaseEvidenceGrade": max(database_grades, key=lambda value: {
                "REJECTED": 0, "CANDIDATE": 1, "PROBABLE": 2, "CONFIRMED": 3,
            }.get(value, 0)),
            "PreliminaryLocalGrade": _preliminary(len(matched), agreements, bounds_failures,
                                                   rmse, tolerance),
        }
        grades.append(grade)

    with grade_csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=GRADE_COLUMNS)
        writer.writeheader()
        writer.writerows(grades)
    summary = {
        "session": session,
        "decoded_rows": len(decoded),
        "ocr_rows": len(ocr),
        "can_ocr_pairs": len(correlations),
        "agreements": sum(str(row["Agreement"]).lower() == "true" for row in correlations),
        "bounds_failures": sum(int(row["BoundsFailures"]) for row in grades),
        "expected_mismatches": sum(int(row["ExpectedMismatches"]) for row in grades),
        "grade_rows": len(grades),
        "confirmation_ready_rows": sum(row["PreliminaryLocalGrade"] == "CONFIRMATION_READY" for row in grades),
        "policy": (
            "Preliminary local grades never modify the versioned decoder database or promote a "
            "definition to CONFIRMED. Independent evidence review remains required."
        ),
    }
    grade_json_path.write_text(json.dumps({"summary": summary, "grades": grades}, indent=2),
                               encoding="utf-8")
    return summary
