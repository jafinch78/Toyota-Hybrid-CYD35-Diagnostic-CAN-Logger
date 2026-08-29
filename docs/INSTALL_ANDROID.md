# Android build and installation

## Build the APK

1. Install the current stable Android Studio on Windows and allow it to install
   Android SDK Platform 35 and its bundled JDK 17.
2. Open `android/ToyotaCANSyncRecorder` as a project and wait for Gradle sync.
3. Connect the Samsung phone by USB, enable Developer options and USB debugging,
   approve the computer, then press Android Studio's Run button.
4. Alternatively select **Build > Build APK(s)**. The debug APK appears under
   `app\build\outputs\apk\debug\app-debug.apk` and can be installed with:

   ```bat
   adb install -r app-debug.apk
   ```

The source has `minSdk 26` for Android 8 and `targetSdk 35` for current Android.
This release bundle contains source rather than a signed production APK, so the
PC that builds it controls the signing key.

## Samsung A35 5G

1. Grant **Nearby devices**, **Microphone**, and **Notifications** when asked.
2. In **Settings > Apps > Toyota CAN Sync > Battery**, select **Unrestricted**.
3. In **Battery and device care > Battery > Background usage limits**, add the
   app to **Never sleeping apps** if Samsung pauses long captures.
4. Accept Android's screen-recording confirmation every session.

## Samsung S8+ / Android 8 and newer

1. Grant **Microphone** and **Location**. Android 8 requires Location permission
   and Location services enabled to discover BLE devices even though the app
   does not save location.
2. Disable battery optimization for Toyota CAN Sync.
3. Android 8 records microphone narration but cannot capture another app's
   internal audio. OCR and voice narration are unaffected.
4. For manual APK installation, permit **Install unknown apps** for the app used
   to open the APK, or install it through ADB.

## Capture procedure

1. Insert the CYD microSD card, boot logger v2.4.0, and connect the VP230 to the
   vehicle. Confirm `LISTEN-ONLY 500k` on the CYD.
2. Open Toyota CAN Sync, grant permissions, and connect to `ToyotaCYD-xxxx`.
3. Press **START SYNCED CAPTURE** and accept the screen-recording prompt.
4. Switch to Hybrid Assistant, Dr. Prius, or MaxiAP200 and connect that app to
   its normal OBD adapter. Leave the CYD `DIAG` control off.
5. Speak vehicle actions and observations. Press **ADD NARRATION MARKER** before
   an especially important action if practical.
6. Return to Toyota CAN Sync and press **STOP AND CLOSE CAPTURE**.
7. Press **SHARE LAST CAPTURE ZIP** and save it to Drive, Files, or the Windows
   laptop. The ZIP contains `SCREEN.mp4` and `CAPTURE_SYNC.json`.

If the saved video is black only while a particular diagnostic app is visible,
that app is probably using Android's secure-screen flag. Other apps and spoken
narration can still be captured, but protected pixels cannot be bypassed by a
normal recorder.
