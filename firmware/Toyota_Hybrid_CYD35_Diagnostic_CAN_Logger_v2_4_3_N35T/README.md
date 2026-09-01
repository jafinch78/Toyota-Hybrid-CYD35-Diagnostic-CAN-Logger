# Toyota Hybrid CYD35 Logger v2.4.3-rc.1 — N35T

This build advances the known-good v2.4.2 logger design for the ESP32-3248S035R / E32N35T resistive-touch board.

## Fixed board profile

- Board: ESP32-3248S035R / E32N35T
- Touch calibration: `{295, 3524, 310, 3487, 7}`
- VP230 TXD: GPIO25
- VP230 RXD: GPIO32
- CAN: 500 kbit/s, LISTEN_ONLY at startup

Do not use this sketch on the Dorhea B0DLNJSSFW board; use the separate Dorhea folder.

## What changed from v2.4.2

- Retains the proven first-missing-directory allocator. Starting a log performs no session-counter NVS write and no `NEXT_SESSION` SD-file transaction.
- Keeps exclusive Wi-Fi file transfer from the later development branch.
- Wi-Fi maintenance **clears files but never deletes the `S####` folder**. It writes `SESSION_TOMBSTONE.JSON`, preserving the session identifier as the counter.
- Records the fixed board profile and CAN pins in `MANIFEST.JSON`.

## Arduino setup

1. Use an ESP32 Arduino core and TFT_eSPI compatible with the v2.4.2 build.
2. Copy the definitions from `TFT_eSPI_User_Setup_CYD35.h` into TFT_eSPI's active `User_Setup.h`.
3. Open the `.ino` whose name matches this folder and compile for your established N35T ESP32 board target.
4. Keep the VP230 connection on GPIO25 TXD and GPIO32 RXD.

This is an RC source package. A local Arduino toolchain was not available for the source preparation pass; complete the bench matrix in the release validation document before promoting it to stable.

