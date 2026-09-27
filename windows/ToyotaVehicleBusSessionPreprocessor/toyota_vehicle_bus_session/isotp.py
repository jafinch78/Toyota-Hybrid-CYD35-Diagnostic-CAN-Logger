from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IsoTpResult:
    status: str
    payload: bytes
    frame_count: int
    complete_time_us: int
    response_id: int


class IsoTpAssembler:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.active = False
        self.expected_length = 0
        self.payload = bytearray()
        self.next_sequence = 1
        self.frame_count = 0
        self.response_id: int | None = None

    def feed(self, time_us: int, can_id: int, data: bytes, dlc: int) -> IsoTpResult | None:
        if dlc <= 0:
            return None
        frame = bytes(data[:dlc])
        if not frame:
            return None
        pci = frame[0] >> 4

        if pci == 0x0:
            length = frame[0] & 0x0F
            if length > max(0, dlc - 1):
                return IsoTpResult("INCOMPLETE_SEQUENCE", frame[1:dlc], 1, time_us, can_id)
            payload = frame[1 : 1 + length]
            status = "NEGATIVE_RESPONSE" if payload[:1] == b"\x7f" else "OK"
            self.reset()
            return IsoTpResult(status, payload, 1, time_us, can_id)

        if pci == 0x1:
            if dlc < 2:
                return IsoTpResult("INCOMPLETE_SEQUENCE", b"", 1, time_us, can_id)
            self.active = True
            self.expected_length = ((frame[0] & 0x0F) << 8) | frame[1]
            self.payload = bytearray(frame[2:dlc])
            self.next_sequence = 1
            self.frame_count = 1
            self.response_id = can_id
            if len(self.payload) >= self.expected_length:
                payload = bytes(self.payload[: self.expected_length])
                status = "NEGATIVE_RESPONSE" if payload[:1] == b"\x7f" else "OK"
                result = IsoTpResult(status, payload, self.frame_count, time_us, can_id)
                self.reset()
                return result
            return None

        if pci == 0x2:
            if not self.active or self.response_id != can_id:
                return IsoTpResult("INCOMPLETE_SEQUENCE", b"", 1, time_us, can_id)
            sequence = frame[0] & 0x0F
            if sequence != self.next_sequence:
                payload = bytes(self.payload)
                frame_count = self.frame_count + 1
                response_id = self.response_id
                self.reset()
                return IsoTpResult("INCOMPLETE_SEQUENCE", payload, frame_count, time_us, response_id)
            self.payload.extend(frame[1:dlc])
            self.frame_count += 1
            self.next_sequence = (self.next_sequence + 1) & 0x0F
            if len(self.payload) >= self.expected_length:
                payload = bytes(self.payload[: self.expected_length])
                status = "NEGATIVE_RESPONSE" if payload[:1] == b"\x7f" else "OK"
                response_id = self.response_id
                frame_count = self.frame_count
                self.reset()
                return IsoTpResult(status, payload, frame_count, time_us, response_id)
            return None

        # Flow-control and other PCI types do not contribute response payload bytes.
        return None
