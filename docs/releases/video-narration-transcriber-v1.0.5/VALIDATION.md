# Video Narration Transcriber v1.0.5 — Validation

Date: 2026-09-26

Target: Windows 10 x64 version 1607, build 14393

## Exact target result

`RELEASE_CHECKLIST_WIN1607.bat` completed successfully in EXE mode on build 14393.

- Stage 1 — exact Windows build and test fixture: PASS
- Stage 2 — Python 3.12.7 x64 and `small.en` CPU/int8 verification: PASS
- Stage 3 — end-to-end EXE transcription: PASS; process returned 0
- Stage 4 — read-back of canonical transcript and compatibility summary: PASS
- Final result: `RELEASE CHECK PASS: exact Windows 10 1607 build 14393 transcription verified in EXE mode.`

## Compatibility contract

The canonical output is `VOICE_TRANSCRIPT.csv`, using media/video-clock timestamps and an Evidence Builder-compatible transcript contract. The release checklist verified a non-empty transcript and `evidence_builder_compatible=true` after the EXE run.

## Runtime/build identities

- Python 3.12.7 x64
- faster-whisper 1.2.0
- CTranslate2 4.8.2
- `small.en`
- CPU / int8
- `vad_filter=True`
- NumPy 2.2.6
- PyInstaller 6.14.1
- v140 / VS2015 / SDK 14393 present on the target machine; native toolchain remains informational for ordinary transcription runtime

## Package identity

`VideoNarrationTranscriber_Win10_1607_Portable_v1.0.5.zip`

SHA-256: `f559c225099fc06936f569d61d8d798c35b5ac4fb5cf8cbc751acfe53761547a`

## Scope

This validation establishes the exact frozen EXE transcription path on Windows 10 1607 build 14393. It does not imply CAN decoding, OCR, diagnostic control, or Analyzer processing; those are outside this transcription-only application.
