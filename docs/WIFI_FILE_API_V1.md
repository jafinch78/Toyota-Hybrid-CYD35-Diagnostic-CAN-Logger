# Toyota CYD Wi-Fi file API v1

Firmware v2.5.0 introduces an HTTP interface at `http://192.168.4.1` while the
CYD is in exclusive Wi-Fi maintenance mode. The CYD creates its own WPA2 access
point; no router or internet connection is required.

## Operating boundary

- Logging must be stopped before entry.
- All session files are closed.
- TWAI is stopped and uninstalled.
- BLE is deinitialized.
- No CAN, firmware upload, arbitrary filesystem upload, or SD-format endpoint
  exists.
- Exiting the mode restarts the CYD rather than attempting to rebuild BLE and
  TWAI in the same heap lifetime.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Mobile-friendly browser file manager |
| `GET` | `/api/v1/info` | Device, storage, next-session and per-boot delete token |
| `GET` | `/api/v1/sessions` | Valid `S####` directories, file counts, sizes and clean state |
| `GET` | `/api/v1/files?session=S####` | Files within one validated session |
| `GET` | `/api/v1/file?session=S####&name=FILE` | File download; supports one HTTP `Range` |
| `GET` | `/api/v1/session.zip?session=S####` | Direct stored ZIP stream with an `S####/` root |
| `POST` | `/api/v1/delete?...` | Permanently delete one clean, closed session |

Deletion requires all three query parameters:

- `session=S####`
- `confirm=DELETE-S####`
- the current `token` returned by `/api/v1/info`

The token changes every time Wi-Fi maintenance mode starts. The path validator
accepts exactly `S` plus four digits and download names containing only letters,
digits, dot, underscore, or hyphen. `SESSION.OPEN` blocks deletion.

## Folder ZIP behavior

The ESP32 emits a standards-compatible ZIP using method 0 (stored) and data
descriptors. It calculates CRC-32 while reading and does not create a temporary
archive on the microSD card. The first release supports up to 128 files and
rejects ZIP64-sized files. An interrupted whole-folder ZIP should be downloaded
again; individual files support resumed downloads.

## Windows integration direction

Evidence Builder v1.1.0 can use the JSON endpoints to discover and copy a
session file-by-file, resume large TCB files, compare byte counts, and then pass
the local session folder into its existing evidence pipeline. This preserves a
deterministic import path without requiring browser ZIP extraction.
