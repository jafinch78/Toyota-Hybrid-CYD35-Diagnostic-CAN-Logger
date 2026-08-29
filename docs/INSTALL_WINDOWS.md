# Windows 10 and 11 installation

## Core processor

1. Install 64-bit Python 3.12 from python.org and select **Add Python to PATH**.
2. Open the `windows/ToyotaCANEvidenceBuilder` folder.
3. Double-click `INSTALL_WINDOWS.bat`. It creates a private virtual environment,
   installs the processor, and installs BLE support.
4. Double-click `RUN_EVIDENCE_BUILDER.bat`.
5. Select the CYD `CANLOG.zip` or its extracted folder. Select the Android
   capture ZIP when available, choose an output folder, and process.

The output contains one folder per logger session with:

- `COMPATIBILITY_REPORT.json`
- `CAN_ID_INVENTORY.csv`
- optional `CAN_RAW.csv`
- `EVENTS_ALIGNED.csv`, `DECODED_ALIGNED.csv`
- `DIAGNOSTICS_NORMALIZED.csv`
- `TIME_ALIGNMENT.json` when a matching BLE capture is present
- `SESSION_SUMMARY.json` and `REPORT.html`

The matching session is taken from the BLE `START_PASSIVE` acknowledgement. The
clock slope, offset, drift, residuals, and video mapping are recalculated for
every capture; S0034's earlier offset is never reused.

## OCR and narration

Install a Windows FFmpeg build and Tesseract OCR, then add both executable
folders to PATH. The GUI can then sample Android or Techstream video with the
`AUTO`, `HYBRID_ASSISTANT`, `DR_PRIUS`, `AUTEL_MAXIAP200`, or `TECHSTREAM`
profile label. Version 1.0 performs full-frame OCR and preserves all recognized
text/numbers in `OCR_TEXT.csv`; later calibrated crop profiles can improve
individual screens without changing the capture format.

For local voice transcription, run `INSTALL_VOICE_TRANSCRIPTION.bat`, then check
**Transcribe narration**. The first run downloads the selected Whisper model.

## BLE-synchronized Techstream recording

1. The PC needs working Bluetooth Low Energy; add a USB BLE adapter if needed.
2. Install FFmpeg and connect a microphone.
3. Run `LIST_AUDIO_DEVICES.bat` and copy the exact microphone device name.
4. Start the CYD and confirm listen-only mode.
5. Open Techstream, then run `RUN_TECHSTREAM_CAPTURE.bat` and enter the device
   name. The program synchronizes clocks, starts CYD logging, and records the
   Windows desktop plus narration.
6. Type `m` and Enter for a marker. Press Enter on an empty line to stop.
7. Process the resulting `CAPTURE_...` folder alongside the CANLOG folder.

Windows display capture uses FFmpeg's `gdigrab`; the Techstream window must be
visible and unobscured. The Windows recorder does not control Techstream or send
diagnostic/CAN commands.

## Optional standalone EXE

After installation, run `BUILD_WINDOWS_EXE.bat` on Windows. PyInstaller writes
`dist\ToyotaCANEvidenceBuilder.exe`. PyInstaller must build on Windows; a Linux
build cannot be substituted for a Windows executable.
