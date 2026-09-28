from __future__ import annotations

import unittest

from toyota_vehicle_bus_session.oracle import _raw_response_recovery_improvement


RAW_IDENTICAL = {
    "raw_record_count_equal": True,
    "raw_stream_identical": True,
    "inventory_identical": True,
}


class RawResponseRecoveryGuardTests(unittest.TestCase):
    def test_s0149_shape_preserves_request_backed_count(self) -> None:
        original = {
            "transactions": 2666,
            "status_counts": {
                "OK": 15,
                "NO_RESPONSE": 2625,
                "INCOMPLETE_SEQUENCE": 23,
                "UNMATCHED_RESPONSE": 3,
            },
            "battery_block_rows": 10,
            "diagnostic_action_rows": 1,
            "decoded_field_rows": 198,
            "resistance_rows": 2,
            "identity_rows": 0,
        }
        expanded = {
            "transactions": 2678,
            "status_counts": {
                "OK": 2271,
                "NO_RESPONSE": 35,
                "INCOMPLETE_SEQUENCE": 357,
                "UNMATCHED_RESPONSE": 15,
            },
            "battery_block_rows": 712,
            "diagnostic_action_rows": 1,
            "decoded_field_rows": 24939,
            "resistance_rows": 713,
            "identity_rows": 0,
        }
        self.assertTrue(_raw_response_recovery_improvement(original, expanded, **RAW_IDENTICAL))

    def test_s0128_shape_preserves_negative_response_semantics(self) -> None:
        original = {
            "transactions": 2651,
            "status_counts": {
                "NEGATIVE_RESPONSE_12": 1,
                "NO_RESPONSE": 235,
                "OK": 2279,
                "UNMATCHED_RESPONSE": 120,
                "INCOMPLETE_SEQUENCE": 16,
            },
            "battery_block_rows": 129,
            "diagnostic_action_rows": 2,
            "decoded_field_rows": 7602,
            "resistance_rows": 36,
            "identity_rows": 32,
        }
        expanded = {
            "transactions": 2651,
            "status_counts": {
                "NEGATIVE_RESPONSE_12": 1,
                "OK": 2526,
                "UNMATCHED_RESPONSE": 120,
                "NO_RESPONSE": 4,
            },
            "battery_block_rows": 136,
            "diagnostic_action_rows": 2,
            "decoded_field_rows": 8265,
            "resistance_rows": 36,
            "identity_rows": 35,
        }
        self.assertTrue(_raw_response_recovery_improvement(original, expanded, **RAW_IDENTICAL))

    def test_request_backed_transaction_inflation_is_rejected(self) -> None:
        original = {
            "transactions": 22,
            "status_counts": {"OK": 10, "NO_RESPONSE": 10, "UNMATCHED_RESPONSE": 2},
        }
        expanded = {
            "transactions": 23,
            "status_counts": {"OK": 21, "UNMATCHED_RESPONSE": 2},
        }
        self.assertFalse(_raw_response_recovery_improvement(original, expanded, **RAW_IDENTICAL))

    def test_negative_response_semantics_loss_is_rejected(self) -> None:
        original = {
            "transactions": 20,
            "status_counts": {"NEGATIVE_RESPONSE_12": 1, "OK": 10, "NO_RESPONSE": 9},
        }
        expanded = {
            "transactions": 20,
            "status_counts": {"OK": 20},
        }
        self.assertFalse(_raw_response_recovery_improvement(original, expanded, **RAW_IDENTICAL))


if __name__ == "__main__":
    unittest.main()
