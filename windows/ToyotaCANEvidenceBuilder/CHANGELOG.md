# Changelog

## 1.0.1 — 2026-08-30

- Added data-driven Toyota Hybrid CAN Database v0.5.2 loading and schema/version validation.
- Added passive external ISO-TP request/response reconstruction with explicit OK, unanswered, incomplete-sequence, unmatched, and negative-response states.
- Added AHV40 `7E2 / 21CE` 17-block voltage decoder as `PROBABLE / READ_ONLY_DIAGNOSTIC` evidence.
- Added `BATTERY_BLOCKS_ALIGNED.csv`, populated normalized external diagnostics, and database provenance in summaries/reports.
- Added Hybrid Assistant Battery Check graph extraction, axis fitting, block-bar extraction, audit crops, printed-value parsing, CAN correlation, and power plausibility checks.
- Added a generic variable-block graph route for Dr. Prius; it remains unvalidated until an application-specific sample is captured.
- Retained v1.0.0 behavior for TCB1 inventory, raw expansion, BLE affine alignment, OCR text, narration, and Techstream desktop capture.

Rollback: use Toyota CAN Evidence Builder v1.0.0 with Toyota Hybrid CAN Database v0.5.1.
