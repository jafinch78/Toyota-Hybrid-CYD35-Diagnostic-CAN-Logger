# Simplified Capture Firmware — Validated TVM1 Contract Amendment

Date: 2026-09-28

This amendment is normative for `feature/logger-simplified-capture-v2.6` and supersedes conflicting details in:

- `2026-09-27-simplified-capture-logger-design.md`
- `2026-09-27-simplified-capture-offline-contract-alignment.md`

The validated offline compatibility boundary is recorded on `feature/native-session-preprocessor-impl` and ends with:

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```

The firmware implementation must therefore emit the exact native contract already consumed by the validated preprocessor. It must not implement the older draft `TCM1` framing.

## 1. Canonical Native Session Layout

For a CAN-only session the firmware writes:

```text
/CANLOG/S####/
    SESSION.META
    RAW_000.TCB
    RAW_001.TCB        # only after normal 25 MiB rotation
    ...
```

There is **no native `SESSION.OPEN` marker in TVM1 v1**. Clean/unclean state is authoritative from `SESSION.META`:

- a valid `SESSION_CLOSE` record with `clean=1` means clean close;
- missing/invalid `SESSION_CLOSE` means unclean;
- the offline expander creates legacy `SESSION.OPEN` only when expanding an unclean native session for legacy compatibility.

Existing historical/legacy sessions containing `SESSION.OPEN` remain readable and must not be rewritten.

## 2. Canonical `SESSION.META` Framing

Firmware must match `docs/TVM1_SESSION_META_BINARY_SPEC.md` from the validated preprocessor lineage.

### File header — exactly 32 bytes

```text
0   u8[4]  magic = "TVM1"
4   u8     major = 1
5   u8     minor = 0
6   u16    header_size = 32
8   u32    session_number
12  u32    header_flags = 0
16  u64    session_create_us
24  u32    header_crc32     # CRC-32/ISO-HDLC of bytes 0..23
28  u32    reserved = 0
```

All multi-byte values are little-endian.

### Record envelope

```text
0   u16    sync = 0xA55A
2   u16    total_record_length = 24 + payload_length
4   u16    record_type
6   u8     stream_id        # 0 = session-level
7   u8     flags
8   u32    sequence         # starts at 1, monotonic per metadata file
12  u64    time_us          # same monotonic clock as TCB1
20  byte[] payload
... u32    crc32             # envelope+payload, excluding trailing CRC
```

Minimum record length is 24 bytes. Firmware must never emit a record larger than 4096 bytes in TVM1 v1.

CRC is CRC-32/ISO-HDLC, equivalent to Python `zlib.crc32()` and the reflected polynomial `0xEDB88320`.

## 3. Stream Registration

Initial IDs:

```text
stream_id 0 = session metadata
stream_id 1 = CAN
```

CAN `STREAM_REGISTER` uses:

```text
stream_type = 1          # CAN
raw_format_id = 1        # TCB1
raw_format_major = 1
raw_format_minor = 0
direction_caps = 0x03    # RX and TX observable
config_version = 0
config_length = 0
nominal_rate = 500000
```

BTH stream type 2 and AVC-LAN stream type 3 remain reserved by the contract. This firmware phase does not invent their raw formats.

## 4. Required TVM1 Records for CAN Firmware

The first simplified firmware must implement at least:

- `0x0001 SESSION_START`
- `0x0002 STREAM_REGISTER`
- `0x0003 STREAM_START`
- `0x0004 STREAM_STOP`
- `0x0005 STREAM_FILE_OPEN`
- `0x0006 STREAM_FILE_CLOSE`
- `0x0010 CLOCK_SYNC`
- `0x0011 USER_MARKER`
- `0x0020 HEALTH_SNAPSHOT`
- `0x0021 STREAM_COUNTERS`
- `0x0022 STORAGE_HEALTH`
- `0x0030 EVENT`
- `0x0031 DIAGNOSTIC_STATE`
- `0x0032 BUS_STATE`
- `0x00FE SESSION_CLOSE`

Payloads must exactly match the validated TVM1 binary specification. Unknown/future record types are an offline compatibility concern; the firmware need only emit types it implements.

## 5. TCB1 Is Unchanged

The CAN stream remains the existing 16-byte TCB1 file header followed by packed 24-byte `CapturedFrame` records:

```text
uint64 time_us
uint32 can_id
uint8  data[8]
uint8  dlc
uint8  extended
uint8  rtr
uint8  direction
```

The current 25 MiB rotation threshold remains the initial firmware default. Rotation is a physical-file operation inside stream 1, not a new stream.

Logger diagnostic requests and ISO-TP flow-control transmissions remain in TCB1 with `direction=1`.

## 6. Board Scope

The supported CYD profiles for the simplified firmware are:

- `E32R35T_TOUCH`
- `DORHEA_B0DLNJSSFW_TOUCH`

`E32N35T` is not an active target for this revision. Existing source comments/profile naming that describe E32N35T as the fallback must be replaced before release.

Do not guess an E32R35T touch calibration. Use a documented/known-working board configuration and bench-verify touch before promotion.

## 7. SD Product Removal

Because the offline TVM1 compatibility gate is now PASS, the new firmware may remove normal on-device generation of:

- `DECODED.CSV`
- `DIAGNOSTICS.CSV`
- `EXTERNAL_DIAGNOSTICS.CSV`
- `EVENTS.CSV`
- `SYNC.CSV`
- `SIGNALS.CSV`
- `README.TXT`
- `MANIFEST.JSON`
- `CHECKPOINT.JSON`
- `PLOT.CSV`

The normal capture path keeps only current TCB1 RAW plus `SESSION.META` open.

Live in-RAM decoding remains allowed where required for display and the read-only diagnostic scheduler.

## 8. Session Finalization and Wi-Fi Compatibility

The current Wi-Fi UI uses `SESSION.OPEN` to infer whether a session is closed. Simplified native sessions must instead determine clean/unclean state by reading TVM1 metadata. Wi-Fi file mode must support both:

- legacy session: `SESSION.OPEN` means unclean/open;
- native TVM1 session: valid clean `SESSION_CLOSE` means closed; absent/invalid close means unclean.

Deletion remains prohibited for an unclean session.

## 9. Gate Provenance

Firmware implementation is authorized by these four completed offline gates:

1. S0141 RAW identity + Builder 1.0.4 compatibility PASS.
2. S0149 RAW identity + Builder 1.0.4 compatibility PASS.
3. S0128 RAW identity + Builder 1.0.4 compatibility PASS.
4. Windows 10 build 14393 packaged runtime PASS using Python 3.12.7 with 1,021,568 S0141 RAW records preserved, zero truncation, zero failures, and final `ERRORLEVEL=0`.

Analyzer RC7/RC8 smoke is not a firmware-authorization input for this boundary.
