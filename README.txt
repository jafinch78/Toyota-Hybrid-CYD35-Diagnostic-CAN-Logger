Toyota Hybrid CYD 3.5 Diagnostic CAN Logger v2.3.0
==================================================

Validated hardware integration
------------------------------
- ESP32-3248S035R / E32R35T resistive-touch display
- VP230/SN65HVD230: GPIO25 TX, GPIO32 RX
- TFT_eSPI display and XPT2046 touch retain TFT_eSPI's normal SPI controller
- microSD uses a separate SPIClass(HSPI) object
- SD pins: SCK 18, MISO 19, MOSI 23, CS 5
- Touch CS 33
- Measured touch calibration: {295, 3524, 310, 3487, 7}
- Target ESP32 Arduino core: 3.3.10
- TFT_eSPI_User_Setup_CYD35.h is a reference for the library's active
  User_Setup.h and must not be added as a second Arduino sketch tab.

Changes from v2.2.0
-------------------
- ISO-TP flow control now transmits immediately in the high-priority CAN receive
  task, before display and SD work can delay it.
- Diagnostic timeouts are inactivity-based and UDS response-pending is handled.
- CHECKPOINT.JSON is refreshed with a recoverable two-generation replacement
  every five seconds while logging.
- SESSION.OPEN remains after unexpected power loss and is removed on clean stop.
- TWAI missed, overrun, transmit, arbitration, bus-error and bus-off counters are
  recorded, with automatic controller recovery after bus-off.
- Adds passive Camry AHV40 PROBABLE candidates: gear (0x120, redundant 0x2D0),
  engine RPM (0x2C4), and engine coolant (0x3B9).
- Startup Serial output is readable at 115200 baud and no longer recursively
  lists the entire card unless PRINT_SD_DIRECTORY_AT_BOOT is enabled.

Safety
------
- TWAI is in NORMAL mode because read-only diagnostic requests and ISO-TP flow
  control require transmission.
- DIAG remains OFF until a strong Prius Gen 2 profile is detected and the user
  explicitly touches DIAG OFF.
- The firmware contains no fan-control, actuator, write, clear, reset, coding,
  erase-card, or format-card commands.
- Keep the vehicle stationary during initial testing.
- Do not add a 120-ohm termination resistor to an intact vehicle CAN bus.

First test
----------
1. Insert the microSD card with the ESP32 powered off.
2. Connect USB only; leave VP230 CANH/CANL disconnected for the first boot.
3. Upload the sketch and open Serial Monitor at 115200 baud.
4. Confirm the SD CARD summary. Full directory listing is disabled by default.
5. Touch STOP LOG once and confirm the button changes to START LOG.
6. Touch START LOG once and confirm a new /CANLOG/S#### session is created.
7. The button should show DIAG N/A until a strong Gen 2 vehicle fingerprint is
   present. Camry operation remains passive-only.
8. After bench validation, connect to the vehicle using the established safe
   wiring and test logging before enabling diagnostics.

Retrieving captures
-------------------
Stop logging before removing power. Remove the card and upload the complete
session directory, including MANIFEST.JSON, SIGNALS.CSV, RAW_###.TCB,
CHECKPOINT.JSON, DECODED.CSV, DIAGNOSTICS.CSV, EVENTS.CSV, and README.TXT.
If SESSION.OPEN remains, the session was not stopped cleanly. If CHECKPOINT.JSON
is absent, include CHECKPOINT.OLD. Uploading the TCB
files directly is supported; tcb_to_csv.py is included for local conversion.
