# v2.4.3-rc.1 — simpler session start, isolated board builds

v2.4.3-rc.1 is intentionally based on the proven v2.4.2 logging and session-allocation method. It does not carry forward the v2.5.0 monotonic NVS/SD counter transaction.

Choose exactly one firmware folder:

- `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_3_N35T` — established GPIO25 TX / GPIO32 RX and touch flag 7.
- `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_3_Dorhea_B0DLNJSSFW` — tested touch flag 3 and GPIO4 LED-off behavior; candidate GPIO22 TX / GPIO35 RX still requires vehicle validation.

## Session behavior

At log start, the firmware scans `S0001` through `S9999` and creates the first missing directory. It does not write Preferences/NVS or a `NEXT_SESSION` file.

Wi-Fi clear is deliberately different from directory deletion:

1. It requires a closed session, the per-boot authorization token, and typed `CLEAR-S####` confirmation.
2. It removes the files within that session.
3. It retains the `S####` directory.
4. It writes `SESSION_TOMBSTONE.JSON` to record the clear.

The retained directory is therefore the persistent counter and prevents reuse of that session identifier.

## Release status

This is an RC source release. Static safety checks pass, but Arduino compile size/RAM figures and physical bench/vehicle results are pending. Keep v2.4.2 available as the rollback build until the validation matrix passes.

