# Android build and installation

## Build the APK

1. Install the current stable Android Studio from
   <https://developer.android.com/studio/install>. Android 17/API 37 may remain
   installed, but also install **Android 15 / API 35** in SDK Manager.
2. From Android Studio's startup screen select **Open**, then open the complete
   `android/ToyotaCANSyncRecorder` folder—the folder containing
   `settings.gradle`. Select **Trust Project** when prompted.
3. Confirm the project configuration:

   - `compileSdk 35`
   - `targetSdk 35`
   - `minSdk 23` (required for the Android 6.0.1 / API 23 field device)
   - Gradle JDK 17

   API 35 and 37 can coexist. Do not change `minSdk` to 35 or 37.
4. Wait for Gradle sync and dependency downloads. **Download external
   annotations for dependencies** may remain checked; it is optional and does
   not change the app.
5. If the project has no generated Gradle wrapper and Android Studio selects
   incompatible Gradle 9.x, install the official Gradle 8.9 binary distribution
   under `C:\Gradle\gradle-8.9`, then select:

   **File > Settings > Build, Execution, Deployment > Build Tools > Gradle**

   Set **Distribution** to **Local installation**, location to
   `C:\Gradle\gradle-8.9`, and **Gradle JDK** to JDK 17. Then run
   **Sync Project with Gradle Files**.
6. Connect the Samsung phone by USB, enable Developer options and USB debugging,
   approve the computer, then press Android Studio's Run button.
7. Alternatively select **Build > Generate App Bundles or APKs > Generate
   APKs**. The debug APK appears under
   `app\build\outputs\apk\debug\app-debug.apk` and can be installed with:

   ```bat
   adb install -r app-debug.apk
   ```

The source has `minSdk 23` for Android 6.0.1 and `targetSdk 35` for current Android.
This release bundle contains source rather than a signed production APK, so the
PC that builds it controls the signing key.

Android Studio's **Run** button builds, debug-signs, installs, and launches the
app on the selected USB device. A separately generated APK is only needed for
manual transfer/backup. Once installed, the app runs normally with Developer
options and USB debugging disabled.

If Windows Defender Firewall prompts for `adb.exe`, allow **Private networks**
only; public-network access is unnecessary for USB deployment.

To enable Developer options on a Samsung phone: open **Settings > About phone >
Software information**, tap **Build number** seven times, enter the device PIN,
then enable **USB debugging** under the new **Developer options** menu.

## Samsung A35 5G

1. Grant **Nearby devices**, **Microphone**, and **Notifications** when asked.
2. In **Settings > Apps > Toyota CAN Sync > Battery**, select **Unrestricted**.
3. In **Battery and device care > Battery > Background usage limits**, add the
   app to **Never sleeping apps** if Samsung pauses long captures.
4. Accept Android's screen-recording confirmation every session.

## Samsung S8+ / Android 6.0.1 (API 23) and newer

1. Grant **Microphone** and **Location**. On Android 6.0.1/API 23, BLE scanning
   requires runtime Location permission; Location services may also need to be
   enabled even though the app does not save location.
2. Disable battery optimization for Toyota CAN Sync.
3. Android 6.0.1 records microphone narration but cannot capture another app's
   internal audio. OCR and voice narration are unaffected.
4. For manual APK installation, permit **Install unknown apps** for the app used
   to open the APK, or install it through ADB.

## Capture procedure

1. Insert the CYD microSD card, boot logger v2.4.2, and connect the VP230 to the
   vehicle. Confirm `LISTEN-ONLY 500k` on the CYD.
2. Open Toyota CAN Sync, grant permissions, and connect to `ToyotaCYD-xxxx`.
3. Press **START SYNCED CAPTURE** and accept the screen-recording prompt.
   Version 1.0.1 first asks you to confirm that the separate OBD reader app has
   already been opened and connected; select **NOT YET** if it is not ready.
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
