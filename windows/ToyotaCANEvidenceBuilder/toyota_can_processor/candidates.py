from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .database import find_definition
from .diagnostics import READ_ONLY_SERVICES, Transaction


def write_signal_candidates(path: Path, transactions: list[Transaction], profile: str,
                            database: dict[str, Any]) -> dict[str, Any]:
    groups: dict[tuple[int, int, int, int | None, int], list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        request = transaction.request
        if (request is None or transaction.response_id is None or transaction.status != "OK"
                or request.service not in READ_ONLY_SERVICES):
            continue
        if find_definition(database, profile, request.can_id, request.service, request.pid):
            continue
        groups[(request.can_id, transaction.response_id, request.service,
                request.pid, len(transaction.response_payload))].append(transaction)

    candidates = []
    for (request_id, response_id, service, pid, length), rows in sorted(groups.items()):
        payloads = [row.response_payload.hex().upper() for row in rows]
        identity_payload_omitted = service == 0x09 and pid == 0x02
        candidates.append({
            "profile": profile,
            "request_id": f"{request_id:03X}",
            "response_id": f"{response_id:03X}",
            "service": f"{service:02X}",
            "pid": f"{pid:02X}" if pid is not None else None,
            "response_length_bytes": length,
            "response_prefix": payloads[0][:4] if payloads else "",
            "observed_transactions": len(rows),
            "distinct_payloads": len(set(payloads)),
            "sample_response_payloads": [] if identity_payload_omitted else sorted(set(payloads))[:3],
            "identity_payload_omitted": identity_payload_omitted,
            "suggested_decoder": "response_signature",
            "evidence_grade": "CANDIDATE",
            "safety_class": "READ_ONLY_DIAGNOSTIC",
            "automatic_promotion_allowed": False,
            "next_evidence": (
                "Review the masked identity export; raw VIN response samples are deliberately omitted."
                if identity_payload_omitted else
                "Correlate labeled physical values across an independent session before assigning fields or formulas."
            ),
        })
    result = {
        "profile": profile,
        "candidate_count": len(candidates),
        "policy": "Candidates are observed read-only responses, not approved decoder definitions.",
        "candidates": candidates,
    }
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"candidate_count": len(candidates)}
