# Toyota Hybrid CAN v0.5.3 / Evidence Builder v1.0.2

This release contains the auditable Toyota Hybrid CAN database and the Windows
Evidence Builder used to process CYD logger captures plus BLE-aligned Android
screen recordings.

## Contents

- `Toyota_Hybrid_CAN_Database_v0.5.3.xlsx` — workbook with the v0.5.3 change
  log, S0012 diagnostic actions, Dr. Prius graph evidence, and decoder export.
- `toyota_hybrid_can_db_v0.5.3.json` — version-checked runtime decoder data.
- `ToyotaCANEvidenceBuilder_v1.0.2/` — Windows 10/11 source, GUI/CLI, tests,
  and automated dependency setup.

## Install and use

1. Extract the `ToyotaCANEvidenceBuilder_v1.0.2` folder.
2. Run `INSTALL_WINDOWS.bat` once. It creates the app-local virtual
   environment and checks/repairs Python, `faster-whisper`, `requests`,
   FFmpeg, and Tesseract. Follow `INSTALL_WINDOWS.md` for PATH setup.
3. Run `RUN_EVIDENCE_BUILDER.bat`, select a CYD `CANLOG` folder and optional
   Android companion ZIP/folder, then enable OCR only when Tesseract is ready.

The processor is passive: it decodes frames already present in the capture and
never sends CAN requests. Read-code observations are labelled
`READ_ONLY_DIAGNOSTIC`; clear-code observations remain
`CONTROL_WRITE_QUARANTINED` evidence and are never enabled for automatic
transmit. The AHV40 `21CE` mapping and Dr. Prius graph rows are `PROBABLE`, not
confirmed vehicle-wide definitions.

`Toyota_Hybrid_CAN_Database_v0.5.2.xlsx` remains the rollback checkpoint.
