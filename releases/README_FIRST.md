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
- `VideoNarrationTranscriber_Win10_1607_Portable_v1.0.1.zip` — standalone
  narration transcriber for quickly generating timestamped transcripts from
  `SCREEN.mp4`, `SCREEN_FAST.mp4`, and ordinary audio/video files while full
  Evidence Builder / Analyzer processing runs separately. It uses the proven
  `faster-whisper 1.2.0` / `small.en` / CPU `int8` path and restores the
  Evidence Builder `vad_filter=True` transcription behavior. The ZIP includes
  source, GUI/CLI, tests, install/verification scripts, and a synthetic spoken
  WAV fixture for the Windows 10 1607 release checklist.

## Install and use

1. Extract the `ToyotaCANEvidenceBuilder_v1.0.2` folder.
2. Run `INSTALL_WINDOWS.bat` once. It creates the app-local virtual
   environment and checks/repairs Python, `faster-whisper`, `requests`,
   FFmpeg, and Tesseract. Follow `INSTALL_WINDOWS.md` for PATH setup.
3. Run `RUN_EVIDENCE_BUILDER.bat`, select a CYD `CANLOG` folder and optional
   Android companion ZIP/folder, then enable OCR only when Tesseract is ready.

### Video Narration Transcriber

1. Extract `VideoNarrationTranscriber_Win10_1607_Portable_v1.0.1.zip`.
2. Run `INSTALL.bat` and allow the `small.en` model load/download check.
3. Run `RUN_TRANSCRIBER.bat` and select the video/audio files to transcribe.
4. `CHATGPT_TRANSCRIPT.txt` is the quick handoff artifact; `VOICE_TRANSCRIPT.csv`
   preserves media/video-clock timestamps for later Evidence Builder / Analyzer
   correlation.
5. On the Windows 10 1607 target, `RELEASE_CHECKLIST_WIN1607.bat` uses the
   bundled `tests\fixtures\short_spoken_fixture.wav` when no argument is given.

The processor is passive: it decodes frames already present in the capture and
never sends CAN requests. Read-code observations are labelled
`READ_ONLY_DIAGNOSTIC`; clear-code observations remain
`CONTROL_WRITE_QUARANTINED` evidence and are never enabled for automatic
transmit. The AHV40 `21CE` mapping and Dr. Prius graph rows are `PROBABLE`, not
confirmed vehicle-wide definitions.

The Video Narration Transcriber is transcription-only: it performs no CAN
transmission, CAN decoding, OCR, or evidence grading. Native Windows 10 1607
build-14393 validation remains an explicit release gate rather than being
inferred from Linux/container tests.

`Toyota_Hybrid_CAN_Database_v0.5.2.xlsx` remains the rollback checkpoint.
