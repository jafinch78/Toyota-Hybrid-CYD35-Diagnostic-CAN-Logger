from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .diagnostics import reconstruct_logger_diagnostics
from .external_transactions import reconstruct_external_transactions
from .meta import decode_record_payload
from .schemas import PROFILE_LABELS
from .tcb1 import TcbFrame, iter_tcb_frames

LEGACY_DECODED_HEADER = [
    "Time_ms", "Profile", "ProfileConfidence", "SOC_pct", "Pack_V", "Pack_A", "Pack_kW",
    "MG1_RPM", "MG2_RPM", "Engine_RPM", "Gear_Candidate", "Engine_Coolant_F",
    "Engine_Intake_Air_F", "Catalyst_B1S1_F", "Converter_Temp_F", "MG1_Inv_F",
    "MG2_Inv_F", "MG1_Temp_F", "MG2_Temp_F", "HV_T1_F", "HV_T2_F", "HV_T3_F",
    "HV_Avg_F", "Battery_Intake_F", "Aux_V", "Fan_Level", "Delta_SOC_pct",
    "Block_Min_V", "Block_Min_Number", "Block_Max_V", "Block_Max_Number", "Block_Delta_V",
    "B01_V", "B02_V", "B03_V", "B04_V", "B05_V", "B06_V", "B07_V", "B08_V",
    "B09_V", "B10_V", "B11_V", "B12_V", "B13_V", "B14_V", "DataQuality",
]


def _word_be(data: bytes, pos: int) -> int:
    return (data[pos] << 8) | data[pos + 1]


def _raw_temperature_f(high: int, low: int) -> float:
    return ((high << 8) | low) * 9.0 / 500.0 - 557.824


def _fmt(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


class LegacyDecodedProjector:
    """Reproduce the useful legacy live-signal projection from authoritative RAW.

    This intentionally implements only formulas that were already present in the logger or
    explicitly frozen by the native-capture tests. It does not infer new CAN definitions.
    """

    def __init__(self, profile: str, confidence: int) -> None:
        self.profile = profile
        self.confidence = int(confidence)
        self.values: dict[str, float | int | str] = {}
        self.passive_times: dict[str, int] = {}
        self.diag_seen = False

    def _set(self, key: str, value: float | int | str) -> None:
        self.values[key] = value

    def observe_passive(self, time_us: int, can_id: int, data: bytes) -> None:
        if self.profile == "PRIUS GEN 2":
            if can_id == 0x03B and len(data) == 5:
                raw_current = ((data[0] & 0x0F) << 8) | data[1]
                if raw_current & 0x800:
                    raw_current -= 0x1000
                amps = raw_current * 0.1
                volts = float(_word_be(data, 2))
                if -500.0 <= amps <= 500.0 and 100.0 <= volts <= 400.0:
                    self._set("Pack_A", amps)
                    self._set("Pack_V", volts)
                    self._set("Pack_kW", volts * amps / 1000.0)
                    self.passive_times["electrical"] = time_us
            elif can_id == 0x3CB and len(data) == 7:
                soc = data[3] * 0.5
                t1 = data[4]
                t2 = data[5]
                if 0.0 <= soc <= 100.0 and t1 <= 100 and t2 <= 100:
                    self._set("SOC_pct", soc)
                    self._set("HV_T1_F", t1 * 1.8 + 32.0)
                    self._set("HV_T2_F", t2 * 1.8 + 32.0)
                    self._set("HV_Avg_F", (t1 + t2) * 0.9 + 32.0)
                    self.passive_times["soc"] = time_us
        elif self.profile == "CAMRY HYB G1":
            if can_id == 0x120 and len(data) >= 6:
                code = data[5] & 0x0F
                if code <= 3:
                    self._set("Gear_Candidate", ("P", "R", "N", "D")[code])
            elif can_id == 0x2C4 and len(data) >= 2:
                rpm = _word_be(data, 0)
                if rpm <= 8000:
                    self._set("Engine_RPM", rpm)
            elif can_id == 0x3B9 and len(data) >= 1 and data[0] <= 130:
                self._set("Engine_Coolant_F", data[0] * 1.8 + 32.0)

    def observe_transaction(self, tx: object) -> None:
        if getattr(tx, "status", "") != "OK":
            return
        service = getattr(tx, "service", None)
        pid = getattr(tx, "pid", None)
        payload = bytes(getattr(tx, "payload", b""))
        if service is None or not payload:
            return
        # ISO-TP payload normally includes positive service and PID before data.
        data = payload[2:] if pid is not None and len(payload) >= 2 else payload[1:]

        if service == 0x01 and pid is not None:
            if pid == 0x0C and len(data) >= 2:
                self._set("Engine_RPM", _word_be(data, 0) // 4)
            elif pid == 0x05 and data:
                self._set("Engine_Coolant_F", data[0] * 1.8 - 40.0)
            elif pid == 0x0F and data:
                self._set("Engine_Intake_Air_F", data[0] * 1.8 - 40.0)
            elif pid == 0x3C and len(data) >= 2:
                c = _word_be(data, 0) / 10.0 - 40.0
                self._set("Catalyst_B1S1_F", c * 1.8 + 32.0)
            self.diag_seen = True
            return

        if service != 0x21 or pid is None:
            return
        if self.profile == "PRIUS GEN 2":
            self._observe_gen2_21(pid, data)
        elif self.profile == "PRIUS PHV G1":
            self._observe_phv_21(pid, data)

    def _observe_gen2_21(self, pid: int, d: bytes) -> None:
        if pid == 0xC3 and len(d) >= 31:
            self._set("Engine_RPM", _word_be(d, 14))
            self._set("SOC_pct", 0.392 * d[18])
            self._set("MG1_Inv_F", 1.8 * d[24] - 58.0)
            self._set("MG2_Inv_F", 1.8 * d[25] - 58.0)
            self._set("MG1_Temp_F", 1.8 * d[26] - 58.0)
            self._set("MG2_Temp_F", 1.8 * d[27] - 58.0)
            volts = 2.0 * d[28]
            amps = 2.0 * d[30] - 256.0
            self._set("Pack_V", volts)
            self._set("Pack_A", amps)
            self._set("Pack_kW", volts * amps / 1000.0)
            self.diag_seen = True
        elif pid == 0xC4 and len(d) >= 6:
            self._set("Converter_Temp_F", 1.8 * d[5] - 58.0)
            self.diag_seen = True
        elif pid == 0xCE and len(d) >= 31:
            self._set("SOC_pct", 0.5 * d[0])
            amps = 2.56 * d[1] + 0.01 * d[2] - 327.68
            blocks = []
            for index in range(14):
                pos = 3 + index * 2
                value = 2.56 * d[pos] + 0.01 * d[pos + 1] - 327.68
                blocks.append(value)
                self._set(f"B{index + 1:02d}_V", value)
            volts = sum(blocks)
            self._set("Pack_A", amps)
            self._set("Pack_V", volts)
            self._set("Pack_kW", volts * amps / 1000.0)
            self.diag_seen = True
        elif pid == 0xCF and len(d) >= 16:
            self._set("Battery_Intake_F", _raw_temperature_f(d[0], d[1]))
            self._set("Aux_V", 0.2 * d[3] - 25.6)
            self._set("Delta_SOC_pct", 0.01 * d[6])
            self._set("Fan_Level", int(d[8]))
            temps = [_raw_temperature_f(d[10], d[11]), _raw_temperature_f(d[12], d[13]), _raw_temperature_f(d[14], d[15])]
            for key, value in zip(("HV_T1_F", "HV_T2_F", "HV_T3_F"), temps):
                self._set(key, value)
            self._set("HV_Avg_F", sum(temps) / 3.0)
            self.diag_seen = True
        elif pid == 0xD0 and len(d) >= 29:
            min_v = 2.56 * d[9] + 0.01 * d[10] - 327.68
            max_v = 2.56 * d[12] + 0.01 * d[13] - 327.68
            self._set("Block_Min_V", min_v)
            self._set("Block_Min_Number", int(d[11]) + 1)
            self._set("Block_Max_V", max_v)
            self._set("Block_Max_Number", int(d[14]) + 1)
            self._set("Block_Delta_V", max_v - min_v)
            self.diag_seen = True

    def _observe_phv_21(self, pid: int, d: bytes) -> None:
        # These are the already-established PHV live-display projections used by
        # the project tests. They are compatibility decodes, not new discovery.
        if pid == 0x01 and len(d) >= 22:
            self._set("Engine_RPM", int(d[2]) * 20)
            self._set("SOC_pct", d[21] * 20.0 / 51.0)
            self.diag_seen = True
        elif pid == 0x81 and len(d) >= 20:
            for index in range(8):
                self._set(f"B{index + 1:02d}_V", _word_be(d, index * 2) / 1000.0)
            for index in range(8, 14):
                self._set(f"B{index + 1:02d}_V", 0.0)
            self._set("Pack_V", _word_be(d, 18) / 10.0)
            self.diag_seen = True
        elif pid == 0x98 and len(d) >= 5:
            amps = (_word_be(d, 0) - 32768) * 0.01
            self._set("Pack_A", amps)
            if "Pack_V" in self.values:
                self._set("Pack_kW", float(self.values["Pack_V"]) * amps / 1000.0)
            self._set("Fan_Level", int(d[4]))
            self.diag_seen = True
        elif pid == 0x87 and len(d) >= 6:
            temps = [_raw_temperature_f(d[pos], d[pos + 1]) for pos in range(0, min(len(d), 6), 2)]
            for key, value in zip(("HV_T1_F", "HV_T2_F", "HV_T3_F"), temps):
                self._set(key, value)
            if temps:
                self._set("HV_Avg_F", sum(temps) / len(temps))
            self.diag_seen = True

    def row(self, time_us: int) -> dict[str, str]:
        values = dict(self.values)
        passive_soc_fresh = "soc" in self.passive_times and time_us - self.passive_times["soc"] <= 2_000_000
        passive_electrical_fresh = "electrical" in self.passive_times and time_us - self.passive_times["electrical"] <= 2_000_000
        if self.profile == "PRIUS GEN 2" and not self.diag_seen:
            if not passive_soc_fresh:
                for key in ("SOC_pct", "HV_T1_F", "HV_T2_F", "HV_Avg_F"):
                    values.pop(key, None)
            if not passive_electrical_fresh:
                for key in ("Pack_A", "Pack_V", "Pack_kW"):
                    values.pop(key, None)

        result = {key: "" for key in LEGACY_DECODED_HEADER}
        result["Time_ms"] = str(int(time_us // 1000))
        result["Profile"] = self.profile
        result["ProfileConfidence"] = str(self.confidence)
        integer_fields = {"MG1_RPM", "MG2_RPM", "Engine_RPM", "Fan_Level", "Block_Min_Number", "Block_Max_Number"}
        three_fields = {"Pack_kW"}
        one_fields = {"Engine_Coolant_F", "Engine_Intake_Air_F", "Catalyst_B1S1_F", "Converter_Temp_F", "MG1_Inv_F", "MG2_Inv_F", "MG1_Temp_F", "MG2_Temp_F", "HV_T1_F", "HV_T2_F", "HV_T3_F", "HV_Avg_F", "Battery_Intake_F"}
        for key, value in values.items():
            if key not in result:
                continue
            if isinstance(value, str):
                result[key] = value
            elif key in integer_fields:
                result[key] = str(int(value))
            elif key in three_fields:
                result[key] = _fmt(float(value), 3)
            elif key in one_fields:
                result[key] = _fmt(float(value), 1)
            else:
                result[key] = _fmt(float(value), 2)
        if self.profile == "PRIUS GEN 2":
            if self.diag_seen:
                result["DataQuality"] = "GEN2_DIAG_CONFIRMED"
            elif passive_soc_fresh:
                result["DataQuality"] = "PASSIVE_SOC_CONFIRMED"
            elif passive_electrical_fresh:
                result["DataQuality"] = "PASSIVE_ELECTRICAL_CONFIRMED"
        elif self.profile == "PRIUS PHV G1" and self.diag_seen:
            result["DataQuality"] = "PHV_DIAG_CONFIRMED"
        elif self.profile == "CAMRY HYB G1":
            result["DataQuality"] = "CAMRY_PASSIVE_PROBABLE"
        return result


def _profile_from_meta(session: object) -> tuple[str, int]:
    profile = "UNKNOWN"
    confidence = 0
    for record in session.meta.records:
        if record.record_type != 0x0030:
            continue
        decoded = decode_record_payload(record)
        if decoded.get("event_code") not in (17, 18):
            continue
        args = {arg_id: value for arg_id, _flags, value in decoded.get("args", ())}
        if 5 in args:
            profile = PROFILE_LABELS.get(int(args[5]), "UNKNOWN")
        if 6 in args:
            confidence = max(0, min(100, int(args[6])))
    return profile, confidence


def _merge_transactions(session: object) -> list[object]:
    logger = reconstruct_logger_diagnostics(iter_tcb_frames(session.can_paths), session.meta)
    external = reconstruct_external_transactions(iter_tcb_frames(session.can_paths))
    items = [item for item in (*logger, *external) if getattr(item, "complete_time_us", None) is not None]
    items.sort(key=lambda item: int(getattr(item, "complete_time_us")))
    return items


def write_legacy_decoded(session: object, path: Path) -> int:
    if session.can_stream is None or session.can_stream.first_time_us is None or session.can_stream.last_time_us is None:
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=LEGACY_DECODED_HEADER, lineterminator="\n").writeheader()
        return 0

    profile, confidence = _profile_from_meta(session)
    projector = LegacyDecodedProjector(profile, confidence)
    transactions = _merge_transactions(session)
    tx_index = 0
    frames = iter(iter_tcb_frames(session.can_paths))
    current = next(frames, None)
    first = session.can_stream.first_time_us
    last = session.can_stream.last_time_us
    sample = ((first + 99_999) // 100_000) * 100_000
    rows = 0

    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_DECODED_HEADER, lineterminator="\n")
        writer.writeheader()
        while sample < last:
            while current is not None and current.time_us <= sample:
                if current.direction == 0 and not current.extended and not current.rtr:
                    projector.observe_passive(current.time_us, current.can_id, bytes(current.data[:current.dlc]))
                current = next(frames, None)
            while tx_index < len(transactions) and int(getattr(transactions[tx_index], "complete_time_us")) <= sample:
                projector.observe_transaction(transactions[tx_index])
                tx_index += 1
            writer.writerow(projector.row(sample))
            rows += 1
            sample += 100_000
    return rows
