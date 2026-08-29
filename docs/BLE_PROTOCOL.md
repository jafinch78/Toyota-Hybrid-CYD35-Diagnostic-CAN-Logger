# ToyotaCYD-Sync/1 BLE protocol

All multibyte integers are unsigned little-endian. Every packet is 20 bytes or
less so it works with the default ATT payload without relying on MTU expansion.

| Item | UUID |
| --- | --- |
| Service | `6ed9f000-4f21-4c8c-a8a7-923c86b40001` |
| Command write/write-without-response | `6ed9f000-4f21-4c8c-a8a7-923c86b40002` |
| Response notify/read | `6ed9f000-4f21-4c8c-a8a7-923c86b40003` |

## Clock exchange

- Request, 4 bytes: `type=01`, `version=01`, `sequence:uint16`.
- Reply, 20 bytes: `type=81`, `version=01`, `sequence:uint16`,
  `ESP_receive_us:uint64`, `ESP_send_us:uint64`.

The client records T1 immediately before the write and T4 in the notification
callback. The ESP32 records E2 on callback entry and E3 immediately before the
notification. Each sample midpoint maps the independent monotonic clocks.

The Windows processor rejects invalid exchanges, filters high-latency samples,
and fits:

`client_ns = slope_ns_per_us * esp_us + intercept_ns`

It then combines that mapping with the current recording's video anchor. Both
offset and drift are session-specific.

## Session control

- Request, 8 bytes: `type=02`, `version=01`, `sequence:uint16`, `opcode:uint8`,
  `flags:uint8`, `marker:uint16`.
- Opcodes: 1 start passive logging; 2 clean stop; 3 marker.
- Reply, 20 bytes: `type=82`, `version=01`, `sequence:uint16`, `status:uint8`,
  `logging:uint8`, `session:uint32`, `event_us:uint64`, `diagnostic:uint8`,
  `twai_normal:uint8`.

Status 0 is success; 1 invalid command; 2 SD unavailable; 3 invalid state. Start
always disables diagnostic polling and restores listen-only mode. There is no
packet type for arbitrary CAN transmission, diagnostic enable, fan control,
write service, erase, or format.
