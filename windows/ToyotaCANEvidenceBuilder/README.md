# Toyota CAN Evidence Builder 1.0.2

The Windows application accepts a CYD `CANLOG.zip` or session tree and an
optional Android/Windows synchronized-capture ZIP. It validates the logger
manifest, inventories TCB1 traffic, recovers complete records from a truncated
tail, normalizes diagnostic outcomes, fits the session's BLE clock relationship,
and writes aligned CSV/JSON/HTML evidence. Version 1.0.2 also reconstructs
passively observed external ISO-TP requests/responses and uses the versioned
Toyota Hybrid CAN Database v0.5.3 decoder export.

## New in 1.0.2

- Detects Samsung portrait and rotated-landscape app frames individually, so
  Hybrid Assistant and Dr. Prius can be used in one recording.
- Extracts Dr. Prius Battery Monitor's 17 printed block voltages and displayed
  pack/SOC/current/temperature metrics. Labels obscured by very short bars are
  reconstructed only from a low-residual bar fit and accepted only when the
  result reconciles with the displayed pack voltage.
- Writes `DIAGNOSTIC_ACTIONS_ALIGNED.csv`, grouping repeated read/clear actions
  by ECU. Read-code `53 00` responses report no DTC present. Clear-code
  acknowledgements are evidence only and remain `CONTROL_WRITE_QUARANTINED`.
- Installs/verifies FFmpeg, Tesseract, `faster-whisper`, and `requests`, and
  hides child command windows during OCR/video processing on Windows.

## Added in 1.0.1

- Populates `DIAGNOSTICS_NORMALIZED.csv` from external tester traffic instead
  of leaving a header-only logger transaction file when the CYD itself did not
  issue requests.
- Keeps `LOGGER_DIAGNOSTICS_NORMALIZED.csv` and
  `EXTERNAL_DIAGNOSTICS_NORMALIZED.csv` separately for provenance.
- Decodes the S0010 AHV40 `7E2 / 21CE` response into 17 battery-block voltages
  and writes `BATTERY_BLOCKS_ALIGNED.csv`.
- Adds graph-aware OCR for Hybrid Assistant Battery Check screens. It locates
  the graph geometrically, fits the voltage scale from OCR Y-axis labels,
  extracts ordered block bars, preserves graph crops, and writes
  `BATTERY_GRAPH_ALIGNED.csv`.
- Cross-checks graph values against the nearest BLE-aligned CAN response and
  checks displayed power against graph pack voltage × displayed current.
- Provides the Hybrid Assistant Battery Check graph/CAN route used as the
  baseline for the application-specific Dr. Prius validation in v1.0.2.

The GUI runs with `RUN_EVIDENCE_BUILDER.bat`. A command-line interface is also
available:

```bat
.venv\Scripts\python -m toyota_can_processor CANLOG.zip -c CAPTURE.zip -o Results --raw-csv --ocr
```

Installation and dependency setup:

- `INSTALL_WINDOWS.bat` installs the app-local Python environment, BLE and
  voice packages, and automatically checks/installs FFmpeg and Tesseract.
- `INSTALL_VOICE_TRANSCRIPTION.bat` repairs and verifies voice dependencies in
  the same `.venv` for existing installations.
- `--check-install` prints the resolved interpreter, package imports, and tool
  paths without processing a capture.

Optional post-processing:

- `--ocr --ocr-profile HYBRID_ASSISTANT_BATTERY_CHECK` requires FFmpeg and Tesseract.
- `--transcribe` re-checks and repairs `faster-whisper` and `requests` in the
  active `.venv`, then downloads the selected Whisper model on first use.
- `RUN_TECHSTREAM_CAPTURE.bat` uses BLE plus FFmpeg to record the Windows
  desktop and microphone while Techstream runs.

The processor fully supports firmware v2.3.x/capture 1.3 and firmware
v2.4.x/capture 1.4, including the tested v2.4.2 S0010 capture. It parses an unrecognized firmware when the capture/raw
format is known, warns on new minor formats, and refuses unknown major/raw
formats instead of guessing.

Safety boundary: the decoder processes traffic already present in the capture.
It does not transmit CAN requests, controls, clear-code commands, or writes.
