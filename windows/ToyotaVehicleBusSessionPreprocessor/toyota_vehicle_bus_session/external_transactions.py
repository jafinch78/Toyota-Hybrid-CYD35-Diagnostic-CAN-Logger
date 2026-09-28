from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .diagnostics import ExternalDiagnosticFrame, classify_external_diagnostic_frames
from .isotp import IsoTpAssembler
from .tcb1 import TcbFrame


@dataclass(frozen=True)
class ExternalDiagnosticTransaction:
    request_time_us: int | None
    response_start_us: int | None
    complete_time_us: int | None
    request_id: int | None
    response_id: int | None
    service: int | None
    pid: int | None
    status: str
    payload: bytes
    frame_count: int
    missing_sequences: int
    response_time_ms: float | None


@dataclass
class _Request:
    time_us: int
    can_id: int
    service: int
    pid: int | None
    matched: bool = False


def _parse_request(frame: ExternalDiagnosticFrame) -> _Request | None:
    data = frame.data
    if not data or data[0] >> 4 != 0:
        return None
    length = data[0] & 0x0F
    if length < 1 or length > len(data) - 1:
        return None
    payload = data[1 : 1 + length]
    service = payload[0]
    pid = payload[1] if len(payload) >= 2 else None
    return _Request(frame.time_us, frame.can_id, service, pid)


def _expected_response(request_id: int, response_id: int) -> bool:
    if request_id == 0x7DF:
        return 0x7E8 <= response_id <= 0x7EF
    return response_id == request_id + 8


def _response_matches(request: _Request, response_id: int, payload: bytes) -> bool:
    if not payload or not _expected_response(request.can_id, response_id):
        return False
    if payload[0] == 0x7F:
        return len(payload) >= 2 and payload[1] == request.service
    if payload[0] != ((request.service + 0x40) & 0xFF):
        return False
    if request.pid is None or request.service == 0x13:
        return True
    return len(payload) >= 2 and payload[1] == request.pid


def reconstruct_external_transactions(
    frames: Iterable[TcbFrame],
) -> tuple[ExternalDiagnosticTransaction, ...]:
    """Reconstruct external-tester ISO-TP transactions from authoritative raw CAN.

    Logger-owned TX traffic is excluded by the existing external-frame classifier.
    The returned transactions therefore describe only tester traffic observed on RX.
    """
    external = classify_external_diagnostic_frames(frames)
    requests: list[_Request] = []
    assemblers: dict[int, IsoTpAssembler] = {}
    response_start: dict[int, int] = {}
    completed: list[ExternalDiagnosticTransaction] = []

    def finish(response_id: int, start_us: int, complete_us: int, payload: bytes,
               frame_count: int, status: str, missing_sequences: int) -> None:
        request = next(
            (
                candidate
                for candidate in reversed(requests)
                if not candidate.matched and _response_matches(candidate, response_id, payload)
            ),
            None,
        )
        if request is not None:
            request.matched = True
        final_status = "UNMATCHED_RESPONSE" if request is None else status
        completed.append(
            ExternalDiagnosticTransaction(
                request_time_us=request.time_us if request else None,
                response_start_us=start_us,
                complete_time_us=complete_us,
                request_id=request.can_id if request else None,
                response_id=response_id,
                service=request.service if request else None,
                pid=request.pid if request else None,
                status=final_status,
                payload=payload,
                frame_count=frame_count,
                missing_sequences=missing_sequences,
                response_time_ms=(complete_us - request.time_us) / 1000.0 if request else None,
            )
        )

    for item in external:
        if item.classification == "EXTERNAL_REQUEST":
            request = _parse_request(item)
            if request is not None:
                requests.append(request)
            continue
        if item.classification != "EXTERNAL_RESPONSE" or not item.data:
            continue

        response_id = item.can_id
        pci = item.data[0] >> 4
        if pci in (0, 1):
            response_start[response_id] = item.time_us
            assemblers[response_id] = IsoTpAssembler()
        assembler = assemblers.get(response_id)
        if assembler is None:
            assembler = IsoTpAssembler()
            assemblers[response_id] = assembler
            response_start.setdefault(response_id, item.time_us)

        result = assembler.feed(item.time_us, response_id, item.data, item.dlc)
        if result is None:
            continue
        missing = 1 if result.status == "INCOMPLETE_SEQUENCE" else 0
        finish(
            response_id,
            response_start.pop(response_id, item.time_us),
            result.complete_time_us,
            result.payload,
            result.frame_count,
            result.status,
            missing,
        )
        assemblers.pop(response_id, None)

    for response_id, assembler in list(assemblers.items()):
        if not assembler.active:
            continue
        payload = bytes(assembler.payload[: assembler.expected_length])
        finish(
            response_id,
            response_start.get(response_id, 0),
            response_start.get(response_id, 0),
            payload,
            assembler.frame_count,
            "INCOMPLETE_SEQUENCE",
            1,
        )

    for request in requests:
        if request.matched:
            continue
        completed.append(
            ExternalDiagnosticTransaction(
                request_time_us=request.time_us,
                response_start_us=None,
                complete_time_us=None,
                request_id=request.can_id,
                response_id=None,
                service=request.service,
                pid=request.pid,
                status="NO_RESPONSE",
                payload=b"",
                frame_count=0,
                missing_sequences=0,
                response_time_ms=None,
            )
        )

    return tuple(completed)
