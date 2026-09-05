# Toyota CAN Sync Recorder for Android 1.0.1

Native Android source for Samsung A35 5G and older Samsung field devices running
Android 6.0/API 23 or newer. The API-23 compatibility path uses the legacy
`startService()` entry point and an AndroidX-compatible foreground notification;
Android 8.0/API 26 and newer continue to use `startForegroundService()`. The app
connects directly to the CYD over BLE, records the Android display and microphone,
and exports `SCREEN.mp4` plus `CAPTURE_SYNC.json` as one shareable ZIP.

The diagnostic application remains in the foreground after capture starts.
The recorder performs no OBD connection and sends no CAN command. Its BLE
control surface can only start/stop passive SD logging and add markers.

Before starting a synchronized capture, version 1.0.1 asks the operator to
confirm that the separate OBD reader application has already been opened and
connected. The prompt does not connect to or control the OBD adapter.

See `API23_COMPATIBILITY.md` for the Android 6.0.1 validation notes.

Open this folder in Android Studio. See `docs/INSTALL_ANDROID.md` in the release
root for build, installation, Samsung permission, and capture instructions.

Manual copy of the ZIP file can be performed from the phone to a computer via USB connection. The A35 may prevent Samsung My Files from browsing Android/data . The S8+ on Android 8 is more likely to permit access through My Files or USB. Selecting the USB Charging from Notifications dropdown and checking Transferring File / Android Auto was required for the A35. 
Generated ZIP location:
>  Internal storage/Android/data/com.jafinch78.toyotacansync/files/Movies/ ToyotaCANSync/CAPTURE_YYYYMMDD_HHMMSS/ SCREEN.mp4 CAPTURE_SYNC.json
