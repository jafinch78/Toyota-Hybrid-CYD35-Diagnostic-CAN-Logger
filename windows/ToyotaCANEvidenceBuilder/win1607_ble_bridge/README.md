# Win1607 BLE Bridge

Transport-only compatibility bridge for Windows 10 version 1607 (build 14393).

Purpose: preserve the existing ToyotaCYD-Sync/1 Python capture workflow while isolating legacy WinRT BLE behavior required by build 14393. The bridge does not parse Toyota CAN traffic, does not perform Evidence Builder analysis, and does not alter the ToyotaCYD-Sync/1 packet format.

## Responsibilities

- Enumerate paired Bluetooth LE devices only. Windows 10 build 14393 requires the ToyotaCYD logger to be paired before GATT access.
- Open service `6ed9f000-4f21-4c8c-a8a7-923c86b40001` with the legacy `BluetoothLEDevice.GetGattService` path.
- Enumerate characteristics with the legacy `GattDeviceService.GetAllCharacteristics` path.
- Locate command characteristic `6ed9f000-4f21-4c8c-a8a7-923c86b40002`.
- Locate response characteristic `6ed9f000-4f21-4c8c-a8a7-923c86b40003`.
- Enable response notifications using `WriteClientCharacteristicConfigurationDescriptorAsync(Notify)`.
- Convert raw command bytes to `IBuffer` and write with `WriteValueAsync(..., WriteWithoutResponse)`.
- Convert notification `IBuffer` values back to raw bytes and forward them to Python immediately.
- Report connection and transport errors.

## Non-responsibilities

The bridge does not own sequence numbering, START_PASSIVE / STOP / MARKER semantics, synchronization fitting, FFmpeg capture, JSON generation, CAN decoding, or evidence processing. Those remain in Python.

The current compatibility adapter also leaves T1/T4 acquisition in Python so the existing `CAPTURE_SYNC.json` schema is unchanged. Because a subprocess/stdio hop is inserted around the GATT operation, real build-14393 testing must quantify the extra synchronization residual before this path is declared timing-equivalent to direct Bleak operation.

## IPC protocol

Line-oriented stdin/stdout protocol:

Commands:

- `CONNECT AUTO`
- `WRITE <hex>`
- `DISCONNECT`
- `QUIT`

Responses/events:

- `READY Win1607_BLE_Bridge protocol=1`
- `OK CONNECTED <device-name>\t<device-id>`
- `OK WRITE`
- `OK DISCONNECTED`
- `RX <hex>`
- `ERR <code> <message>`

`WRITE` accepts only the existing 4-byte ToyotaCYD-Sync/1 clock request or 8-byte session-control request. `RX` carries the response notification unchanged; the current protocol replies are 20 bytes.

## Build target

The Visual C++ project explicitly targets Windows 10 SDK `10.0.14393.0`, x64, and the Visual Studio 2015 `v140` toolset. It uses C++/CX `/ZW /EHsc` and legacy APIs that are present before the 1703 GATT discovery additions.

From a Visual Studio 2015 Developer Command Prompt with SDK 14393 installed:

```bat
BUILD_WIN1607_BRIDGE.bat
```

The build script expects `x64\Release\Win1607_BLE_Bridge.exe` and copies the verified build output to this directory as `Win1607_BLE_Bridge.exe` for the Python adapter.

## Capture use

1. Pair the ESP32 ToyotaCYD logger through Windows Settings first.
2. Build the bridge.
3. From `windows\ToyotaCANEvidenceBuilder`, run:

```bat
RUN_TECHSTREAM_CAPTURE_WIN1607.bat
```

That launcher sets `TOYOTA_BLE_BACKEND=win1607` and points Python at the native helper. The original `RUN_TECHSTREAM_CAPTURE.bat` remains on the direct Bleak backend for modern Windows.

## Validation status

Source integration is not equivalent to runtime validation. The bridge must still be compiled with the actual 14393 SDK/toolset and exercised on Windows 10 version 1607 with a paired ToyotaCYD logger. Required validation includes connect/disconnect, CCCD notification enable, 4-byte sync request/reply, 8-byte START_PASSIVE/STOP/MARKER request/reply, repeated clock bursts, clean capture shutdown, and comparison of BLE fit residuals with the direct modern-Windows path.
