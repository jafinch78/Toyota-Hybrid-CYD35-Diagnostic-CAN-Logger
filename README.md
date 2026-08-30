# Toyota Hybrid CAN Sync Toolkit

The current firmware release is **CYD Logger v2.4.2** for the ESP32 CYD
3.5-inch board and SN65HVD230/VP230 transceiver using CAN TX GPIO25 and CAN RX
GPIO32.

## Current components

1. **CYD Logger v2.4.2** — listen-only startup, touch and microSD capture,
   passive Toyota profile detection, evidence-graded decoding, BLE timestamp
   synchronization, and traffic-aware session logging. v2.4.2 corrects the
   SD-plus-BLE startup failure found during v2.4.1 hardware testing by reserving
   BLE resources first, reducing SD descriptor and CAN queue reservations, and
   making BLE allocation failure nonfatal.
2. **Toyota CAN Sync Recorder 1.0 for Android** — screen and microphone capture
   for Hybrid Assistant, Dr. Prius, and Autel MaxiAP200 on Android 8/API 26 and
   newer, including Samsung A35 5G and S8+.
3. **Toyota CAN Evidence Builder 1.0.1 for Windows** — Windows 10/11 GUI and
   CLI for v2.3/v2.4 manifests, TCB1, BLE alignment, OCR, narration
   transcription, passive external ISO-TP reconstruction, Hybrid Assistant
   Battery Check graph extraction, graph-to-CAN correlation, and optional
   BLE-synchronized Techstream desktop capture. A generic Dr. Prius graph route
   is included but remains unvalidated pending a representative capture.
4. **Toyota Hybrid CAN Database v0.5.2** — auditable XLSX plus version-checked
   JSON. It includes S0010 Camry Hybrid diagnostic inventory and 133 observed
   `7E2 / 21CE` 17-block battery samples, graded `PROBABLE` until independently
   repeated or corroborated.

## Start here

- Firmware: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_2`
- v2.4.2 release notes and test procedure: `docs/releases/v2.4.2`
- Ready-to-download ZIP: `releases/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2.4.2.zip`
- Android setup: `docs/INSTALL_ANDROID.md`
- Windows setup: `docs/INSTALL_WINDOWS.md`
- Database: `database/Toyota_Hybrid_CAN_Database_v0.5.2.xlsx`
- Evidence Builder source: `windows/ToyotaCANEvidenceBuilder`
- Combined analysis release: `releases/Toyota_Hybrid_CAN_v0.5.2_Evidence_Builder_v1.0.1.zip`
- Analysis release notes and validation: `docs/releases/v0.5.2-v1.0.1`

Capture package 1.4, the 24-byte TCB1 raw record, and ToyotaCYD-Sync/1 remain
unchanged. The Windows processor accepts firmware v2.4.x with this format.

v2.4.1 is retained for failure provenance only and must not be deployed: with
the tested microSD installed it could fail BLE server creation and reboot
through a null address. The v2.4.2 ZIP contains the capture-tested v2.3.0
rollback.

## Safety boundary

Passive capture is the default. BLE has no CAN-transmit API. The firmware has
no actuator, fan, write, clear, reset, coding, SD erase, or SD format command.
Diagnostic normal mode is a separate, explicit, profile-gated read-only
function and must remain off while another tester is connected. Camry Hybrid
remains passive-only.

Evidence Builder reconstructs only traffic already present in a capture. It
does not transmit diagnostic requests or CAN control/write commands.
