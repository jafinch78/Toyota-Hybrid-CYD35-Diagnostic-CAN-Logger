# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.3.0

Use the `.ino` as the only Arduino sketch tab in a folder with the same base name.
The target is ESP32 Arduino core 3.3.10. `TFT_eSPI_User_Setup_CYD35.h` is included
as a reference for the active TFT_eSPI `User_Setup.h`; do not add it as a sketch
tab.

Hardware pins: CAN TX GPIO25, CAN RX GPIO32, TFT backlight GPIO27, touch CS GPIO33,
SD SCK/MISO/MOSI/CS GPIO18/19/23/5. Touch calibration is
`{295, 3524, 310, 3487, 7}`.

Raw traffic is saved as `RAW_nnn.TCB` to reduce SD overhead. Convert it on a PC:

```sh
python tcb_to_csv.py RAW_000.TCB RAW_001.TCB -o RAW.csv
```

v2.3 keeps the proven TCB1 raw format and adds:

- immediate ISO-TP flow control from the high-priority CAN receive task;
- inactivity-based diagnostic timeouts and response-pending handling;
- recoverable two-generation five-second `CHECKPOINT.JSON` updates plus a
  `SESSION.OPEN` marker;
- TWAI missed/overrun/error/bus-off metrics with automatic bus recovery;
- passive, profile-gated Camry AHV40 candidates for gear, engine RPM, and
  engine coolant temperature;
- clearer `DIAG N/A` behavior until a strong Prius Gen 2 profile is present.

The temperature page shows Engine Coolant, Engine Intake Air, Catalyst B1S1,
converter, MG1/MG2 inverter, MG1/MG2 motor, all three HV battery temperatures,
battery intake temperature, and battery average temperature. Diagnostic requests
are read-only and remain disabled until a strong Prius Gen 2 profile is detected
and the user presses DIAG.
Stopping logging also disables diagnostic polling so the firmware never emits
unrecorded diagnostic traffic.

Camry decoding is passive-only. The current AHV40 mappings are marked
`PROBABLE`, not confirmed, in each session's `SIGNALS.CSV`.
