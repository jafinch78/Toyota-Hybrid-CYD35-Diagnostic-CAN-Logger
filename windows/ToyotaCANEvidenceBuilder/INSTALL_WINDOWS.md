# Toyota CAN Evidence Builder 1.0.3 — Windows 10 and 11

## Automatic installation

1. Install 64-bit Python 3.12 from [python.org](https://www.python.org/downloads/windows/).
   Enable **Add Python to PATH** and **Python Launcher**. In the installer,
   select **Disable path length limit** when offered.
2. Open the `ToyotaCANEvidenceBuilder` folder.
3. Double-click `INSTALL_WINDOWS.bat`.

The installer performs the remaining setup automatically:

- creates or reuses the app-local `.venv` virtual environment;
- installs the Evidence Builder and BLE support into that `.venv`;
- installs and verifies `faster-whisper 1.2.0` and its required `requests`
  package in the same `.venv`;
- checks for FFmpeg and `ffprobe`;
- downloads the Gyan **ffmpeg-release-essentials.zip** build when FFmpeg is
  missing, normally to `C:\Tools\ffmpeg\bin` (or a per-user fallback if
  `C:\Tools` is not writable);
- checks for 64-bit Tesseract OCR and, when missing, downloads the UB Mannheim
  Tesseract 5.5.3 installer and installs it to the default location;
- verifies Tesseract `eng` and `osd` data, downloading missing trained-data
  files when necessary; and
- adds the resolved FFmpeg and Tesseract folders to the Windows **user PATH**
  without overwriting existing entries.

The script stops with a specific error if an external download, UAC approval,
or verification fails. It is safe to run again later; existing valid installs
are detected and reused. After installation, run `RUN_EVIDENCE_BUILDER.bat`.

To verify the exact interpreter and folders at any time:

```bat
.venv\Scripts\python.exe -m toyota_can_processor --check-install
```

The check must show the app-local `.venv` interpreter, importable
`faster-whisper` and `requests`, and resolved `ffmpeg`, `ffprobe`, and
`tesseract` paths.

## Processing and outputs

Select the CYD `CANLOG.zip` or extracted folder, the Android capture ZIP when
available, an output folder, and then process. The output contains one folder
per logger session with:

- `COMPATIBILITY_REPORT.json`
- `CAN_ID_INVENTORY.csv`
- optional `CAN_RAW.csv`
- `EVENTS_ALIGNED.csv`, `DECODED_ALIGNED.csv`
- `DIAGNOSTICS_NORMALIZED.csv`
- `DIAGNOSTIC_ACTIONS_ALIGNED.csv` for grouped read/clear-code evidence
- `LOGGER_DIAGNOSTICS_NORMALIZED.csv` and `EXTERNAL_DIAGNOSTICS_NORMALIZED.csv`
- `BATTERY_BLOCKS_ALIGNED.csv` when a supported diagnostic decoder matches
- `TIME_ALIGNMENT.json` when a matching BLE capture is present
- `SESSION_SUMMARY.json` and `REPORT.html`

The matching session is taken from the BLE `START_PASSIVE` acknowledgement. The
clock slope, offset, drift, residuals, and video mapping are recalculated for
every capture; no offset from another session is reused.

## OCR and narration

The GUI can sample Android or Techstream video with the `AUTO`,
`HYBRID_ASSISTANT_BATTERY_CHECK`, `DR_PRIUS_BATTERY_MONITOR`,
`AUTEL_MAXIAP200`, or `TECHSTREAM` layout. Version 1.0.3 preserves full-frame
OCR in `OCR_TEXT.csv` and writes graph-aware battery results to
`BATTERY_GRAPH_ALIGNED.csv`, with audit crops in `GRAPH_KEYFRAMES`.
It detects orientation independently for every sampled frame. Hybrid Assistant
portrait screens and Dr. Prius landscape Battery Monitor screens may therefore
appear in the same recording without entering rotation times manually.

When **Transcribe narration** is selected, the program checks the active
`.venv` before processing. If `faster-whisper` or `requests` is absent or
broken, it automatically runs that same `.venv`'s pip and verifies the imports
again. The first successful transcription downloads the selected Whisper model.
No system-wide Python installation is used for this repair.

When OCR is selected, FFmpeg and Tesseract are resolved from the current PATH
or the documented installation folders. If they are missing, the GUI reports
the exact tools and directs you to rerun `INSTALL_WINDOWS.bat`.

The matching FFmpeg build is the Gyan Windows **essentials** archive:
<https://www.gyan.dev/ffmpeg/builds/>. The matching Tesseract source is the
64-bit UB Mannheim build documented at
<https://github.com/UB-Mannheim/tesseract/wiki>; the current pinned installer
URL is:
<https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe>.

For a manual command-line check in a newly opened Command Prompt, use:

```bat
ffmpeg --version
ffprobe --version
tesseract --version
tesseract --list-langs
```

The last command should list at least `eng` and `osd`. Existing Command Prompt
windows do not receive PATH changes; open a new one after installation.

Hybrid Assistant Battery Check is validated against the supplied S0010/S0012
Camry captures. Dr. Prius Battery Monitor landscape extraction is validated
against the supplied S0012 recording. Non-monitor Dr. Prius screens, Android
app switchers, and the initial erroneous portion of a recording are rejected
from battery-block output.

## BLE-synchronized Techstream recording

1. The PC needs working Bluetooth Low Energy; add a USB BLE adapter if needed.
2. Run `LIST_AUDIO_DEVICES.bat` and copy the exact microphone device name.
3. Start the CYD and confirm listen-only mode.
4. Open Techstream, then run `RUN_TECHSTREAM_CAPTURE.bat` and enter the device
   name. The program synchronizes clocks, starts CYD logging, and records the
   Windows desktop plus narration.
5. Type `m` and Enter for a marker. Press Enter on an empty line to stop.
6. Process the resulting `CAPTURE_...` folder alongside the CANLOG folder.

Windows display capture uses FFmpeg's `gdigrab`; the Techstream window must be
visible and unobscured. The recorder does not control Techstream or send
diagnostic/CAN commands.

## Optional standalone EXE

After installation, run `BUILD_WINDOWS_EXE.bat` on Windows. PyInstaller writes
`dist\ToyotaCANEvidenceBuilder.exe`. PyInstaller must build on Windows; a Linux
build cannot be substituted for a Windows executable.
