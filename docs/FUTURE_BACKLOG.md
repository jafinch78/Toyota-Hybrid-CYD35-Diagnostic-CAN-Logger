# Firmware backlog

## Implemented in v2.5.0-rc.1: deletion-safe session folder numbering

The CYD logger now allocates `/CANLOG/S####` identifiers monotonically even
when older session folders are deleted to reclaim microSD space. RC1:

- inspects existing `S####` directories at startup and never chooses a number
  lower than the highest valid directory already present;
- persists a recoverable next-session counter using SD temporary-file/rename
  recovery plus an ESP32 NVS high-water value;
- ignores malformed folder names without reusing their apparent numbers;
- reserves the identifier before opening session files and recovers safely after a
  power loss; and
- records the allocator policy and selected identifier in `MANIFEST.JSON` and
  the startup event stream.

Capture package 1.4 and existing session contents remain unchanged. Actual-CYD
bench validation is still required before promoting v2.5.0 from release
candidate to stable.

## Later Wi-Fi enhancements

- Add an Evidence Builder `Import from CYD` client using file API v1.
- Add per-file SHA-256 manifests at clean session close if measured SD and CPU
  overhead are acceptable.
- Do not add dashboards, Android offline decoding, arbitrary upload, OTA, or CAN
  control to the maintenance-mode firmware without a separate design review.
