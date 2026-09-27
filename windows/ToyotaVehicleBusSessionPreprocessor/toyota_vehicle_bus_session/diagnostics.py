from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .isotp import IsoTpAssembler
from .meta import MetaReadResult, decode_record_payload
from .schemas import DIAGNOSTICS_HEADER, EXTERNAL_DIAGNOSTICS_HEADER
from .tcb1 import TcbFrame

LOGGER_REQUEST_MIN = 0x7E0
LOGGER_REQUEST_MAX = 0x7E7
RESPONSE_MIN = 0x7E8
RESPONSE_MAX = 0x7EF
DEFAULT_LOGGER_TIMEOUT_US = 500_000


@dataclass(frozen=True)
class DiagnosticTransaction:
    request_time_us: int
    complete_time_us: int | None
    request_id: int
    response_id: int | None
    service: int | None
    pid: int | None
    status: str
    payload: bytes
    frame_count: int
    response_time_ms: float | None


@dataclass(frozen=True)
class ExternalDiagnosticFrame:
    time_us: int
    can_id: int
    dlc: int
    data: bytes
    classification: str


def _standard_data(frame: TcbFrame) -> bool:
    return frame.extended == 0 and frame.rtr == 0


def _pci_type(frame: TcbFrame) -> int | None:
    return None if frame.dlc < 1 else frame.data[0] >> 4


def _request_id(can_id: int) -> bool:
    return can_id == 0x7DF or LOGGER_REQUEST_MIN <= can_id <= LOGGER_REQUEST_MAX


def _logger_tx_request(frame: TcbFrame) -> bool:
    return (
        frame.direction == 1
        and _standard_data(frame)
        and frame.dlc >= 3
        and LOGGER_REQUEST_MIN <= frame.can_id <= LOGGER_REQUEST_MAX
        and _pci_type(frame) in (0, 1)
    )


def _external_request(frame: TcbFrame) -> bool:
    return (
        frame.direction == 0
        and _standard_data(frame)
        and frame.dlc >= 3
        and _request_id(frame.can_id)
        and _pci_type(frame) in (0, 1)
    )


def _request_service_pid(frame: TcbFrame) -> tuple[int | None, int | None]:
    pci = _pci_type(frame)
    if pci == 0 and frame.dlc >= 2:
        length = frame.data[0] & 0x0F
        service = frame.data[1] if length >= 1 else None
        pid = frame.data[2] if length >= 2 and frame.dlc >= 3 else None
        return service, pid
    if pci == 1 and frame.dlc >= 3:
        length = ((frame.data[0] & 0x0F) << 8) | frame.data[1]
        service = frame.data[2] if length >= 1 else None
        pid = frame.data[3] if length >= 2 and frame.dlc >= 4 else None
        return service, pid
    return None, None


def _expected_response_id(request_id: int) -> int | None:
    return request_id + 8 if LOGGER_REQUEST_MIN <= request_id <= LOGGER_REQUEST_MAX else None


def reconstruct_logger_diagnostics(
    frames: Iterable[TcbFrame],
    meta: MetaReadResult,
    *,
    timeout_us: int = DEFAULT_LOGGER_TIMEOUT_US,
) -> tuple[DiagnosticTransaction, ...]:
    results: list[DiagnosticTransaction] = []
    current: DiagnosticTransaction | None = None
    assembler: IsoTpAssembler | None = None
    expected_id: int | None = None

    def finish_no_response(status: str = "NO_RESPONSE") -> None:
        nonlocal current, assembler, expected_id
        if current is not None:
            results.append(replace(current, status=status))
        current = None
        assembler = None
        expected_id = None

    for frame in frames:
        if _logger_tx_request(frame):
            if current is not None:
                finish_no_response()
            service, pid = _request_service_pid(frame)
            current = DiagnosticTransaction(
                frame.time_us, None, frame.can_id, None, service, pid,
                "NO_RESPONSE", b"", 0, None,
            )
            assembler = IsoTpAssembler()
            expected_id = _expected_response_id(frame.can_id)
            continue

        if current is None:
            continue
        if frame.time_us - current.request_time_us > timeout_us and current.response_id is None:
            finish_no_response()
            continue
        if frame.direction != 0 or not _standard_data(frame) or frame.can_id != expected_id:
            continue
        if _pci_type(frame) not in (0, 1, 2):
            continue

        assert assembler is not None
        result = assembler.feed(frame.time_us, frame.can_id, frame.data, frame.dlc)
        if current.response_id is None:
            current = replace(current, response_id=frame.can_id)
        if result is not None:
            results.append(
                replace(
                    current,
                    complete_time_us=result.complete_time_us,
                    status=result.status,
                    payload=result.payload,
                    frame_count=result.frame_count,
                    response_time_ms=(result.complete_time_us - current.request_time_us) / 1000.0,
                )
            )
            current = None
            assembler = None
            expected_id = None

    if current is not None:
        finish_no_response()

    # Metadata may refine an already-observed logger transaction, but must not invent one.
    state_status = {
        3: "TIMEOUT",
        5: "INCOMPLETE_SEQUENCE",
        6: "EXTERNAL_INTERLOCK",
        7: "USER_DISABLED",
        8: "BUS_OFF",
    }
    state_records: list[tuple[int, str]] = []
    for record in meta.records:
        if record.record_type != 0x0031:
            continue
        try:
            code = decode_record_payload(record).get("state_code")
        except Exception:
            continue
        if code in state_status:
            state_records.append((record.time_us, state_status[code]))

    if state_records:
        mutable = list(results)
        used: set[int] = set()
        for time_us, status in state_records:
            candidate: int | None = None
            for index, transaction in enumerate(mutable):
                if index in used or transaction.status != "NO_RESPONSE" or transaction.request_time_us > time_us:
                    continue
                if candidate is None or transaction.request_time_us > mutable[candidate].request_time_us:
                    candidate = index
            if candidate is not None:
                transaction = mutable[candidate]
                mutable[candidate] = replace(
                    transaction,
                    status=status,
                    complete_time_us=time_us,
                    response_time_ms=(time_us - transaction.request_time_us) / 1000.0,
                )
                used.add(candidate)
        results = mutable

    return tuple(results)


def classify_external_diagnostic_frames(
    frames: Iterable[TcbFrame],
    *,
    hold_us: int = 5_000_000,
    logger_timeout_us: int = DEFAULT_LOGGER_TIMEOUT_US,
) -> tuple[ExternalDiagnosticFrame, ...]:
    output: list[ExternalDiagnosticFrame] = []
    last_external_request_us: int | None = None
    logger_claim_id: int | None = None
    logger_claim_started: int | None = None
    logger_assembler: IsoTpAssembler | None = None

    for frame in frames:
        if _logger_tx_request(frame):
            logger_claim_id = _expected_response_id(frame.can_id)
            logger_claim_started = frame.time_us
            logger_assembler = IsoTpAssembler()
            continue

        if _external_request(frame):
            output.append(
                ExternalDiagnosticFrame(
                    frame.time_us, frame.can_id, frame.dlc,
                    bytes(frame.data[: frame.dlc]), "EXTERNAL_REQUEST",
                )
            )
            last_external_request_us = frame.time_us
            # Current firmware immediately cancels logger diagnostic ownership.
            logger_claim_id = None
            logger_claim_started = None
            logger_assembler = None
            continue

        if frame.direction != 0 or not _standard_data(frame):
            continue

        if logger_claim_id is not None and logger_claim_started is not None:
            if frame.time_us - logger_claim_started > logger_timeout_us:
                logger_claim_id = None
                logger_claim_started = None
                logger_assembler = None
            elif frame.can_id == logger_claim_id and _pci_type(frame) in (0, 1, 2):
                assert logger_assembler is not None
                complete = logger_assembler.feed(frame.time_us, frame.can_id, frame.data, frame.dlc)
                if complete is not None:
                    logger_claim_id = None
                    logger_claim_started = None
                    logger_assembler = None
                continue

        if (
            RESPONSE_MIN <= frame.can_id <= RESPONSE_MAX
            and last_external_request_us is not None
            and frame.time_us >= last_external_request_us
            and frame.time_us - last_external_request_us <= hold_us
        ):
            output.append(
                ExternalDiagnosticFrame(
                    frame.time_us, frame.can_id, frame.dlc,
                    bytes(frame.data[: frame.dlc]), "EXTERNAL_RESPONSE",
                )
            )

    return tuple(output)


def _hex_id(value: int | None) -> str:
    return "" if value is None else f"0x{value:X}"


def write_legacy_diagnostics(transactions: Iterable[DiagnosticTransaction], path) -> int:
    import csv

    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(DIAGNOSTICS_HEADER)
        for index, transaction in enumerate(transactions, 1):
            writer.writerow([
                index,
                transaction.request_time_us,
                "" if transaction.complete_time_us is None else transaction.complete_time_us,
                _hex_id(transaction.request_id),
                _hex_id(transaction.response_id),
                "" if transaction.service is None else f"0x{transaction.service:02X}",
                "" if transaction.pid is None else f"0x{transaction.pid:02X}",
                transaction.status,
                len(transaction.payload),
                transaction.payload.hex().upper(),
                transaction.frame_count,
                "" if transaction.response_time_ms is None else f"{transaction.response_time_ms:.3f}",
            ])
            rows += 1
    return rows


def write_external_diagnostics(frames: Iterable[ExternalDiagnosticFrame], path) -> int:
    import csv

    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(EXTERNAL_DIAGNOSTICS_HEADER)
        for frame in frames:
            writer.writerow([
                frame.time_us,
                f"0x{frame.can_id:X}",
                frame.dlc,
                frame.data.hex().upper(),
                frame.classification,
            ])
            rows += 1
    return rows


def build_diagnostic_summary(
    frames: Iterable[TcbFrame],
    transactions: Iterable[DiagnosticTransaction],
    external_frames: Iterable[ExternalDiagnosticFrame],
    meta: MetaReadResult,
) -> dict[str, object]:
    raw_rx = 0
    raw_tx = 0
    for frame in frames:
        if frame.direction == 0:
            raw_rx += 1
        else:
            raw_tx += 1

    transactions = tuple(transactions)
    external_frames = tuple(external_frames)
    statuses: dict[str, int] = {}
    for transaction in transactions:
        statuses[transaction.status] = statuses.get(transaction.status, 0) + 1

    external_requests = sum(frame.classification == "EXTERNAL_REQUEST" for frame in external_frames)
    external_responses = sum(frame.classification == "EXTERNAL_RESPONSE" for frame in external_frames)

    meta_timeouts = 0
    for record in meta.records:
        if record.record_type != 0x0031:
            continue
        try:
            if decode_record_payload(record).get("state_code") == 3:
                meta_timeouts += 1
        except Exception:
            continue

    reconstructed_timeouts = statuses.get("TIMEOUT", 0)
    disagreements: list[dict[str, object]] = []
    if meta_timeouts != reconstructed_timeouts:
        disagreements.append({
            "metric": "diagnostic_timeouts",
            "meta": meta_timeouts,
            "reconstructed": reconstructed_timeouts,
        })

    return {
        "raw_rx_count": raw_rx,
        "raw_tx_count": raw_tx,
        "logger_transaction_count": len(transactions),
        "logger_status_counts": dict(sorted(statuses.items())),
        "external_request_count": external_requests,
        "external_response_count": external_responses,
        "incomplete_transaction_count": statuses.get("INCOMPLETE_SEQUENCE", 0) + statuses.get("NO_RESPONSE", 0),
        "timeout_count": reconstructed_timeouts,
        "meta_reconstruction_disagreements": disagreements,
    }
