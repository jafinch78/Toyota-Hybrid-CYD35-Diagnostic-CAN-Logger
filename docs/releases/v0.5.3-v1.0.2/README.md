# Toyota Hybrid CAN Database v0.5.3 + Evidence Builder v1.0.2

This release updates the analysis/database components only. It does not replace
the tested CYD Logger v2.4.2 firmware or Android sync recorder 1.0.1.

The Evidence Builder now detects phone orientation per video frame, extracts
Hybrid Assistant and Dr. Prius Battery Monitor graph values, reconstructs
occluded Dr. Prius block labels from bar geometry, aligns graph rows to passive
CAN samples, and writes grouped diagnostic actions. Windows installation checks
and repairs the app-local voice/OCR dependencies, including `requests` required
by faster-whisper.

## Files

- `Toyota_Hybrid_CAN_Database_v0.5.3.xlsx` — auditable workbook with S0012
  diagnostic actions, Dr. Prius evidence, and decoder export.
- `toyota_hybrid_can_db_v0.5.3.json` — machine-readable, version-checked
  decoder database used by Evidence Builder.
- `ToyotaCANEvidenceBuilder_v1.0.2` — Windows 10/11 source/install folder.

Run `INSTALL_WINDOWS.bat` once in the Evidence Builder folder, then run
`RUN_EVIDENCE_BUILDER.bat`. The app is passive and never transmits CAN requests;
clear-code rows remain quarantined evidence.
