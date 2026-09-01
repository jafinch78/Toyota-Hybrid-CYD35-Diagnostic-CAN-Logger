# Toyota Hybrid CAN v0.5.5 / Evidence Builder v1.0.3

This release contains the auditable Toyota Hybrid CAN database and the Windows
Evidence Builder source used to process CYD logger captures plus BLE-aligned
Android or Windows recordings entirely offline.

## Contents

- `Toyota_Hybrid_CAN_Database_v0.5.5.xlsx` — visually verified workbook with
  v0.5.5 changes, profiles, S0018 evidence, and the 44-definition decoder
  export.
- `toyota_hybrid_can_db_v0.5.5.json` — schema-checked runtime decoder data.
- `ToyotaCANEvidenceBuilder_v1.0.3/` — Windows 10/11 source, GUI/CLI, tests,
  dependency setup, generic decoding, batch pairing, offline evidence grading,
  interactive report, compact capsule, and optional OCR review proxy.

## Install and use

1. Extract the `ToyotaCANEvidenceBuilder_v1.0.3` folder.
2. Run `INSTALL_WINDOWS.bat` once. It creates the app-local virtual environment
   and checks Python, FFmpeg, Tesseract, and optional narration dependencies.
3. Run `RUN_EVIDENCE_BUILDER.bat`, select a CYD `CANLOG` ZIP/folder and optional
   companion capture, then enable OCR/transcription only when their dependencies
   are ready.
4. For multiple archives, use the GUI batch folder option or CLI `--batch`;
   pairing is based on a successful BLE `START_PASSIVE` session number.

The processor remains passive. It decodes frames already present in a capture
and never sends CAN requests or enables clear-code, reset, actuator, or control
commands. Local evidence grades are review aids and never promote the database
automatically. VINs are masked by default.

The confirmed ZVW35 profile contains eight seven-cell aggregate block voltages.
It does not claim 56 individually decoded cell voltages.

Database v0.5.4 and Evidence Builder v1.0.2 remain the rollback checkpoints.
