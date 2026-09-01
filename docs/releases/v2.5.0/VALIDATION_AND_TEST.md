# Validation and CYD bench test

## Completed before RC packaging

- Host C++17 syntax validation with Arduino/ESP32 API stubs passes.
- The embedded browser JavaScript passes `node --check`.
- ZIP method-0 headers, data descriptors, CRC-32, central directory, and
  extraction were validated in memory with Python `zipfile`.
- Static safety guards found no Mode `2E`, arbitrary remote CAN handler, SD
  format, file upload, firmware update, or automatic control command.
- TCB1 remains protected by the 24-byte packed-record `static_assert`.
- The highest existing `S####`, SD committed/pending counters, and NVS counter
  all participate in monotonic allocation; malformed directories are ignored.

The final ESP32 Arduino core compile and physical transfer tests cannot be
performed in the release environment. Complete every step below before calling
v2.5.0 stable.

## Arduino IDE compile and upload

1. Keep stable v2.4.2 available as the rollback ZIP.
2. Use ESP32 Arduino core 3.3.10 and the tested TFT_eSPI `User_Setup.h`.
3. Select `ESP32 Dev Module`.
4. Select **Huge APP (3MB No OTA/1MB SPIFFS)**.
5. Compile and record program-storage and global-memory usage.
6. Upload with the microSD card initially removed, then reset once.
7. Confirm the TFT is stable and normal BLE/TWAI startup completes.
8. Confirm the Dorhea red RGB LED on GPIO4 remains off after setup.

## SD and normal-logger regression

1. Power down, insert the known 483 MB card, and boot.
2. Confirm one startup, no reboot loop, and these Serial prefixes:

   ```text
   # ToyotaHybridCAN Diagnostic Logger v2.5.0-rc.2
   # CYD BOARD,DORHEA_B0DLNJSSFW_ESP32-WROOM-32,touch_flags=3,rotation=1
   # SD READY,max_open_files=10,session=deferred
   # SESSION ALLOCATOR,policy=MONOTONIC_V1,...
   # BLE READY,ToyotaCYD-....
   # EVENT,...,TWAI_READY,500 kbps LISTEN_ONLY; GPIO25 TX; GPIO32 RX
   ```

3. Confirm Android BLE connection still works.
4. Start and stop one empty bench session.
5. Start and stop a second session and confirm its number increases.
6. Confirm no `no free file descriptors`, panic, or repeated reset occurs.

## Wi-Fi entry and browser

1. With logging stopped, tap `WIFI FILES`.
2. Test `CANCEL`; normal UI and BLE must remain functional.
3. Enter again and tap `START WIFI`.
4. Confirm Serial reports `WIFI_LOGGER_SERVICES_STOPPED` before `WIFI READY`.
5. Confirm the TFT shows SSID, password, `http://192.168.4.1`, SD usage, and
   `READY - OPEN BROWSER`.
6. Connect a Samsung phone or Windows laptop to the shown WPA2 network. Accept
   the expected “no internet” notice and remain connected.
7. Open `http://192.168.4.1` and confirm session and file lists load.
8. Confirm each session offers both `Download CANLOG ZIP` and the original
   `Download S#### folder ZIP` option.

The Dorhea B0DLNJSSFW File Manager Touch Test and Wi-Fi path were physically
tested successfully with rotation 1 and `{295,3524,310,3487,3}`. The complete
logger RC2 still requires the normal-screen, confirmation-screen, and Wi-Fi
screen touch matrix before stable release.

## Transfer integrity

1. Download a small text/JSON file and compare its byte size with the web list.
2. Download `RAW_000.TCB`; compare SHA-256 with the same SD file after a later
   direct-card read when practical.
3. Interrupt a large individual download, resume it, and verify the final hash.
4. Download a full session ZIP and confirm:
   - it opens without repair;
   - it contains one `S####` root folder;
   - file count and sizes match the browser list; and
   - `MANIFEST.JSON` and TCB files process in Evidence Builder.
5. Download `CANLOG_S####.zip` and confirm:
   - its root is `CANLOG/S####/`;
   - it passes ZIP integrity testing; and
   - Evidence Builder accepts it directly as a CYD CANLOG ZIP.
6. Disconnect and reconnect the Wi-Fi client, then repeat one download.

## Deletion and monotonic-number test

1. Create two disposable clean empty sessions and note their identifiers.
2. In Wi-Fi mode, delete the older one. The browser must require typing
   `DELETE-S####`.
3. Confirm a session containing `SESSION.OPEN` cannot be deleted.
4. Tap `EXIT / RESTART`; confirm the normal logger, BLE, and LISTEN_ONLY TWAI
   return after one reboot.
5. Create another disposable session. Its number must be greater than every
   number previously reserved and must not reuse the deleted identifier.
6. Confirm `/CANLOG/NEXT_SESSION.TXT` contains the following identifier.

## Vehicle regression after all bench tests pass

Perform the first test stationary with diagnostics off. Verify passive logging,
BLE time synchronization, clean stop, and Evidence Builder processing before
testing the optional Prius Gen 2 read-only diagnostic mode separately. Incorrect
CAN transmission can affect vehicle behavior; Camry and unresolved profiles
remain passive-only.
