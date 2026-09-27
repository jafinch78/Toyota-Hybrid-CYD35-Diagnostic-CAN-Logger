# TVM1 `SESSION.META` Binary Specification

Status: **Proposed v1.0 implementation contract**  
Date: 2026-09-27  
Parent contract: `docs/TOYOTA_VEHICLE_BUS_CAPTURE_CONTRACT.md`

## 1. Purpose

`SESSION.META` is the compact, append-only, bus-neutral metadata stream for Toyota vehicle-bus captures. Raw stream files remain authoritative for bus traffic; TVM1 preserves session facts that cannot be reconstructed reliably from raw traffic alone.

The format is designed for low allocation, bounded writes, power-loss recovery, forward compatibility, and straightforward decoding in both ESP32 C++ and offline Python.

## 2. Byte order and CRC

All multi-byte integers are little-endian.

CRC fields use **CRC-32/ISO-HDLC**, equivalent to Python `zlib.crc32()` over the specified byte range and masked to 32 bits. The reflected polynomial is `0xEDB88320`.

## 3. File header

The file begins with exactly 32 bytes:

| Offset | Size | Type | Field | v1 value/meaning |
|---:|---:|---|---|---|
| 0 | 4 | bytes | magic | ASCII `TVM1` |
| 4 | 1 | u8 | major | `1` |
| 5 | 1 | u8 | minor | `0` |
| 6 | 2 | u16 | header_size | `32` |
| 8 | 4 | u32 | session_number | numeric portion of `S####` |
| 12 | 4 | u32 | header_flags | `0` in v1 |
| 16 | 8 | u64 | session_create_us | common monotonic logger clock |
| 24 | 4 | u32 | header_crc32 | CRC of bytes 0-23 |
| 28 | 4 | u32 | reserved | `0` in v1 |

A reader must reject a file with bad magic, unsupported major version, header size below 32, or invalid header CRC. A reader may accept a newer minor version when all records it needs are independently parseable.

## 4. Record envelope

Every record after the file header has:

| Offset from record start | Size | Type | Field |
|---:|---:|---|---|
| 0 | 2 | u16 | sync word `0xA55A` |
| 2 | 2 | u16 | total record length |
| 4 | 2 | u16 | record type |
| 6 | 1 | u8 | stream_id (`0` = session-level) |
| 7 | 1 | u8 | flags |
| 8 | 4 | u32 | sequence |
| 12 | 8 | u64 | time_us |
| 20 | N | bytes | payload |
| 20+N | 4 | u32 | record CRC-32 |

`total record length = 24 + payload length`.

Rules:

- minimum record length: 24 bytes;
- maximum v1 record length accepted without an explicit extension: 4096 bytes;
- sequence starts at 1 and increases monotonically for every metadata record in the file;
- `time_us` uses the same monotonic clock as all native acquisition streams;
- CRC covers bytes from the sync word through the last payload byte, excluding the trailing CRC field;
- a truncated final record is ignored and reported as recovery;
- a CRC-invalid record is reported as corruption; a reader may scan forward for the next valid `0xA55A` record boundary;
- unknown record types with valid length and CRC are skipped, not treated as fatal.

## 5. String encoding

Low-frequency provenance records may contain UTF-8 strings. Strings are not null-terminated.

A string is encoded as:

```text
u16 byte_length
byte[byte_length] UTF-8
```

Maximum v1 length for any single string is 255 bytes even though the stored length field is u16.

## 6. Stream and format identifiers

### 6.1 Stream type

| ID | Stream type |
|---:|---|
| 0 | SESSION |
| 1 | CAN |
| 2 | BTH |
| 3 | AVC_LAN |
| 4-254 | reserved |
| 255 | vendor/experimental |

### 6.2 Raw format identifier

| ID | Raw format |
|---:|---|
| 0 | UNKNOWN / not yet frozen |
| 1 | TCB1 |
| 2-254 | reserved for future standardized formats |
| 255 | vendor/experimental |

BTH and AVC-LAN initially register with raw format `0` until their validated native raw formats are frozen. Reserving their stream types now does not manufacture an unvalidated binary bus format.

### 6.3 Direction capability bits

`direction_caps` bit field:

- bit 0: RX observable;
- bit 1: TX observable;
- bits 2-7: reserved, zero in v1.

## 7. Record types and payloads

### `0x0001 SESSION_START` — stream 0

Written once immediately after the TVM1 header.

Payload:

```text
string logger_name
string firmware_version
string board_profile
string build_id
string runtime_database
```

Examples of `board_profile` are `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`. `build_id` may be a Git commit, release tag, or other immutable build identifier. `runtime_database` may be empty when no live decoder database is loaded.

### `0x0002 STREAM_REGISTER` — target stream

Written once for each stream ID before `STREAM_START`.

Fixed payload prefix:

```text
u8  stream_type
u8  raw_format_id
u8  raw_format_major
u8  raw_format_minor
u8  direction_caps
u8  config_version
u16 config_length
u32 nominal_rate
byte[config_length] config
```

`nominal_rate` is bits/s or symbols/s when a meaningful nominal rate exists; zero means unknown/not applicable. `config` is interpreted only by the stream/raw-format pair. A v1 TCB1 CAN stream uses `config_version=0`, `config_length=0`, and normally `nominal_rate=500000`.

### `0x0003 STREAM_START` — target stream

No payload. Record `time_us` is the stream start time.

### `0x0004 STREAM_STOP` — target stream

Payload:

```text
u16 reason_code
```

Initial reason codes:

- `0`: normal/user stop;
- `1`: session close;
- `2`: storage failure;
- `3`: bus/controller failure;
- `4`: mode change;
- `5`: watchdog/recovery;
- `65535`: other/unknown.

### `0x0005 STREAM_FILE_OPEN` — target stream

Payload:

```text
u16 file_index
string filename
```

The filename is the basename only, never an absolute path.

### `0x0006 STREAM_FILE_CLOSE` — target stream

Payload:

```text
u16 file_index
u16 reason_code
u64 records_persisted
u64 bytes_persisted
```

The close record is advisory integrity metadata. Offline readers still verify actual file size and parseable record count.

### `0x0010 CLOCK_SYNC` — stream 0

The record envelope `time_us` is the ESP receive timestamp corresponding to current legacy `ESP_Receive_us` / E2.

Payload:

```text
u16 sequence
u8  source
u8  reserved = 0
u64 esp_send_us
```

Initial source values:

- `0`: BLE;
- `1`: BLE_PRESTART;
- `2-254`: reserved;
- `255`: experimental/unknown.

This is sufficient to regenerate legacy `SYNC.CSV` columns `Sequence,ESP_Receive_us,ESP_Send_us,Source`.

### `0x0011 USER_MARKER` — stream 0

Payload:

```text
u16 sequence
u16 source
u32 marker
```

Initial source `0` = BLE companion marker. Other values are reserved.

### `0x0020 HEALTH_SNAPSHOT` — stream 0

Extensible metric vector:

```text
u16 schema_version = 1
u16 metric_count
repeat metric_count:
    u16 metric_id
    u16 metric_flags
    u64 value
```

`metric_flags` bit 0 means the value is a high-water/worst-case value; all other bits are reserved in v1.

Initial metric IDs:

| ID | Metric |
|---:|---|
| 1 | free_heap_bytes |
| 2 | largest_free_block_bytes |
| 3 | minimum_free_heap_bytes |
| 4 | main_loop_max_us |
| 5 | main_task_stack_high_water_bytes |
| 6 | can_rx_task_stack_high_water_bytes |
| 7 | tft_render_max_us |
| 8 | raw_write_average_us |
| 9 | raw_write_max_us |
| 10 | flush_max_us |
| 11 | flush_count |

Unknown metric IDs are preserved/skipped without failing the record.

### `0x0021 STREAM_COUNTERS` — target stream

Payload:

```text
u64 rx_records
u64 tx_records
u64 persisted_records
u64 queue_drops
u64 storage_dropped_records
u32 queue_high_water
u32 protocol_errors
```

All counters are session-scoped for that stream. `persisted_records` is the count successfully committed to raw stream files. The offline expander must not replace `rx_records` with `persisted_records` or hide loss indicators.

### `0x0022 STORAGE_HEALTH` — stream 0

Same metric-vector encoding as `HEALTH_SNAPSHOT`, with these initial metric IDs:

| ID | Metric |
|---:|---|
| 1 | card_total_bytes |
| 2 | card_free_bytes |
| 3 | write_error_count |
| 4 | short_write_count |
| 5 | flush_error_count |
| 6 | open_file_failure_count |

### `0x0030 EVENT` — stream 0 or target stream

Compact enumerated event:

```text
u16 event_code
u8  severity
u8  arg_count
repeat arg_count:
    u16 arg_id
    u16 arg_flags
    i64 value
```

Severity:

- `0` INFO;
- `1` WARNING;
- `2` ERROR;
- `3` FATAL.

Initial event codes:

| Code | Event |
|---:|---|
| 1 | LOGGING_STARTED |
| 2 | LOGGING_STOP_REQUESTED |
| 3 | LOGGING_STOPPED |
| 4 | CAN_TRAFFIC_STARTED |
| 5 | RAW_ROTATION_FAILED |
| 6 | EXTERNAL_TESTER_DETECTED |
| 7 | TWAI_START_FAILED |
| 8 | TWAI_TRANSMIT_BLOCKED |
| 9 | TWAI_TRANSMIT_FAILED |
| 10 | TWAI_MODE_CHANGE_FAILED |
| 11 | BLE_CAPTURE_START |
| 12 | BLE_CAPTURE_STOP |
| 13 | BLE_MARKER |
| 14 | DIAGNOSTIC_ENABLE_REJECTED |
| 15 | DIAGNOSTIC_IDENTITY_UNRESOLVED |
| 16 | DIAGNOSTIC_RUNTIME_DECODE_MISSING |
| 17 | DATABASE_PROFILE_EVIDENCE |
| 18 | PROFILE_CHANGE |
| 19 | DIAGNOSTIC_IDENTITY_FALLBACK |
| 20-65534 | reserved |
| 65535 | OTHER |

Initial argument IDs:

| ID | Meaning |
|---:|---|
| 1 | sequence |
| 2 | marker |
| 3 | CAN identifier |
| 4 | error/status code |
| 5 | profile enum/value |
| 6 | confidence percent |
| 7 | file index |
| 8 | source enum |

New event or argument IDs may be added without changing TVM1 major version.

### `0x0031 DIAGNOSTIC_STATE` — CAN stream

Payload:

```text
u16 state_code
u16 reason_code
u32 value0
u32 value1
```

Initial state codes:

- `0`: disabled/passive;
- `1`: enabled/read-only scheduler;
- `2`: active transaction;
- `3`: timeout;
- `4`: negative response;
- `5`: incomplete/reassembly error;
- `6`: external-tester interlock;
- `7`: user-disabled;
- `8`: bus-off disabled.

`value0` and `value1` are state-specific numeric details; a decoder must tolerate them being zero. Bus frames themselves remain the authority for transmitted requests, flow-control frames, and received responses.

### `0x0032 BUS_STATE` — target stream

Payload:

```text
u16 state_code
u16 reason_code
u32 value0
u32 value1
```

Initial CAN state codes:

- `0`: offline;
- `1`: listen-only/online;
- `2`: normal diagnostic mode;
- `3`: bus-off;
- `4`: recovering;
- `5`: recovered/listen-only.

### `0x00FE SESSION_CLOSE` — stream 0

Written once only for an orderly close.

Payload:

```text
u16 reason_code
u8  clean
u8  reserved = 0
u16 registered_stream_count
u16 reserved2 = 0
```

`clean` must be `1` for a normal close. If this record is absent or invalid, the session is unclean regardless of other metadata.

## 8. Recommended write cadence

The contract does not require a fixed cadence, but the first optimized firmware should use these defaults:

- `STREAM_COUNTERS`: every 5 seconds and immediately before clean close;
- `HEALTH_SNAPSHOT`: every 5 seconds while logging;
- `STORAGE_HEALTH`: every 5 seconds or when storage state changes;
- event/state records: immediately on state transition;
- `CLOCK_SYNC`: once per accepted BLE sync exchange;
- file open/close records: exactly at physical stream-file transitions.

Metadata writes should be buffered and appended after raw stream persistence has been serviced. They must never preempt mission-critical raw acquisition.

## 9. Recovery semantics

A valid reader returns all records up to the last recoverable record and separately reports:

- clean vs unclean close;
- truncated final bytes;
- CRC-invalid records;
- recovered/resynchronized record count;
- sequence gaps;
- unknown record types;
- stream/file inconsistencies.

Recovery never fabricates missing counters or bus traffic.

## 10. Legacy expansion mapping

The first offline expander maps TVM1 to current legacy artifacts as follows:

| Legacy product | Native source |
|---|---|
| `MANIFEST.JSON` | header + SESSION_START + stream registration + raw scan + last counters/health + close state |
| `CHECKPOINT.JSON` | last valid counters/health + raw scan + close state |
| `SYNC.CSV` | CLOCK_SYNC |
| `EVENTS.CSV` | EVENT + state transitions |
| `DIAGNOSTICS.CSV` | CAN raw TX/RX + DIAGNOSTIC_STATE |
| `EXTERNAL_DIAGNOSTICS.CSV` | CAN raw RX/TX direction + external-tester reconstruction window/state |
| `DECODED.CSV` | CAN raw + selected offline decoder database |
| `SIGNALS.CSV` | selected offline decoder database |
| `PLOT.CSV` | raw streams + metadata + diagnostic reconstruction + selected offline decoder database |
| `README.TXT` | deterministic template + tool/database/native-contract versions |
| `SESSION.OPEN` | emitted only when no valid clean SESSION_CLOSE exists |

For Builder 1.0.4 compatibility, the expanded `MANIFEST.JSON` must use:

- `format = "ToyotaHybridCAN-Capture"`;
- `format_version = "1.4"`;
- `raw_format = "TCB1_24_byte_records"` for a CAN TCB1 session.

The manifest also records the native `TVM1` contract/tool provenance so the legacy package never hides that it was reconstructed offline.

## 11. External diagnostic reconstruction rule

The offline expander reproduces the current logger's external-diagnostic evidence policy from authoritative raw traffic:

- standard, non-RTR, non-extended RX frames on `0x7DF` or `0x7E0-0x7E7` with ISO-TP PCI type 0 or 1 begin/update an external-tester observation;
- responses on `0x7E8-0x7EF` within **5000 ms** after the most recent external request are classified as external responses unless they belong to a logger-originated TX diagnostic transaction;
- logger-originated diagnostic requests/flow-control frames are identified by raw `direction=TX` and are not mislabeled as external tester requests;
- all ISO-TP transaction assembly and semantic decoding is performed offline.

This preserves the established 5000 ms external-tester hold behavior while moving CSV generation off the ESP32.

## 12. Forward compatibility

A TVM1 writer must never reuse a standardized ID for a different meaning. Additions use new record/event/metric IDs or a new minor version. Incompatible envelope or semantic changes require a new major magic/version.

BTH and AVC-LAN can add independently versioned raw stream formats and stream-specific `config` payloads without changing this TVM1 envelope.
