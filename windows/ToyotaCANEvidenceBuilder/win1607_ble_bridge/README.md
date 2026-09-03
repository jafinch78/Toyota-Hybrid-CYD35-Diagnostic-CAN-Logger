# Win1607 BLE Bridge

Transport-only compatibility bridge for Windows 10 version 1607 (build 14393).

Purpose: preserve the existing ToyotaCYD-Sync/1 Python capture workflow while isolating legacy WinRT BLE behavior required by build 14393. The bridge does not parse Toyota CAN traffic, does not perform Evidence Builder analysis, and does not alter the ToyotaCYD-Sync/1 packet format.

## Responsibilities

- Connect only to an already paired ToyotaCYD BLE device.
- Open service `6ed9f000-4f21-4c8c-a8a7-923c86b40001`.
- Open command characteristic `6ed9f000-4f21-4c8c-a8a7-923c86b40002`.
- Open response characteristic `6ed9f000-4f21-4c8c-a8a7-923c86b40003`.
- Enable notifications on the response characteristic using the CCCD.
- Accept raw command bytes from the Python process and write them without modifying their contents.
- Emit raw response-notification bytes to the Python process as soon as they arrive.
- Report connection and transport errors.

## Non-responsibilities

The bridge must not own sequence numbering, START_PASSIVE / STOP / MARKER semantics, T1/T4 timestamps, synchronization fitting, FFmpeg capture, JSON generation, CAN decoding, or evidence processing. Those remain in Python.

## IPC protocol

The proposed line-oriented protocol is intentionally small:

- `CONNECT <device-id>`
- `WRITE <hex>`
- `DISCONNECT`
- `QUIT`

Responses/events:

- `OK CONNECTED`
- `OK WRITE`
- `OK DISCONNECTED`
- `RX <hex>`
- `ERR <code> <message>`

`WRITE` must accept both the 4-byte ToyotaCYD-Sync/1 clock request and the 8-byte session-control request unchanged. `RX` normally carries the 20-byte notification response unchanged.

## Build target

The implementation must target the Windows 10 SDK 14393 API surface and must not depend on Bluetooth APIs introduced in Windows 10 1703 or later. A build on an actual Windows 10/Visual Studio toolchain is required before this component can be considered validated.
