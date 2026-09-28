import csv
import pathlib
import struct
import tempfile
import unittest

from toyota_vehicle_bus_session.diagnostics import (
    build_diagnostic_summary,
    classify_external_diagnostic_frames,
    reconstruct_logger_diagnostics,
    write_external_diagnostics,
    write_legacy_diagnostics,
)
from toyota_vehicle_bus_session.external_transactions import reconstruct_external_transactions
from toyota_vehicle_bus_session.meta import MetaHeader, MetaReadResult, MetaRecovery, MetaRecord
from toyota_vehicle_bus_session.tcb1 import TcbFrame


def frame(time_us, can_id, data, direction=0, *, extended=0, rtr=0):
    data = bytes(data)
    return TcbFrame(time_us, can_id, data + b"\0" * (8 - len(data)), len(data), extended, rtr, direction)


def meta(*records):
    return MetaReadResult(MetaHeader(1, 0, 1, 0, 0), tuple(records), MetaRecovery(0, (), 0, (), ()), False)


class DiagnosticTests(unittest.TestCase):
    def test_logger_multiframe_transaction_and_flow_control_not_external(self):
        frames = [
            frame(100, 0x7E2, [2, 0x21, 0xC3], 1),
            frame(150, 0x7EA, [0x10, 9, 0x61, 0xC3, 1, 2, 3, 4]),
            frame(160, 0x7E2, [0x30, 0, 0], 1),
            frame(170, 0x7EA, [0x21, 5, 6, 7, 8, 9, 0, 0]),
        ]
        transactions = reconstruct_logger_diagnostics(frames, meta())
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].status, "OK")
        self.assertEqual(transactions[0].payload, bytes([0x61, 0xC3, 1, 2, 3, 4, 5, 6, 7]))
        self.assertEqual(classify_external_diagnostic_frames(frames), ())

    def test_no_response_and_response_mismatch(self):
        frames = [
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(200, 0x7E9, [3, 0x41, 0x0C, 0x10]),
        ]
        transaction = reconstruct_logger_diagnostics(frames, meta())[0]
        self.assertEqual(transaction.status, "NO_RESPONSE")
        self.assertIsNone(transaction.response_id)

    def test_missing_sequence_is_visible(self):
        frames = [
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(120, 0x7E8, [0x10, 12, 0x41, 0x0C, 1, 2, 3, 4]),
            frame(130, 0x7E8, [0x22, 5, 6, 7, 8, 9, 10, 11]),
        ]
        self.assertEqual(reconstruct_logger_diagnostics(frames, meta())[0].status, "INCOMPLETE_SEQUENCE")

    def test_metadata_internal_states_refine_only_existing_transaction(self):
        for code, expected in [
            (3, "TIMEOUT"),
            (5, "INCOMPLETE_SEQUENCE"),
            (6, "EXTERNAL_INTERLOCK"),
            (7, "USER_DISABLED"),
            (8, "BUS_OFF"),
        ]:
            with self.subTest(code=code):
                state = MetaRecord(0x0031, 1, 0, 1, 200, struct.pack("<HHII", code, 0, 0, 0))
                transaction = reconstruct_logger_diagnostics([frame(100, 0x7E0, [2, 1, 5], 1)], meta(state))[0]
                self.assertEqual(transaction.status, expected)
        state = MetaRecord(0x0031, 1, 0, 1, 200, struct.pack("<HHII", 3, 0, 0, 0))
        self.assertEqual(reconstruct_logger_diagnostics([], meta(state)), ())

    def test_negative_response(self):
        transaction = reconstruct_logger_diagnostics([
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(150, 0x7E8, [3, 0x7F, 1, 0x12]),
        ], meta())[0]
        self.assertEqual(transaction.status, "NEGATIVE_RESPONSE")
        self.assertEqual(transaction.payload, bytes([0x7F, 1, 0x12]))

    def test_external_request_response_and_five_second_hold(self):
        external = classify_external_diagnostic_frames([
            frame(100, 0x7E0, [2, 1, 0x0C]),
            frame(200, 0x7E8, [4, 0x41, 0x0C, 0x12, 0x34]),
        ])
        self.assertEqual([item.classification for item in external], ["EXTERNAL_REQUEST", "EXTERNAL_RESPONSE"])
        expired = classify_external_diagnostic_frames([
            frame(100, 0x7DF, [2, 1, 0]),
            frame(5_000_101, 0x7E8, [3, 0x41, 0, 0]),
        ])
        self.assertEqual([item.classification for item in expired], ["EXTERNAL_REQUEST"])

    def test_external_transactions_pair_single_frame_and_report_no_response(self):
        transactions = reconstruct_external_transactions([
            frame(100, 0x7E0, [2, 1, 0x0C]),
            frame(150, 0x7E8, [4, 0x41, 0x0C, 0x12, 0x34]),
            frame(300, 0x7E3, [2, 0x21, 0xCE]),
        ])
        self.assertEqual(len(transactions), 2)
        first, second = transactions
        self.assertEqual((first.request_id, first.response_id, first.service, first.pid), (0x7E0, 0x7E8, 1, 0x0C))
        self.assertEqual(first.status, "OK")
        self.assertEqual(first.payload, bytes([0x41, 0x0C, 0x12, 0x34]))
        self.assertEqual(first.frame_count, 1)
        self.assertEqual(second.status, "NO_RESPONSE")
        self.assertEqual((second.request_id, second.service, second.pid), (0x7E3, 0x21, 0xCE))

    def test_external_transactions_reassemble_multiframe_and_expose_sequence_gap(self):
        ok = reconstruct_external_transactions([
            frame(100, 0x7E2, [2, 0x21, 0xC3]),
            frame(150, 0x7EA, [0x10, 9, 0x61, 0xC3, 1, 2, 3, 4]),
            frame(170, 0x7EA, [0x21, 5, 6, 7, 8, 9, 0, 0]),
        ])[0]
        self.assertEqual(ok.status, "OK")
        self.assertEqual(ok.payload, bytes([0x61, 0xC3, 1, 2, 3, 4, 5, 6, 7]))
        self.assertEqual(ok.frame_count, 2)

        incomplete = reconstruct_external_transactions([
            frame(100, 0x7E2, [2, 0x21, 0xC3]),
            frame(150, 0x7EA, [0x10, 12, 0x61, 0xC3, 1, 2, 3, 4]),
            frame(170, 0x7EA, [0x22, 5, 6, 7, 8, 9, 10, 11]),
        ])[0]
        self.assertEqual(incomplete.status, "INCOMPLETE_SEQUENCE")
        self.assertGreater(incomplete.missing_sequences, 0)

    def test_external_transactions_report_unmatched_response(self):
        transactions = reconstruct_external_transactions([
            frame(100, 0x7E0, [2, 1, 0x05]),
            frame(120, 0x7E8, [4, 0x41, 0x0C, 0x12, 0x34]),
        ])
        unmatched = next(item for item in transactions if item.status == "UNMATCHED_RESPONSE")
        self.assertIsNone(unmatched.request_id)
        self.assertEqual(unmatched.response_id, 0x7E8)
        self.assertTrue(any(item.status == "NO_RESPONSE" for item in transactions))

    def test_logger_owned_response_is_not_mislabeled_during_external_hold(self):
        external = classify_external_diagnostic_frames([
            frame(1, 0x7DF, [2, 1, 0]),
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(150, 0x7E8, [3, 0x41, 0x0C, 0x10]),
        ])
        self.assertEqual([item.classification for item in external], ["EXTERNAL_REQUEST"])

    def test_external_request_interrupts_logger_claim(self):
        external = classify_external_diagnostic_frames([
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(120, 0x7E0, [2, 1, 5]),
            frame(150, 0x7E8, [3, 0x41, 5, 80]),
        ])
        self.assertEqual([item.classification for item in external], ["EXTERNAL_REQUEST", "EXTERNAL_RESPONSE"])

    def test_extended_rtr_and_tx_requests_are_never_external(self):
        frames = [
            frame(1, 0x7E0, [2, 1, 0], 1),
            frame(2, 0x7E0, [2, 1, 0], extended=1),
            frame(3, 0x7E0, [2, 1, 0], rtr=1),
        ]
        self.assertEqual(classify_external_diagnostic_frames(frames), ())

    def test_csv_headers_rows_and_reconciliation_summary(self):
        frames = [
            frame(100, 0x7E0, [2, 1, 0x0C], 1),
            frame(150, 0x7E8, [4, 0x41, 0x0C, 0x12, 0x34]),
            frame(300, 0x7DF, [2, 1, 5]),
            frame(350, 0x7E8, [3, 0x41, 5, 80]),
        ]
        transactions = reconstruct_logger_diagnostics(frames, meta())
        external = classify_external_diagnostic_frames(frames)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.assertEqual(write_legacy_diagnostics(transactions, root / "DIAGNOSTICS.CSV"), 1)
            self.assertEqual(write_external_diagnostics(external, root / "EXTERNAL_DIAGNOSTICS.CSV"), 2)
            with (root / "DIAGNOSTICS.CSV").open(newline="", encoding="utf-8") as handle:
                diagnostic_rows = list(csv.reader(handle))
            with (root / "EXTERNAL_DIAGNOSTICS.CSV").open(newline="", encoding="utf-8") as handle:
                external_rows = list(csv.reader(handle))

        self.assertEqual(diagnostic_rows[0], [
            "Transaction", "RequestTime_us", "CompleteTime_us", "RequestID", "ResponseID",
            "Service", "PID", "Status", "PayloadLength", "PayloadHex", "FrameCount", "ResponseTime_ms",
        ])
        self.assertEqual(diagnostic_rows[1][3:8], ["0x7E0", "0x7E8", "0x01", "0x0C", "OK"])
        self.assertEqual(external_rows[0], ["Time_us", "CAN_ID", "DLC", "DataHex", "Classification"])
        self.assertEqual([row[-1] for row in external_rows[1:]], ["EXTERNAL_REQUEST", "EXTERNAL_RESPONSE"])

        summary = build_diagnostic_summary(frames, transactions, external, meta())
        self.assertEqual((summary["raw_rx_count"], summary["raw_tx_count"]), (3, 1))
        self.assertEqual(summary["logger_transaction_count"], 1)
        self.assertEqual((summary["external_request_count"], summary["external_response_count"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
