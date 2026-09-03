# ToyotaCAN Windows Capture Process - IPO and TOE

## Scope
This document covers the Windows Techstream/display capture process using the common Python capture layer, the Windows 10 1607 BLE bridge backend, BLE sync/control data, FFmpeg video/audio capture, and later WiFi/SD retrieved logger data.

## IPO Table
| Input | Process / code used | Output files / records |
|---|---|---|
| Windows 10 1607 PC, VS2015/v140/SDK 14393, Python, FFmpeg | `INSTALL_WIN1607_CAPTURE_SETUP.bat` checks A-G, creates `.venv`, installs requirements, optionally builds bridge | A-G install status, `WIN1607_CAPTURE_INSTALL_LOG.txt` |
| Paired ToyotaCYD BLE device | `RUN_TECHSTREAM_CAPTURE_WIN1607.bat` sets `TOYOTA_BLE_BACKEND=win1607` and bridge path | Capture starts using legacy WinRT bridge path |
| BLE transport | `ble_transport.py` launches `Win1607_BLE_Bridge.exe`; bridge uses legacy Windows 1607 GATT APIs | BLE device name/address in `CAPTURE_SYNC.json`; RX packets routed to Python |
| BLE sync/control packets | `windows_capture.py` / `CydBleClient` sends SYNC plus START_PASSIVE, MARKER, STOP | `sync_samples[]`, `control_events[]`, `markers[]` in `CAPTURE_SYNC.json` |
| Desktop Techstream/app display and optional mic | FFmpeg `gdigrab` + optional `dshow` audio; v3 video anchor from FFmpeg progress | `SCREEN.mp4`, `SCREEN.ffmpeg.log`, video anchor fields in `CAPTURE_SYNC.json` |
| ESP32 CYD SD logger session | Firmware records session state and CAN traffic when present | SD session `Sxxxx` with manifest/events/raw CAN records; `CLOSED EMPTY` if bench/no traffic |
| WiFi/SD retrieval after capture | Download/copy SD session data or CANLOG ZIP | `Sxxxx.zip`, `CANLOG*.zip`, or SD session files paired with the Windows capture folder |
| Evidence Builder | Pairs CAPTURE and CANLOG/Sxxxx evidence; creates 10 fps OCR derivative as needed | HTML report, evidence capsule, OCR/transcription/correlation outputs |

## TOE Table
| Task | Object | Event / trigger | Result |
|---|---|---|---|
| Install/check environment | A-G prerequisite states | User runs setup BAT | Installed/Missing summary and optional repair actions |
| Create Python runtime | `.venv`, pip, requirements | Missing or repair requested | Local capture runtime becomes available |
| Select capture backend | Environment variables | Win1607 BAT run | Python selects Win1607 bridge backend instead of Bleak |
| Connect BLE | Bridge process + paired ToyotaCYD | `CONNECT AUTO` | Device opened and notifications enabled |
| Time sync | SYNC command/response | Pre/mid/post bursts and periodic checks | Client/ESP clock samples recorded |
| Start logging | Control opcode START_PASSIVE | Capture begins | CYD enters armed/logging state and session ID is recorded |
| Mark event | Control opcode MARKER | User types `m` | Marker event recorded on both Windows and CYD sides |
| Stop logging | Control opcode STOP | User presses Enter | CYD closes session; Windows marks `closed_cleanly=true` |
| Record screen/audio | FFmpeg process | Capture start/stop | `SCREEN.mp4` plus progress-derived timing fields |
| Retrieve CAN data | SD/WiFi copy/download | After session closes | CAN/session ZIP available for Evidence Builder |
| Build evidence | Evidence Builder process | User supplies CAPTURE + CANLOG/Sxxxx | Correlated report/capsule with OCR/video/CAN timeline |
