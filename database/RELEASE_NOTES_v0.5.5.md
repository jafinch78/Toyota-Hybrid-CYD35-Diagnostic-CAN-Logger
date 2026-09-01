# Toyota Hybrid CAN Database v0.5.5

Release date: 2026-09-01
Schema: 1.0.0
Rollback: `Toyota_Hybrid_CAN_Database_v0.5.4.xlsx`

## Scope

This is a profile-isolated Prius PHV Gen 1 evidence promotion/refinement
release based on the S0018 Autel MAXIAP200 capture. It preserves all v0.5.4
profiles and definitions and adds six read-only ZVW35 definitions. Evidence
Builder v1.0.3 is the first processor release that operationally exports every
decoder type used here.

## Vehicle identity and profile correction

- Added confirmed `7E0/21C1` ASCII model signature `ZVW35 2ZRFXE`.
- Added confirmed standard `7E0/09 02` VIN decoding with mask-by-default
  metadata. Release evidence stores only `JTDKN3DP4E3******`.
- Added confirmed `7E2/21C2` hybrid ECU code `47520`.
- Made the confirmed ZVW35 model signature authoritative for offline profile
  selection. It overrides the S0018 logger's incorrect Camry 95% heuristic.
- Retained the eight-block PHV response signature as strong corroborating
  evidence, not as a substitute for model identity.

## PHV definitions refined or promoted

- `2101`: confirmed all-battery SoC and coolant; uncorroborated subfields keep
  narrower `PROBABLE`/`CANDIDATE` field grades.
- `2161`/`2162`: corrected formulas to degrees Celsius and recorded the
  observed AP200 label crosswalk. AP200 `Motor temp no2` matched the MG1 PID,
  while `Motor temp no1` matched the MG2 PID.
- `2170`/`2171`: confirmed MG1/MG2 inverter temperature fields.
- `2175`: added confirmed inverter coolant temperature and pump-speed fields.
- `2181`: confirmed all eight approximately 25 V seven-cell aggregate block
  voltages plus the observed pack/auxiliary/fan fields.
- `2187`: confirmed intake-temperature channels 1-4 and battery temperature
  sensors TB1-TB12 from repeated labeled AP200 correlation.
- `218A`: added two confirmed signed power-resource current sensors.
- `2192`: added confirmed minimum/maximum block voltages, one-based block
  indexes, block count, and derived voltage difference.
- `2195`: confirmed eight aggregate-block internal resistances.
- `2198`: confirmed battery current, charge/discharge limits, delta SoC,
  ignition SoC, and maximum/minimum SoC.

## S0018 evidence

- Logger v2.4.2, capture format 1.4, TWAI `LISTEN_ONLY`, zero session transmit
  frames, zero queue/log drops, and zero bus-off events.
- 1,195,423 raw records; 1,870 reconstructed AP200 transactions; 1,554 OK.
- 215 BLE sync samples with 5.498 ms RMS alignment residual.
- Nineteen successful model-signature responses and two VIN responses.
- Generic v1.0.3 regression exported 4,388 decoded rows, 79 eight-block rows,
  and 12 eight-resistance rows with zero bounds/expected-value failures.
- Full-resolution OCR regrading produced 837 CAN/OCR pairs and 798
  within-tolerance agreements. These local grades support review but do not
  automatically assign database evidence grades.

## PHV limitation retained

`2181` exposes eight aggregate block voltages. Each block represents seven
lithium-ion cells (8 x 7 = 56 cells). Database v0.5.5 does **not** claim 56
individually decoded cell voltages. No individual-cell definition will be
added without a response exposing all 56 values and independent validation.

## Safety

- Every new v0.5.5 entry is `READ_ONLY_DIAGNOSTIC`.
- No transmit, control, actuator, reset, or clear-code definition was added.
- The two inherited Mode `04` clear-DTC observations remain
  `CONTROL_WRITE_QUARANTINED` and must never be automatically transmitted.
- Vehicle profiles remain isolated; ZVW35 formulas are not applied to AHV40,
  NHW20, or ZVW30 solely because a PID number is similar.

## Compatibility

- JSON schema remains `1.0.0` with 44 definitions, five profiles, and seven
  detector signatures.
- Evidence Builder v1.0.3 supports the `field_map`, `block_array`,
  `block_health_array`, `resistance_array`, identity, VIN, and response
  signature records used by this release.
- Evidence Builder v1.0.2 can load older databases but does not operationally
  export the full v0.5.5 decoder set; use v1.0.3 for this release.
