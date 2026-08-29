# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.2

Targets the ESP32-3248S035R/E32R35T resistive-touch CYD and SN65HVD230/VP230
on a 500 kbit/s Toyota hybrid CAN bus.

## Validated hardware configuration

- CAN TX GPIO25; CAN RX GPIO32
- VP230 CAN-H to OBD-II pin 6; CAN-L to pin 14
- No added 120-ohm termination on an intact vehicle bus
- TFT backlight GPIO27; touch CS GPIO33
- SD SCK/MISO/MOSI/CS GPIO18/19/23/5 on separate HSPI
- Touch calibration `{295, 3524, 310, 3487, 7}`

## Corrected startup sequence

v2.4.1 mounted a 16-descriptor SD filesystem and allocated CAN/TWAI resources
before BLE. On the tested ESP32-D0WD-V3, BLE server creation then failed and the
firmware rebooted through a null address. v2.4.2 reserves BLE service resources
first, uses a 1,024-record CAN queue, mounts SD with 10 descriptors, and begins
advertising only after setup completes. BLE allocation failures are nonfatal.

## Arduino IDE

1. Install ESP32 Arduino core 3.3.10 and TFT_eSPI.
2. Apply `TFT_eSPI_User_Setup_CYD35.h` to the active TFT_eSPI `User_Setup.h`.
3. Open the `.ino` from this identically named sketch folder.
4. Select `ESP32 Dev Module`, the known working settings, and the correct COM
   port; compile and upload.
5. Insert the card and follow the parent `VALIDATION_AND_TEST.md` bench test.

## Safety

TWAI starts in hardware listen-only mode. BLE has no CAN-transmit API. Camry
Hybrid remains passive-only. The optional normal diagnostic mode requires a
strong Prius Gen 2 profile, active logging, no recently observed external
tester, and an explicit touchscreen action; it uses only fixed read-only Mode
01/21 requests. No actuator, fan, write, clear, reset, coding, erase, or format
command is present.

Capture package 1.4, TCB1 24-byte records, and ToyotaCYD-Sync/1 are unchanged.
