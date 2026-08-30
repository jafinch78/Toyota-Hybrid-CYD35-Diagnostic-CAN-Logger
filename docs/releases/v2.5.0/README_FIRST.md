# Toyota Hybrid CYD35 Logger v2.5.0-rc.1

This is a release candidate for bench testing. Stable v2.4.2 remains the
rollback firmware until the actual ESP32 CYD passes the checks in
`VALIDATION_AND_TEST.md` with its microSD card installed.

New functions:

- fourth `WIFI FILES` touchscreen button and confirmation screen;
- exclusive WPA2 Wi-Fi maintenance mode at `http://192.168.4.1`;
- browser session/file listing;
- resumable individual downloads;
- direct complete-session ZIP streaming without an SD temporary archive;
- guarded permanent deletion of clean sessions; and
- deletion-safe monotonic `S####` allocation backed by the SD card and NVS.

Capture package 1.4, TCB1, ToyotaCYD-Sync/1, GPIO25/GPIO32 CAN wiring, touch
calibration, and the read-only diagnostic safety model are unchanged.
