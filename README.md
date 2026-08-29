# Toyota Hybrid CAN Sync Toolkit v1.0

This coordinated release contains:

1. **CYD Logger v2.4.0** — ESP32 CYD 3.5-inch firmware with GPIO25/32 CAN,
   touch/SD support, listen-only startup, passive Toyota profile detection,
   evidence-graded decoding, and BLE timestamp/session synchronization.
2. **Toyota CAN Sync Recorder 1.0 for Android** — screen plus microphone capture
   for Hybrid Assistant, Dr. Prius, and Autel MaxiAP200 on Android 8/API 26 and
   newer, including Samsung A35 5G and S8+.
3. **Toyota CAN Evidence Builder 1.0 for Windows** — Windows 10/11 GUI and CLI
   for v2.3/v2.4 manifests, TCB1, BLE alignment, OCR, narration transcription,
   and optional BLE-synchronized Techstream desktop capture.

Start with `docs/INSTALL_ANDROID.md`, `docs/INSTALL_WINDOWS.md`, and the firmware
README. The Windows core has been tested against the supplied 34-session
CANLOG archive. Firmware and Android source still require their normal Arduino
IDE and Android Studio on-device build/test steps, documented in
`docs/VALIDATION.md`.

Safety boundary: passive capture is the default. BLE has no CAN-transmit API.
The firmware contains no actuator, fan, write, clear, reset, coding, SD erase,
or SD format command. Diagnostic normal mode is a separate, explicit,
profile-gated read-only function and must remain off while another tester is
connected.
