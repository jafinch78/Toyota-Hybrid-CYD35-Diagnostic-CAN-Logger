from __future__ import annotations

from collections import defaultdict
from typing import Any

from .database import canonical_profile


def _matches(signature: dict[str, Any], transaction: Any) -> bool:
    request = transaction.request
    if request is None or transaction.status != "OK" or transaction.response_id is None:
        return False
    if int(str(signature.get("request_id", "0")), 16) != request.can_id:
        return False
    if "service" in signature and int(str(signature["service"]), 16) != request.service:
        return False
    if "pid" in signature:
        if request.pid is None or int(str(signature["pid"]), 16) != request.pid:
            return False
    if "response_id" in signature and int(str(signature["response_id"]), 16) != transaction.response_id:
        return False
    if "request_payload" in signature and request.payload.hex().upper() != str(signature["request_payload"]).upper():
        return False
    payload = transaction.response_payload
    if "response_length_bytes" in signature and len(payload) != int(signature["response_length_bytes"]):
        return False
    if "response_prefix" in signature and not payload.startswith(bytes.fromhex(str(signature["response_prefix"]))):
        return False
    ascii_contains = signature.get("response_ascii_contains")
    if ascii_contains:
        text = "".join(chr(value) if 32 <= value <= 126 else " " for value in payload)
        if str(ascii_contains) not in text:
            return False
    return True


def detect_vehicle_profile(transactions: list[Any], database: dict[str, Any],
                           manifest_profile: str | None) -> dict[str, Any]:
    original = canonical_profile(manifest_profile)
    scores: dict[str, int] = defaultdict(int)
    evidence: list[dict[str, Any]] = []
    authoritative: set[str] = set()
    for signature in database.get("profile_signatures", []):
        profile = canonical_profile(signature.get("profile"))
        matches = [transaction for transaction in transactions if _matches(signature, transaction)]
        if not matches:
            continue
        weight = int(signature.get("detector_weight", 0))
        scores[profile] += weight
        if signature.get("authoritative") and signature.get("evidence_grade") == "CONFIRMED":
            authoritative.add(profile)
        evidence.append({
            "profile": profile,
            "request_id": str(signature.get("request_id", "")),
            "service": str(signature.get("service", "")),
            "pid": str(signature.get("pid", "")),
            "response_id": str(signature.get("response_id", "")),
            "match_count": len(matches),
            "weight": weight,
            "evidence_grade": str(signature.get("evidence_grade", "CANDIDATE")),
            "authoritative": bool(signature.get("authoritative")),
            "basis": "ASCII_MODEL_SIGNATURE" if signature.get("response_ascii_contains") else "RESPONSE_SIGNATURE",
            "ascii_contains": str(signature.get("response_ascii_contains", "")),
        })

    winner = max(scores, key=scores.get) if scores else original
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    margin = ordered[0][1] - ordered[1][1] if len(ordered) > 1 else (ordered[0][1] if ordered else 0)
    decision = "MANIFEST_RETAINED"
    selected = original
    confidence = 0
    if len(authoritative) == 1:
        selected = next(iter(authoritative))
        confidence = 100
        decision = "AUTHORITATIVE_MODEL_SIGNATURE"
    elif winner and scores.get(winner, 0) >= 80 and margin >= 20:
        selected = winner
        total = sum(scores.values()) or 1
        confidence = min(99, round(scores[winner] / total * 100))
        decision = "DATABASE_SIGNATURE_EVIDENCE"
    elif original and original != "UNKNOWN":
        confidence = 50
    elif winner:
        selected = winner
        confidence = 50
        decision = "WEAK_SIGNATURE_EVIDENCE"

    conflict = bool(original and original != "UNKNOWN" and selected != original)
    contradictions = []
    if conflict:
        contradictions.append({
            "type": "MANIFEST_PROFILE_CONFLICT",
            "manifest_profile": original,
            "evidence_profile": selected,
            "resolution": decision,
        })
    return {
        "manifest_profile": original,
        "selected_profile": selected or "UNKNOWN",
        "profile_conflict": conflict,
        "decision": decision,
        "confidence_pct": confidence,
        "scores": dict(sorted(scores.items())),
        "positive_evidence": evidence,
        "contradictory_evidence": contradictions,
    }
