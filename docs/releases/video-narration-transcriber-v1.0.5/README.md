# Video Narration Transcriber v1.0.5

Validated standalone Windows transcription helper for quickly producing narration transcripts from `SCREEN.mp4`, `SCREEN_FAST.mp4`, and ordinary audio/video files while the longer Toyota CAN Evidence Builder / Analyzer pipeline continues separately.

## Proven transcription path

- Windows 10 x64 version 1607, build 14393
- Python 3.12.7 x64
- faster-whisper 1.2.0
- CTranslate2 4.8.2
- Whisper model `small.en`
- CPU / int8
- `vad_filter=True`, matching the retained Evidence Builder narration implementation
- NumPy 2.2.6 / PyInstaller 6.14.1 for the optional frozen EXE build

## Outputs

- `CHATGPT_TRANSCRIPT.txt` — quick ChatGPT handoff
- `VOICE_TRANSCRIPT.csv` — Evidence Builder-compatible timestamped transcript
- `TRANSCRIPT.txt`
- `TRANSCRIPT.srt`
- `TRANSCRIPT.json`
- `TRANSCRIPTION_SUMMARY.json`

`VOICE_TRANSCRIPT.csv` preserves media/video-clock timestamps for later correlation with Evidence Builder / Analyzer session data.

## Native Windows 10 1607 validation

On 2026-09-26 the exact v1.0.5 frozen EXE build passed `RELEASE_CHECKLIST_WIN1607.bat` on Windows 10 build 14393:

1. Exact Windows build and bundled spoken fixture — PASS
2. Python 3.12.7 x64 and `small.en` CPU/int8 model verification — PASS
3. End-to-end EXE transcription process — PASS, return code 0
4. Read-back of non-empty `VOICE_TRANSCRIPT.csv` plus Evidence Builder compatibility summary — PASS

The prior frozen-runtime defects were corrected before this gate: the distributable EXE is the one-folder application under `dist\VideoNarrationTranscriber\`, frozen-runtime dependency checks no longer pre-import the heavy native transcription stack, and build dependencies are pinned to a compatible PyInstaller/NumPy pair.

## Package identity

Expected package name:

`VideoNarrationTranscriber_Win10_1607_Portable_v1.0.5.zip`

SHA-256:

`f559c225099fc06936f569d61d8d798c35b5ac4fb5cf8cbc751acfe53761547a`

The ZIP is transcription-only and performs no CAN transmission, CAN decoding, OCR, or evidence grading.
