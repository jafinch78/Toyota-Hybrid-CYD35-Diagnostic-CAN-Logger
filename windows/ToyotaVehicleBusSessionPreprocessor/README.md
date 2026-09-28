# Toyota Vehicle Bus Session Preprocessor

Standalone offline preprocessor for the native Toyota vehicle-bus capture contract. The core package uses only the Python standard library and is designed to expand immutable `RAW stream(s) + SESSION.META` input into a legacy Evidence Builder-compatible CANLOG package.

The native evidence is never modified. TCB1 remains authoritative for CAN traffic, while TVM1 carries bus-neutral session and stream metadata.

## Firmware authorization boundary

The compatibility gate is deliberately limited to the boundaries that can invalidate the simplified logger contract: authoritative RAW identity/integrity, three-session Evidence Builder 1.0.4 oracle equivalence, and a Windows 10 1607 preprocessor/launcher validation run. Analyzer RC7/RC8 processing is downstream of the Builder-compatible package and is not a firmware-authorization requirement.
