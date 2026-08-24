Toyota Hybrid CYD 3.5 Diagnostic CAN Logger v2.2.0
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

Changes from v2.1.0
-------------------
- Raw frames use compact, batched TCB1 binary records instead of per-frame CSV.
- A priority diagnostic queue protects ISO-TP response and flow-control timing.
- Adds a touch-selectable temperature page and expanded decoded CSV columns.
- Adds read-only Mode 01 coolant, intake-air, and catalyst thermal requests.
- Fixes the NHW20 C3 MG1/MG2 motor temperature byte assignment.
- Includes tcb_to_csv.py for PC conversion to portable CSV.

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
3. Upload the sketch and open Serial Monitor at 921600 baud.
4. Confirm SD CARD and SD DIRECTORY LIST messages.
5. Touch STOP LOG once and confirm the button changes to START LOG.
6. Touch START LOG once and confirm a new /CANLOG/S#### session is created.
7. DIAG OFF should remain blue and should be rejected without a strong Gen 2
   vehicle fingerprint.
8. After bench validation, connect to the vehicle using the established safe
   wiring and test logging before enabling diagnostics.

Retrieving captures
-------------------
Stop logging before removing power. Remove the card and upload the complete
session directory, including MANIFEST.JSON, SIGNALS.CSV, RAW_###.TCB,
DECODED.CSV, DIAGNOSTICS.CSV, EVENTS.CSV, and README.TXT. Uploading the TCB
files directly is supported; tcb_to_csv.py is included for local conversion.
