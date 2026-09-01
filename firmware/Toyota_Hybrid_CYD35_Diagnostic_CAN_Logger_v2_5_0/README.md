# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.5.0-rc.2

This release candidate adds an exclusive Wi-Fi microSD file manager to the
Dorhea B0DLNJSSFW ESP32-WROOM-32 and ESP32-3248S035R/E32N35T resistive-touch
CYD logger. The Dorhea profile is active by default in RC2. It retains capture package
1.4, TCB1 24-byte records, ToyotaCYD-Sync/1, and the v2.4.2 BLE/SD startup
correction.

## Validated hardware configuration

- CAN TX GPIO25; CAN RX GPIO32
- VP230 CAN-H to OBD-II pin 6; CAN-L to pin 14
- No added 120-ohm termination on an intact vehicle bus
- TFT backlight GPIO27; touch CS GPIO33
- SD SCK/MISO/MOSI/CS GPIO18/19/23/5 on separate HSPI
- Dorhea active-low red RGB LED GPIO4 is driven HIGH during setup
- Landscape rotation 1 touch calibration: Dorhea `{295, 3524, 310, 3487, 3}`;
  original ESP32-3248S035R/E32N35T fallback `{295, 3524, 310, 3487, 7}`

## Wi-Fi SD transfer

The new `WIFI FILES` touchscreen button is enabled only while logging is
stopped and the card is mounted. A second confirmation screen prevents an
accidental mode change. On confirmation the firmware:

1. stops and uninstalls TWAI;
2. deinitializes BLE and releases the CAN/BLE queues;
3. keeps all logging files closed;
4. starts a password-protected `ToyotaCYD-####` access point; and
5. displays its password and `http://192.168.4.1` on the TFT.

The browser interface can list sessions and files, resume individual-file
downloads with HTTP Range, stream an Evidence Builder-ready
`CANLOG_S####.zip` with a `CANLOG/S####/` root, stream the original `S####/`
folder ZIP, and permanently delete a closed session after typed confirmation.
It creates no temporary SD archive and has no upload, format, firmware-update,
or CAN API.
`EXIT / RESTART` reboots into the normal BLE/TWAI logger.

## Deletion-safe session allocation

Session allocation is now `MONOTONIC_V1`. The logger takes the maximum of the
highest valid `S####` directory, `/CANLOG/NEXT_SESSION.TXT`, a recoverable
`NEXT_SESSION.NEW`, and the ESP32 NVS high-water value. It reserves the next
identifier before creating the session directory. Deleted identifiers are not
reused; an interrupted reservation may safely skip a number.

## Arduino IDE

1. Install ESP32 Arduino core **3.3.10** and TFT_eSPI.
2. Apply `TFT_eSPI_User_Setup_CYD35.h` to the active TFT_eSPI `User_Setup.h`.
3. Open the `.ino` from this identically named sketch folder.
4. Select **ESP32 Dev Module** and **Huge APP (3MB No OTA/1MB SPIFFS)**. The
   default 1.2 MB application partition is not suitable.
5. Select the correct COM port, compile, and upload.
6. Follow `docs/releases/v2.5.0/VALIDATION_AND_TEST.md` before vehicle use.

## Safety and release status

TWAI still starts in hardware listen-only mode. Wi-Fi maintenance mode shuts
TWAI down entirely and cannot transmit CAN. Camry Hybrid remains passive-only.
The optional Prius Gen 2 normal mode remains limited to the existing fixed
read-only Mode 01/21 whitelist after explicit touchscreen authorization. There
are no actuator, fan-control, write, clear, reset, coding, erase, SD-format, or
arbitrary remote-CAN commands.

Host C++ syntax and protocol tests pass, but `rc.2` requires Arduino IDE
compilation and CYD bench testing with the actual microSD card before it should
replace v2.4.2 for vehicle captures. v2.4.2 remains the rollback release.
