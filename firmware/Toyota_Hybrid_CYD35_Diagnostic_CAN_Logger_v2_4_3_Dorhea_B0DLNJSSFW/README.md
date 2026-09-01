# Toyota Hybrid CYD35 Logger v2.4.3-rc.1 — Dorhea B0DLNJSSFW

This is the isolated Dorhea build. Its touch mapping and active-low red LED behavior are based on the board tests reported for Amazon board B0DLNJSSFW.

## Fixed board profile

- Board: Dorhea B0DLNJSSFW, ESP32-WROOM-32
- Touch calibration: `{295, 3524, 310, 3487, 3}` (touch-tested)
- VP230 TXD: GPIO22
- VP230 RXD: GPIO35
- Red board LED: GPIO4 active-low, driven HIGH/off during setup
- CAN: 500 kbit/s, LISTEN_ONLY at startup

The GPIO22/GPIO35 VP230 mapping is a **candidate requiring an in-vehicle receive test**. It is intentionally isolated from the N35T build.

## What changed from v2.4.2

- Retains the proven first-missing-directory allocator. Starting a log performs no session-counter NVS write and no `NEXT_SESSION` SD-file transaction.
- Keeps exclusive Wi-Fi file transfer from the later development branch.
- Wi-Fi maintenance **clears files but never deletes the `S####` folder**. It writes `SESSION_TOMBSTONE.JSON`, preserving the session identifier as the counter.
- Adds the tested Dorhea touch flags and turns off its active-low GPIO4 red LED.
- Records the board profile, GPIO22/GPIO35 mapping, and candidate pin status in `MANIFEST.JSON`.

## Arduino setup

1. Use an ESP32 Arduino core and TFT_eSPI compatible with the v2.4.2 build.
2. Copy the definitions from `TFT_eSPI_User_Setup_CYD35.h` into TFT_eSPI's active `User_Setup.h`.
3. Open the `.ino` whose name matches this folder and compile for ESP32-WROOM-DA Module or the same board target used for the successful Dorhea touch test.
4. Connect VP230 TXD to GPIO22 and RXD to input-only GPIO35. Verify shared ground and 3.3 V logic.

This is an RC source package. Do not promote the Dorhea profile to stable until the release validation matrix confirms CAN RX traffic and clean repeated start/stop sessions in a vehicle.

