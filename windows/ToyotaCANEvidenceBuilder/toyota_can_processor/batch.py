from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class Pairing:
    logger: str | None
    companion: str | None
    session: int | None
    basis: str
    warnings: list[str]
    status: str = "READY"
    candidate_loggers: list[str] | None = None
    duplicate_archives: list[str] | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zip_json(path: Path, suffix: str) -> list[tuple[str, dict[str, Any]]]:
    results = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.upper().endswith(suffix.upper()):
                    try:
                        results.append((name, json.loads(archive.read(name).decode("utf-8-sig"))))
                    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
                        continue
    except (OSError, zipfile.BadZipFile):
        return []
    return results


def _session_from_capture(capture: dict[str, Any]) -> int | None:
    for event in capture.get("control_events", []):
        if event.get("operation") == "START_PASSIVE" and int(event.get("status", 1)) == 0:
            try:
                return int(event.get("cyd_session", 0)) or None
            except (TypeError, ValueError):
                return None
    return None


def discover_pairs(input_root: Path) -> list[Pairing]:
    archives = sorted(path for path in input_root.rglob("*.zip") if path.is_file())
    hashes: dict[str, list[Path]] = {}
    for path in archives:
        hashes.setdefault(_sha256(path), []).append(path)
    canonical_archives = [paths[0] for paths in hashes.values()]
    duplicates = {
        paths[0]: [str(item) for item in paths[1:]]
        for paths in hashes.values() if len(paths) > 1
    }
    loggers: dict[Path, set[int]] = {}
    captures: list[tuple[Path, int | None]] = []
    for path in sorted(canonical_archives):
        manifests = _zip_json(path, "MANIFEST.JSON")
        if manifests:
            sessions = set()
            for name, _ in manifests:
                parent = Path(name).parent.name.upper()
                if parent.startswith("S") and parent[1:].isdigit():
                    sessions.add(int(parent[1:]))
            loggers[path] = sessions
            continue
        capture_rows = _zip_json(path, "CAPTURE_SYNC.JSON")
        if capture_rows:
            captures.append((path, _session_from_capture(capture_rows[0][1])))

    pairs: list[Pairing] = []
    used_sessions: set[tuple[Path, int]] = set()
    for capture, session in captures:
        matches = [path for path, sessions in loggers.items() if session is not None and session in sessions]
        warnings = []
        duplicate_archives = duplicates.get(capture, [])
        if duplicate_archives:
            warnings.append(
                f"Ignored {len(duplicate_archives)} byte-identical duplicate capture archive(s) by SHA-256")
        if not matches:
            warnings.append(f"No CANLOG archive contains BLE session S{session:04d}" if session else
                            "CAPTURE_SYNC has no successful START_PASSIVE session")
            continue
        if len(matches) > 1:
            warnings.append(
                "Multiple distinct CANLOG archives contain the selected session; reviewer selection is required")
            for logger in matches:
                if session is not None:
                    used_sessions.add((logger, session))
            pairs.append(Pairing(
                None, str(capture), session, "AMBIGUOUS_BLE_SESSION_MATCH", warnings,
                status="AMBIGUOUS", candidate_loggers=[str(item) for item in matches],
                duplicate_archives=duplicate_archives,
            ))
            continue
        logger = matches[0]
        logger_duplicates = duplicates.get(logger, [])
        if logger_duplicates:
            warnings.append(
                f"Ignored {len(logger_duplicates)} byte-identical duplicate CANLOG archive(s) by SHA-256")
            duplicate_archives.extend(logger_duplicates)
        if session is not None:
            used_sessions.add((logger, session))
        pairs.append(Pairing(
            str(logger), str(capture), session, "BLE_START_PASSIVE_SESSION", warnings,
            duplicate_archives=duplicate_archives))
    for logger, sessions in loggers.items():
        matched = {session for path, session in used_sessions if path == logger}
        if not matched:
            session = next(iter(sessions)) if len(sessions) == 1 else None
            pairs.append(Pairing(
                str(logger), None, session, "LOGGER_ONLY_UNPAIRED",
                ["No matching capture ZIP was found; media alignment is unavailable"],
                duplicate_archives=duplicates.get(logger, [])))
        else:
            for session in sorted(sessions - matched):
                pairs.append(Pairing(
                    str(logger), None, session, "LOGGER_SESSION_UNPAIRED",
                    [f"No matching capture ZIP was found for S{session:04d}; media alignment is unavailable"],
                    duplicate_archives=duplicates.get(logger, []),
                ))
    return pairs


def _aggregate_grades(outputs: list[Path], target: Path) -> int:
    groups: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for output in outputs:
        for path in output.rglob("EVIDENCE_GRADING.csv"):
            session = path.parent.name
            with path.open("r", newline="", encoding="utf-8-sig") as stream:
                for row in csv.DictReader(stream):
                    key = (row["Profile"], row["DecoderKey"], row["Field"],
                           row["ArrayIndex"], row["Unit"])
                    item = groups.setdefault(key, {
                        "Profile": key[0], "DecoderKey": key[1], "Field": key[2],
                        "ArrayIndex": key[3], "Unit": key[4], "DecodedSamples": 0,
                        "OCRPairs": 0, "UniqueOCRFrames": 0,
                        "EffectiveIndependentSamples": 0, "Agreements": 0,
                        "BoundsFailures": 0, "ExpectedMismatches": 0,
                        "UnitCheckFailures": 0, "Outliers": 0, "Sessions": set(),
                    })
                    for name in ("DecodedSamples", "OCRPairs", "UniqueOCRFrames",
                                 "EffectiveIndependentSamples", "Agreements", "BoundsFailures",
                                 "ExpectedMismatches", "UnitCheckFailures", "Outliers"):
                        item[name] += int(row.get(name, 0) or 0)
                    item["Sessions"].add(session)
    fields = ["Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "DecodedSamples",
              "OCRPairs", "UniqueOCRFrames", "EffectiveIndependentSamples", "Agreements",
              "AgreementRate", "BoundsFailures", "ExpectedMismatches", "UnitCheckFailures",
              "Outliers", "IndependentSessions"]
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in sorted(groups.values(), key=lambda row: (row["Profile"], row["DecoderKey"], row["Field"], row["ArrayIndex"])):
            pairs = item["OCRPairs"]
            item["AgreementRate"] = f"{item['Agreements'] / pairs:.6f}" if pairs else ""
            item["IndependentSessions"] = len(item.pop("Sessions"))
            writer.writerow(item)
    return len(groups)


def process_batch(input_root: Path, output_parent: Path, options: Any,
                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    from .processor import process

    progress = progress or (lambda message: None)
    pairs = discover_pairs(input_root.resolve())
    if not pairs:
        raise ValueError("No CANLOG ZIPs with MANIFEST.JSON were found in the batch folder")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_root = output_parent.resolve() / f"ToyotaCAN_Batch_{stamp}"
    batch_root.mkdir(parents=True, exist_ok=False)
    outputs: list[Path] = []
    results = []
    for index, pairing in enumerate(pairs, 1):
        if pairing.status != "READY" or not pairing.logger:
            progress(f"Batch {index}/{len(pairs)}: skipped {pairing.status} pairing for "
                     f"S{pairing.session:04d}" if pairing.session is not None else
                     f"Batch {index}/{len(pairs)}: skipped {pairing.status} pairing")
            results.append({**asdict(pairing), "output": None})
            continue
        session_label = f"S{pairing.session:04d}" if pairing.session is not None else "ALL"
        progress(f"Batch {index}/{len(pairs)}: {Path(pairing.logger).name} + "
                 f"{Path(pairing.companion).name if pairing.companion else 'no capture'}")
        result = process(
            Path(pairing.logger), batch_root,
            Path(pairing.companion) if pairing.companion else None,
            options=options, progress=progress, session_filter=pairing.session,
            output_name=f"Pair_{index:03d}_{session_label}",
        )
        outputs.append(Path(result["output"]))
        results.append({**asdict(pairing), "output": result["output"]})
    aggregate_rows = _aggregate_grades(outputs, batch_root / "BATCH_EVIDENCE_GRADING.csv")
    summary = {
        "processor_version": "1.0.4", "input_root": str(input_root.resolve()),
        "pair_count": sum(pair.status == "READY" for pair in pairs),
        "pairing_record_count": len(pairs),
        "ambiguous_pair_count": sum(pair.status == "AMBIGUOUS" for pair in pairs),
        "aggregate_grade_rows": aggregate_rows,
        "pairs": results,
    }
    (batch_root / "BATCH_PAIRING.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"output": str(batch_root), "summary": summary}
