# Toyota CAN Sync Recorder for Android 1.0.1

Native Android source for Samsung A35 5G and Samsung S8+ devices running
Android 8.0/API 26 or newer. The app connects directly to the CYD over BLE,
records the Android display and microphone, and exports `SCREEN.mp4` plus
`CAPTURE_SYNC.json` as one shareable ZIP.

The diagnostic application remains in the foreground after capture starts.
The recorder performs no OBD connection and sends no CAN command. Its BLE
control surface can only start/stop passive SD logging and add markers.

Before starting a synchronized capture, version 1.0.1 asks the operator to
confirm that the separate OBD reader application has already been opened and
connected. The prompt does not connect to or control the OBD adapter.

Open this folder in Android Studio. See `docs/INSTALL_ANDROID.md` in the release
root for build, installation, Samsung permission, and capture instructions.
