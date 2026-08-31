# Toyota Hybrid CAN Database v0.5.4

Release date: 2026-08-31  
Schema: 1.0.0  
Rollback: `Toyota_Hybrid_CAN_Database_v0.5.3.xlsx`

## Scope

This is a database-only release. It does not change CYD firmware, vehicle-profile detection logic, Evidence Builder code, Android code, or diagnostic transmit policy.

## Changes

- Added two `CONFIRMED` Prius Gen 2 (NHW20) Battery ECU definitions from S0016 Autel MAXIAP200 correlation:
  - `7E3/21CE`: battery SoC, battery current, and 14 block voltages.
  - `7E3/21D0`: 14 block internal-resistance values and block-health metadata.
- Refined the Camry Hybrid (AHV40) profile using S0013 and independent S0017 Autel MAXIAP200 correlation:
  - Promoted `7E2/21CE` to `CONFIRMED`: SoC, battery current, and all 17 block voltages.
  - Promoted `7E2/21D0` to `CONFIRMED`: block count, minimum/maximum block voltage and one-based block numbers, plus 17 internal-resistance values.
  - Added both `7E0/21C1` and `7E2/21C1` ASCII `AHV40L 2AZFXE` model signatures as `CONFIRMED`.
  - Confirmed the four labeled MG motor/inverter temperature fields in `21C3` and five labeled battery/intake temperature fields in `21CF`; unlisted bytes remain candidates.
  - Confirmed AP200-labeled `2105` coolant, `210F` intake-air, `210C` engine-speed, and `211F` engine-runtime fields.
  - Retained `21C4` as a signature-only `CANDIDATE`; no field meaning is inferred.
- Added Prius PHV Gen 1 (ZVW35) definitions from S0015 with conservative grades:
  - `PROBABLE`: `2101`, `2161`, `2170`, `2181`, `2187`, and `2198`.
  - `CANDIDATE`: `2146`, `2162`, `2167`, `2168`, `2171`, `2174`, `2195`, and `219B`.
  - Added observed multi-PID bundle metadata and PHV profile fingerprints.
- Added capture-evidence and profile-signature sections for future detector and Evidence Builder work.

## Important PHV limitation

The ZVW35 `2181` response contains eight approximately 25 V values. Each value represents an aggregate of seven lithium-ion cells:

- 8 blocks
- 7 cells per block
- 56 cells total

Database v0.5.4 does **not** claim that the 56 individual cell voltages have been decoded. No individual-cell definition will be added until a source or capture exposes and independently validates those values.

## Safety

- All new entries are `READ_ONLY_DIAGNOSTIC`.
- No new control or write command was added.
- The two inherited Mode `04` clear-DTC definitions remain `CONTROL_WRITE_QUARANTINED` and must never be automatically transmitted.
- Passive observations are preserved separately from decoded conclusions.

## Compatibility

- The JSON remains schema `1.0.0` and passes the Evidence Builder v1.0.2 database loader.
- Evidence Builder v1.0.2 only operationally implements the existing `block_array` decoder path. The new `field_map`, `block_health_array`, `resistance_array`, signature, and bundled-request metadata are authoritative database records but require a later Evidence Builder decoder update for full automatic export.
- This release does not correct the CYD logger's S0015 Camry false-positive by itself. Its fingerprints provide the evidence for a later firmware detector update.

## S0017 validation details

- S0017 logged 880,701 raw records with zero CYD transmit frames, zero SD-log drops, no truncated tail, and no bus-off events.
- BLE alignment used 138 samples with zero sequence mismatches and 5.87 ms RMS residual.
- `21CE`: 34 successful transactions; 77 of 79 AP200 OCR block values matched exactly; median best-nearby RMSE was 0.000 V.
- `21D0`: 59 successful transactions; displayed block count, voltage extrema, one-based block numbers, and seventeen 0.019 ohm values matched.
- AP200 does not expose Hybrid Assistant/Dr. Prius graph-axis rows; `battery_graph_rows=0` is therefore expected, not a capture failure. Its labeled list values remain valid evidence.
- The resized 720×1568, 10 fps evidence MP4 preserved duration and remained readable for AP200 label/value correlation.

## Promotion requirements

- Camry unmapped `21C3`/`21CF` bytes and `21C4`: require additional labeled AP200/Techstream state variation before assigning meanings.
- PHV candidates: collect labeled AP200/Techstream data and, where applicable, a dynamic driving or HVAC state range.
- PHV 56-cell voltages: require a diagnostic response that exposes all 56 values and independent validation against a capable scan tool.
