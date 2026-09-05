# Android 6.0.1 / API 23 compatibility

Toyota CAN Sync Recorder 1.0.1 lowers the minimum SDK from API 26 to API 23 while retaining the existing modern-Android code paths.

## Compatibility changes

1. `MainActivity` uses `startService()` on API 23-25 and `startForegroundService()` on API 26+.
2. `CaptureService` uses `NotificationCompat.Builder`, which works on API 23 while remaining channel-aware on API 26+.
3. Notification-channel creation remains restricted to API 26+.
4. Existing API 29+, API 30+, API 31+, and API 33+ branches for foreground-service types, BLE permissions, and notification permission remain unchanged.
5. The project minimum SDK is now 23; `compileSdk` and `targetSdk` remain 35.

## Android 6.0.1 validation

Validated on 2026-09-05 on the API 23 field device:

- APK installs and launches.
- BLE scan and ToyotaCYD connection succeed.
- GATT service discovery and response notifications succeed.
- MediaProjection authorization succeeds.
- Foreground capture service starts without the former API-26 `startForegroundService()` crash.
- `SCREEN.mp4` was confirmed by the operator.
- `CAPTURE_SYNC.json` recorded the BLE protocol, API 23 device metadata, synchronized control events, markers, video anchors, and `closed_cleanly: true`.

## Modern Android behavior

The API-23 changes are version-gated. On API 26 and newer, including the Samsung A35 5G path previously used with v1.0, the app continues to call `startForegroundService()`. The foreground notification remains backed by the same channel on API 26+, now built through AndroidX `NotificationCompat`.

The A35 5G v1.0 installation does not need to be replaced solely for this compatibility change. If 1.0.1 is installed later, these changes are intended to preserve its existing modern-Android behavior.
