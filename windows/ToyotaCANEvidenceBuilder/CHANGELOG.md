# Changelog

## 1.0.2 — 2026-08-30

- Added automatic per-frame portrait/landscape detection for Samsung screen
  recordings; no fixed rotation timestamp or session offset is reused.
- Added a Dr. Prius Battery Monitor extractor that reads the 17 printed block
  values in landscape mode, reconstructs only obscured labels from measured
  bar geometry, and requires pack-voltage consistency before accepting a
  reconstructed row.
- Added Dr. Prius pack voltage, blade voltage, SOC, current direction/current,
  three battery temperatures, block minimum/maximum/difference, audit frames,
  and BLE-aligned CAN comparison fields.
- Added `DIAGNOSTIC_ACTIONS_ALIGNED.csv`. S0012 Mode 13 read-code operations
  decode `53 00` as no DTC present; Mode 04 clear acknowledgements remain
  `CONTROL_WRITE_QUARANTINED` and can never authorize transmission.
- Updated the bundled Toyota Hybrid CAN Database to v0.5.3 with the observed
  S0012 AHV40 read/clear diagnostic signatures and rollback to v0.5.2.
- Added automatic Windows FFmpeg essentials and Tesseract OCR setup with
  idempotent user-PATH updates and `eng`/`osd` language-data verification.
- Added app-local `.venv` verification and automatic on-demand repair for
  `faster-whisper` and its required `requests` dependency.
- Added `--check-install` for interpreter, package, and tool
  diagnostics.
- Suppressed FFmpeg/Tesseract child console windows on Windows, including
  Techstream desktop capture.

Rollback: use Toyota CAN Evidence Builder 1.0.1 with Toyota Hybrid CAN Database v0.5.2.

## 1.0.1 — 2026-08-30

- Added data-driven Toyota Hybrid CAN Database v0.5.2 loading and schema/version validation.
- Added passive external ISO-TP request/response reconstruction with explicit OK, unanswered, incomplete-sequence, unmatched, and negative-response states.
- Added AHV40 `7E2 / 21CE` 17-block voltage decoder as `PROBABLE / READ_ONLY_DIAGNOSTIC` evidence.
- Added `BATTERY_BLOCKS_ALIGNED.csv`, populated normalized external diagnostics, and database provenance in summaries/reports.
- Added Hybrid Assistant Battery Check graph extraction, axis fitting, block-bar extraction, audit crops, printed-value parsing, CAN correlation, and power plausibility checks.
- Added a generic variable-block graph route for Dr. Prius; it remains unvalidated until an application-specific sample is captured.
- Retained v1.0.0 behavior for TCB1 inventory, raw expansion, BLE affine alignment, OCR text, narration, and Techstream desktop capture.

Rollback: use Toyota CAN Evidence Builder v1.0.0 with Toyota Hybrid CAN Database v0.5.1.
