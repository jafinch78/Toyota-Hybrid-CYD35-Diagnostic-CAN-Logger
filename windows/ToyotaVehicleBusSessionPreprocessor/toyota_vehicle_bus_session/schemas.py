SYNC_HEADER = ["Sequence", "ESP_Receive_us", "ESP_Send_us", "Source"]
EVENTS_HEADER = ["Time_us", "Severity", "Event", "Details"]
DIAGNOSTICS_HEADER = ["Transaction", "RequestTime_us", "CompleteTime_us", "RequestID", "ResponseID", "Service", "PID", "Status", "PayloadLength", "PayloadHex", "FrameCount", "ResponseTime_ms"]
EXTERNAL_DIAGNOSTICS_HEADER = ["Time_us", "CAN_ID", "DLC", "DataHex", "Classification"]

EVENT_NAMES = {
    1: "LOGGING_STARTED", 2: "LOGGING_STOP_REQUESTED", 3: "LOGGING_STOPPED",
    4: "CAN_TRAFFIC_STARTED", 5: "RAW_ROTATION_FAILED", 6: "EXTERNAL_TESTER_DETECTED",
    7: "TWAI_START_FAILED", 8: "TWAI_TRANSMIT_BLOCKED", 9: "TWAI_TRANSMIT_FAILED",
    10: "TWAI_MODE_CHANGE_FAILED", 11: "BLE_CAPTURE_START", 12: "BLE_CAPTURE_STOP",
    13: "BLE_MARKER", 14: "DIAGNOSTIC_ENABLE_REJECTED", 15: "DIAGNOSTIC_IDENTITY_UNRESOLVED",
    16: "DIAGNOSTIC_RUNTIME_DECODE_MISSING", 17: "DATABASE_PROFILE_EVIDENCE",
    18: "PROFILE_CHANGE", 19: "DIAGNOSTIC_IDENTITY_FALLBACK", 65535: "OTHER",
}
SEVERITY_NAMES = {0: "INFO", 1: "WARNING", 2: "ERROR", 3: "FATAL"}
SOURCE_NAMES = {0: "BLE", 1: "BLE_PRESTART", 255: "UNKNOWN"}

# Match the logger's VehicleProfile uint8_t enum so firmware and offline tools
# can exchange profile provenance without a second translation namespace.
PROFILE_LABELS = {
    0: "SCANNING",
    1: "PRIUS GEN 2",
    2: "PRIUS GEN 3",
    3: "PRIUS PHV G1",
    4: "CAMRY HYB G1",
    5: "GEN3/PHV AMBIG",
    6: "UNKNOWN",
    7: "CONFLICT",
}
PROFILE_ALIASES = {
    "SCANNING": 0,
    "PRIUS GEN 2": 1,
    "PRIUS_GEN2": 1,
    "PRIUS GEN2": 1,
    "PRIUS GEN 3": 2,
    "PRIUS_GEN3": 2,
    "PRIUS GEN3": 2,
    "PRIUS PHV G1": 3,
    "PRIUS PHV GEN 1": 3,
    "PRIUS_PHV_GEN1": 3,
    "CAMRY HYB G1": 4,
    "CAMRY HYBRID GEN 1": 4,
    "CAMRY_HYBRID_GEN1": 4,
    "GEN3/PHV AMBIG": 5,
    "PRIUS_GEN3_OR_PHV": 5,
    "UNKNOWN": 6,
    "CONFLICT": 7,
}
PROFILE_MODEL_CODES = {
    1: "NHW20",
    3: "ZVW35",
    4: "AHV40L",
}


def profile_enum(value: object) -> int | None:
    text = str(value or "").strip().upper().replace("-", " ")
    text = " ".join(text.split())
    return PROFILE_ALIASES.get(text)
