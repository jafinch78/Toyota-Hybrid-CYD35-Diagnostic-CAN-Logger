# Toyota CAN Evidence Builder 1.0.0

The Windows application accepts a CYD `CANLOG.zip` or session tree and an
optional Android/Windows synchronized-capture ZIP. It validates the logger
manifest, inventories TCB1 traffic, recovers complete records from a truncated
tail, normalizes diagnostic outcomes, fits the session's BLE clock relationship,
and writes aligned CSV/JSON/HTML evidence.

The GUI runs with `RUN_EVIDENCE_BUILDER.bat`. A command-line interface is also
available:

```bat
.venv\Scripts\python -m toyota_can_processor CANLOG.zip -c CAPTURE.zip -o Results --raw-csv
```

Optional post-processing:

- `--ocr --ocr-profile HYBRID_ASSISTANT` requires FFmpeg and Tesseract.
- `--transcribe` requires `INSTALL_VOICE_TRANSCRIPTION.bat` and downloads the
  selected Whisper model on first use.
- `RUN_TECHSTREAM_CAPTURE.bat` uses BLE plus FFmpeg to record the Windows
  desktop and microphone while Techstream runs.

The processor fully supports firmware v2.3.0/capture 1.3 and firmware
v2.4.0/capture 1.4. It parses an unrecognized firmware when the capture/raw
format is known, warns on new minor formats, and refuses unknown major/raw
formats instead of guessing.
