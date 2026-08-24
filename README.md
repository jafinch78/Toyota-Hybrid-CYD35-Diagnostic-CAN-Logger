# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.2.0

Use the `.ino` as the only Arduino sketch tab in a folder with the same base name.

Hardware pins: CAN TX GPIO25, CAN RX GPIO32, TFT backlight GPIO27, touch CS GPIO33,
SD SCK/MISO/MOSI/CS GPIO18/19/23/5. Touch calibration is
`{295, 3524, 310, 3487, 7}`.

Raw traffic is saved as `RAW_nnn.TCB` to reduce SD overhead. Convert it on a PC:

```sh
python tcb_to_csv.py RAW_000.TCB RAW_001.TCB -o RAW.csv
```

The temperature page shows Engine Coolant, Engine Intake Air, Catalyst B1S1,
converter, MG1/MG2 inverter, MG1/MG2 motor, all three HV battery temperatures,
battery intake temperature, and battery average temperature. Diagnostic requests
are read-only and remain disabled until a strong Prius Gen 2 profile is detected
and the user presses DIAG.
