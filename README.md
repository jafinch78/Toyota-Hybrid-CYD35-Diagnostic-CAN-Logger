# Toyota Hybrid CAN Sync Toolkit

The current firmware release is **CYD Logger v2.4.1** for the ESP32 CYD
3.5-inch board and SN65HVD230/VP230 transceiver using CAN TX GPIO25 and CAN RX
GPIO32.

## Current components

1. **CYD Logger v2.4.1** — listen-only startup, touch and microSD capture,
   passive Toyota profile detection, evidence-graded decoding, BLE timestamp
   synchronization, and traffic-aware session logging. v2.4.1 fixes the ESP32
   SD five-file descriptor failure, defers session creation until explicit
   Start, and suppresses empty decoded rows before CAN traffic arrives.
2. **Toyota CAN Sync Recorder 1.0 for Android** — screen and microphone capture
   for Hybrid Assistant, Dr. Prius, and Autel MaxiAP200 on Android 8/API 26 and
   newer, including Samsung A35 5G and S8+.
3. **Toyota CAN Evidence Builder 1.0 for Windows** — Windows 10/11 GUI and CLI
   for v2.3/v2.4 manifests, TCB1, BLE alignment, OCR, narration transcription,
   and optional BLE-synchronized Techstream desktop capture.

## Start here

- Firmware: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_1`
- v2.4.1 release notes and test procedure: `docs/releases/v2.4.1`
- Ready-to-download ZIP: `releases/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2.4.1.zip`
- Android setup: `docs/INSTALL_ANDROID.md`
- Windows setup: `docs/INSTALL_WINDOWS.md`

Capture package 1.4, the 24-byte TCB1 raw record, and ToyotaCYD-Sync/1 remain
compatible with v2.4.0. The Windows processor accepts firmware v2.4.1 without a
format warning.

## Safety boundary

Passive capture is the default. BLE has no CAN-transmit API. The firmware has
no actuator, fan, write, clear, reset, coding, SD erase, or SD format command.
Diagnostic normal mode is a separate, explicit, profile-gated read-only
function and must remain off while another tester is connected. Camry Hybrid
remains passive-only.
