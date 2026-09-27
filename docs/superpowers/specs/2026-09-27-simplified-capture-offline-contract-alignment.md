# Simplified Capture Offline Contract Alignment

Date: 2026-09-27

This document is a normative extension to `2026-09-27-simplified-capture-logger-design.md`. It incorporates the previously agreed requirements from the Branch - Scrape CYD Links offline-processing design. Where this document is more specific, it takes precedence.

## 1. Compatibility Gate Before Firmware File Removal

The simplified firmware MUST NOT become the preferred vehicle-capture firmware, and MUST NOT remove the legacy on-device derived files from a release intended for normal capture, until the offline compatibility preprocessor has been implemented and validated against representative simplified fixtures plus legacy sessions.

The preprocessor must accept the new native input and regenerate the legacy Builder/Analyzer-facing package so the existing Windows processing path can continue to operate without treating intentionally absent derived files as corruption.

The required regenerated compatibility outputs are:

- `MANIFEST.JSON`
- `CHECKPOINT.JSON`
- `SYNC.CSV`
- `EVENTS.CSV`
- `DIAGNOSTICS.CSV`
- `EXTERNAL_DIAGNOSTICS.CSV`
- `DECODED.CSV`
- `SIGNALS.CSV`
- `README.TXT`

`PLOT.CSV`, graphs, reports, and other visualization artifacts remain offline-derived outputs and are not native CYD requirements.

Validation must prove that the regenerated package can be passed through the current Evidence Builder / Analyzer validation and loading paths while preserving provenance, warnings, drop counters, synchronization evidence, diagnostic chronology, and clean/unclean-finalization state.

Legacy packages remain supported directly. The compatibility preprocessor must not rewrite or weaken legacy provenance merely because a legacy session is also parseable from TCB.

## 2. Native Input Contract

For CAN-only simplified firmware, the native session input remains:

```text
/CANLOG/S####/
    RAW_000.TCB
    RAW_001.TCB        # if rotated
    SESSION.META
    SESSION.OPEN       # only while open / after unclean stop
```

TCB1 remains unchanged and authoritative for CAN frame chronology. The compact metadata stream holds information not reconstructible from bus traffic alone.

The offline processor must treat absence of the legacy CSV/JSON files as intentional when a valid simplified `SESSION.META` contract is present.

## 3. SESSION.META Is Bus-Neutral

`SESSION.META` is not a CAN-specific sidecar. It is the session-level envelope for zero or more acquisition streams.

The metadata model must be capable of describing streams such as:

- `CAN`
- `BTH`
- `AVC_LAN`
- future bus or sensor streams

A session may contain one stream, multiple concurrent streams, independently active streams, or no bus stream at all if the session is being used for another synchronized acquisition purpose.

Each stream declaration must identify at minimum:

- stable stream ID within the session;
- stream type / protocol family;
- one or more native file names or file patterns;
- native record format and version;
- timestamp domain / clock source;
- nominal bitrate or link-rate field when applicable;
- RX/TX/direction semantics when applicable;
- stream start and stop boundaries;
- record/frame counters;
- drop/loss/error counters;
- file rotation information;
- stream-specific health counters;
- whether the stream is authoritative raw evidence or derived data.

Session-level records remain responsible for firmware ID, board profile, synchronized capture lifecycle, BLE/phone synchronization anchors, markers, global heap/stack/resource health, clean-close state, and other device-wide information.

## 4. Metadata Record Scope

The record framing and CRC/truncated-tail recovery requirements from the simplified logger design remain unchanged, but records must carry enough scope to distinguish session-level events from stream-level events.

The implementation may accomplish this by adding a `stream_id` to applicable payloads or by defining stream-scoped record types. It must not create separate incompatible metadata formats for CAN, BTH, and AVC_LAN.

At minimum the format needs records equivalent to:

- session start / close;
- stream declaration;
- stream start / stop;
- stream file rotation;
- stream health snapshot;
- device health snapshot;
- BLE synchronization sample;
- synchronized start/stop request;
- marker/event;
- diagnostic state and external-tester event for CAN streams;
- storage error/event;
- unclean-recovery information.

## 5. CAN-Specific Reconstruction

For a CAN stream using TCB1:

- request, response, and flow-control direction-marked frames remain reconstructible from raw TCB;
- logger diagnostics are reconstructed offline from RAW plus metadata-only internal outcomes such as timeout, reject, user disable, or bus-off;
- external diagnostics are reconstructed from RAW;
- decoded values are regenerated from RAW using the selected canonical decoder/database version;
- `SYNC.CSV` is regenerated from metadata BLE synchronization records and combined with Android `CAPTURE_SYNC.json` using the existing session-independent fit process.

The offline processor must preserve the exact native source references and distinguish observed raw evidence from regenerated/derived artifacts.

## 6. Future BTH / AVC_LAN Reuse

The first firmware implementation may populate only a CAN stream, but the parser, schema, and compatibility preprocessor must not assume `stream_id == CAN` or exactly one stream.

Future BTH or AVC_LAN firmware may reuse the same `SESSION.META` envelope and add native raw files without redesigning the session contract.

A multi-stream session must allow the offline processor to normalize each stream independently and then correlate them through the common session timestamp/synchronization model.

## 7. Required Implementation Order

The implementation order is mandatory:

1. Define and test the bus-neutral `SESSION.META` codec/schema.
2. Implement the offline compatibility preprocessor for simplified `RAW + META` input.
3. Regenerate the legacy Builder/Analyzer-facing artifact set.
4. Validate regenerated packages through the current Builder/Analyzer path using representative fixtures and at least one legacy comparison session.
5. Only after the compatibility gate passes, change the firmware capture path to stop producing redundant live derived files.
6. Implement RAW-first ordering, pending synchronized stop/finalization, external-tester interlock, health instrumentation, and 80 MHz dirty-field display updates.
7. Bench-validate E32R35T and Dorhea before promoting the simplified firmware over RC2.

## 8. Acceptance Criteria

The combined simplified-capture design is accepted only when:

- TCB1 remains unchanged for CAN;
- `SESSION.META` is demonstrably bus-neutral and supports zero or more declared streams;
- an offline simplified package can be expanded into the legacy compatibility artifact set;
- Evidence Builder / Analyzer accepts that regenerated package through its normal validation/load path;
- legacy sessions remain accepted;
- intentional absence of legacy on-device files is not reported as corruption for simplified packages;
- provenance clearly distinguishes native raw/metadata from regenerated outputs;
- firmware file removal occurs only after the offline compatibility gate passes;
- E32R35T and Dorhea bench validation passes with the simplified logger.
