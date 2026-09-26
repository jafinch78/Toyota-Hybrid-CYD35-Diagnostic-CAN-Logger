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
- `ToyotaCAN_DB_Compat_Converter_v2_v140_x64.zip` — validated v140 x64
  compatibility converter retained as a standalone Windows helper.
- `VideoNarrationTranscriber_Win10_1607_Portable_v1.0.1.zip` — original
  standalone narration-transcriber release retained for provenance.
- Video Narration Transcriber **v1.0.5** is the current validated implementation.
  Its exact portable-package SHA-256 and Windows 10 1607 EXE validation record
  are under `docs/releases/video-narration-transcriber-v1.0.5/` and the matching
  checksum record is in this `releases/` directory.

## Install and use

1. Extract the `ToyotaCANEvidenceBuilder_v1.0.2` folder.
2. Run `INSTALL_WINDOWS.bat` once. It creates the app-local virtual
   environment and checks/repairs Python, `faster-whisper`, `requests`,
   FFmpeg, and Tesseract. Follow `INSTALL_WINDOWS.md` for PATH setup.
3. Run `RUN_EVIDENCE_BUILDER.bat`, select a CYD `CANLOG` folder and optional
   Android companion ZIP/folder, then enable OCR only when Tesseract is ready.

### Video Narration Transcriber

Video Narration Transcriber is a transcription-only helper for quickly turning
`SCREEN.mp4`, `SCREEN_FAST.mp4`, and ordinary audio/video narration into files
that can be provided to ChatGPT while the longer Evidence Builder / Analyzer
pipeline continues.

The validated v1.0.5 stack is:

- Windows 10 x64 version 1607, build 14393
- Python 3.12.7 x64
- faster-whisper 1.2.0
- CTranslate2 4.8.2
- `small.en`
- CPU / int8
- `vad_filter=True`, matching the proven Evidence Builder narration path
- NumPy 2.2.6 / PyInstaller 6.14.1 for the optional frozen EXE build

`CHATGPT_TRANSCRIPT.txt` is the quick handoff artifact. `VOICE_TRANSCRIPT.csv`
preserves the exact Evidence Builder-compatible schema and media/video-clock
timestamps for later Evidence Builder / Analyzer correlation.

On 2026-09-26 the exact v1.0.5 `dist\VideoNarrationTranscriber` EXE build passed
`RELEASE_CHECKLIST_WIN1607.bat` on Windows 10 1607 build 14393: operating-system
and fixture gate PASS, Python/model gate PASS, EXE transcription process return
code 0, and read-back of a non-empty `VOICE_TRANSCRIPT.csv` with
`evidence_builder_compatible=true` PASS.

The processor is passive: it decodes frames already present in the capture and
never sends CAN requests. Read-code observations are labelled
`READ_ONLY_DIAGNOSTIC`; clear-code observations remain
`CONTROL_WRITE_QUARANTINED` evidence and are never enabled for automatic
transmit. The AHV40 `21CE` mapping and Dr. Prius graph rows are `PROBABLE`, not
confirmed vehicle-wide definitions.

The Video Narration Transcriber performs no CAN transmission, CAN decoding,
OCR, or evidence grading.

`Toyota_Hybrid_CAN_Database_v0.5.2.xlsx` remains the rollback checkpoint.
