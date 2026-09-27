# Toyota Vehicle Bus Session Preprocessor

Standalone offline preprocessor for the native Toyota vehicle-bus capture contract. The core package uses only the Python standard library and is designed to expand immutable `RAW stream(s) + SESSION.META` input into a legacy Evidence Builder-compatible CANLOG package.

The native evidence is never modified. TCB1 remains authoritative for CAN traffic, while TVM1 carries bus-neutral session and stream metadata.
