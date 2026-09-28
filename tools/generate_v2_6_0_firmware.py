from __future__ import annotations

import shutil
from pathlib import Path

OUT_DIR_NAME = "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0"
OLD_INO = "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0.ino"
NEW_INO = "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino"


def _find_function_end(text: str, signature: str) -> tuple[int, int, int]:
    start = text.find(signature)
    if start < 0:
        raise ValueError(f"function signature not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise ValueError(f"opening brace not found: {signature}")
    depth = 0
    in_string: str | None = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string is not None:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == in_string:
                in_string = None
            i += 1
            continue
        if c == "/" and n == "/":
            line_comment = True
            i += 2
            continue
        if c == "/" and n == "*":
            block_comment = True
            i += 2
            continue
        if c in ('"', "'"):
            in_string = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, brace, i + 1
        i += 1
    raise ValueError(f"unterminated function: {signature}")


def _replace_function(text: str, signature: str, body: str) -> str:
    start, brace, end = _find_function_end(text, signature)
    prefix = text[start:brace]
    replacement = prefix + "{\n" + body.rstrip() + "\n}"
    return text[:start] + replacement + text[end:]


def _prepend_function(text: str, signature: str, prefix_body: str) -> str:
    start, brace, end = _find_function_end(text, signature)
    old_body = text[brace + 1:end - 1]
    return text[:brace + 1] + "\n" + prefix_body.rstrip() + "\n" + old_body + text[end - 1:]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


TVM1_META_H = r'''#pragma once

#include <Arduino.h>
#include <FS.h>

static constexpr char TVM1_MAGIC[4] = {'T', 'V', 'M', '1'};
static constexpr uint8_t TVM1_MAJOR = 1;
static constexpr uint8_t TVM1_MINOR = 0;
static constexpr uint16_t TVM1_HEADER_SIZE = 32;
static constexpr uint16_t TVM1_RECORD_SYNC = 0xA55A;
static constexpr uint16_t TVM1_MIN_RECORD_SIZE = 24;
static constexpr uint16_t TVM1_MAX_RECORD_SIZE = 4096;
static constexpr uint32_t TVM1_CRC32_POLYNOMIAL = 0xEDB88320UL;

static constexpr uint16_t TVM1_SESSION_START = 0x0001;
static constexpr uint16_t TVM1_STREAM_REGISTER = 0x0002;
static constexpr uint16_t TVM1_STREAM_START = 0x0003;
static constexpr uint16_t TVM1_STREAM_STOP = 0x0004;
static constexpr uint16_t TVM1_STREAM_FILE_OPEN = 0x0005;
static constexpr uint16_t TVM1_STREAM_FILE_CLOSE = 0x0006;
static constexpr uint16_t TVM1_CLOCK_SYNC = 0x0010;
static constexpr uint16_t TVM1_USER_MARKER = 0x0011;
static constexpr uint16_t TVM1_HEALTH_SNAPSHOT = 0x0020;
static constexpr uint16_t TVM1_STREAM_COUNTERS = 0x0021;
static constexpr uint16_t TVM1_STORAGE_HEALTH = 0x0022;
static constexpr uint16_t TVM1_EVENT = 0x0030;
static constexpr uint16_t TVM1_DIAGNOSTIC_STATE = 0x0031;
static constexpr uint16_t TVM1_BUS_STATE = 0x0032;
static constexpr uint16_t TVM1_SESSION_CLOSE = 0x00FE;

static constexpr uint8_t TVM1_STREAM_SESSION = 0;
static constexpr uint8_t TVM1_STREAM_CAN = 1;

inline void tvm1PutLe16(uint8_t *dst, uint16_t value) {
  dst[0] = (uint8_t)(value & 0xFFU);
  dst[1] = (uint8_t)((value >> 8) & 0xFFU);
}

inline void tvm1PutLe32(uint8_t *dst, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) dst[i] = (uint8_t)((value >> (8U * i)) & 0xFFU);
}

inline void tvm1PutLe64(uint8_t *dst, uint64_t value) {
  for (uint8_t i = 0; i < 8; ++i) dst[i] = (uint8_t)((value >> (8U * i)) & 0xFFU);
}

inline uint16_t tvm1GetLe16(const uint8_t *src) {
  return (uint16_t)src[0] | ((uint16_t)src[1] << 8);
}

inline uint32_t tvm1GetLe32(const uint8_t *src) {
  return (uint32_t)src[0] | ((uint32_t)src[1] << 8) |
         ((uint32_t)src[2] << 16) | ((uint32_t)src[3] << 24);
}

inline uint32_t tvm1Crc32Update(uint32_t crc, const uint8_t *data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (TVM1_CRC32_POLYNOMIAL & (uint32_t)-(int32_t)(crc & 1U));
  }
  return crc;
}

inline uint32_t tvm1Crc32(const uint8_t *data, size_t length) {
  return tvm1Crc32Update(0xFFFFFFFFUL, data, length) ^ 0xFFFFFFFFUL;
}

class Tvm1Writer {
 public:
  Tvm1Writer() : file_(nullptr), sequence_(0) {}

  bool begin(File &file, uint32_t sessionNumber, uint64_t sessionCreateUs) {
    file_ = &file;
    sequence_ = 0;
    uint8_t header[TVM1_HEADER_SIZE] = {};
    memcpy(header, TVM1_MAGIC, sizeof(TVM1_MAGIC));
    header[4] = TVM1_MAJOR;
    header[5] = TVM1_MINOR;
    tvm1PutLe16(header + 6, TVM1_HEADER_SIZE);
    tvm1PutLe32(header + 8, sessionNumber);
    tvm1PutLe32(header + 12, 0);
    tvm1PutLe64(header + 16, sessionCreateUs);
    tvm1PutLe32(header + 24, tvm1Crc32(header, 24));
    tvm1PutLe32(header + 28, 0);
    return file_->write(header, sizeof(header)) == sizeof(header);
  }

  bool append(uint16_t recordType, uint8_t streamId, uint8_t flags,
              uint64_t timeUs, const uint8_t *payload, uint16_t payloadLen) {
    if (file_ == nullptr || !(*file_)) return false;
    const uint16_t total = (uint16_t)(TVM1_MIN_RECORD_SIZE + payloadLen);
    if (total < TVM1_MIN_RECORD_SIZE || total > TVM1_MAX_RECORD_SIZE) return false;

    uint8_t envelope[20] = {};
    tvm1PutLe16(envelope + 0, TVM1_RECORD_SYNC);
    tvm1PutLe16(envelope + 2, total);
    tvm1PutLe16(envelope + 4, recordType);
    envelope[6] = streamId;
    envelope[7] = flags;
    const uint32_t nextSequence = sequence_ + 1U;
    tvm1PutLe32(envelope + 8, nextSequence);
    tvm1PutLe64(envelope + 12, timeUs);

    uint32_t crc = tvm1Crc32Update(0xFFFFFFFFUL, envelope, sizeof(envelope));
    if (payloadLen != 0 && payload != nullptr)
      crc = tvm1Crc32Update(crc, payload, payloadLen);
    crc ^= 0xFFFFFFFFUL;
    uint8_t crcBytes[4];
    tvm1PutLe32(crcBytes, crc);

    if (file_->write(envelope, sizeof(envelope)) != sizeof(envelope)) return false;
    if (payloadLen != 0 && file_->write(payload, payloadLen) != payloadLen) return false;
    if (file_->write(crcBytes, sizeof(crcBytes)) != sizeof(crcBytes)) return false;
    sequence_ = nextSequence;
    return true;
  }

  bool flush() {
    if (file_ == nullptr || !(*file_)) return false;
    file_->flush();
    return true;
  }

  uint32_t sequence() const { return sequence_; }
  bool valid() const { return file_ != nullptr && (bool)(*file_); }
  void detach() { file_ = nullptr; sequence_ = 0; }

 private:
  File *file_;
  uint32_t sequence_;
};
'''


BOARD_BLOCK = r'''// v2.6 supported board profiles. Dorhea remains the default because its fixed
// calibration is already bench validated. E32R35T uses first-boot TFT_eSPI
// calibration stored in NVS; no E32N35T calibration values are relabeled.
#define CYD_BOARD_PROFILE_DORHEA 1
#define CYD_BOARD_PROFILE_E32R35T 2
#ifndef CYD_BOARD_PROFILE_SELECT
#define CYD_BOARD_PROFILE_SELECT CYD_BOARD_PROFILE_DORHEA
#endif

#if CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_DORHEA
constexpr char CYD_BOARD_PROFILE[] = "DORHEA_B0DLNJSSFW_TOUCH";
uint16_t touchCalibration[5] = {295, 3524, 310, 3487, 3};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = false;
#elif CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_E32R35T
constexpr char CYD_BOARD_PROFILE[] = "E32R35T_TOUCH";
uint16_t touchCalibration[5] = {0, 0, 0, 0, 0};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = true;
#else
#error "CYD_BOARD_PROFILE_SELECT must be Dorhea or E32R35T"
#endif'''


META_GLOBALS = r'''File rawFile;
File metaFile;
Tvm1Writer tvm1Writer;

constexpr uint8_t META_QUEUE_LENGTH = 16;
constexpr uint16_t META_PAYLOAD_MAX = 192;
struct PendingMetaRecord {
  uint16_t type;
  uint8_t streamId;
  uint8_t flags;
  uint64_t timeUs;
  uint16_t payloadLen;
  uint8_t payload[META_PAYLOAD_MAX];
};
PendingMetaRecord metaQueueRecords[META_QUEUE_LENGTH] = {};
uint8_t metaQueueHead = 0;
uint8_t metaQueueTail = 0;
uint8_t metaQueueCount = 0;
uint32_t metaQueueDrops = 0;
uint32_t metaWriteErrors = 0;
uint32_t metaFlushCount = 0;
uint64_t metaFlushMaxUs = 0;
uint64_t rawWriteCount = 0;
uint64_t rawWriteTotalUs = 0;
uint64_t rawWriteMaxUs = 0;
uint64_t rawFlushCount = 0;
uint64_t rawFlushMaxUs = 0;
uint32_t rawShortWriteCount = 0;
uint32_t canQueueHighWater = 0;
uint64_t mainLoopMaxUs = 0;
uint64_t tftRenderCount = 0;
uint64_t tftRenderMaxUs = 0;
uint64_t rawFilePersistedRecords = 0;
uint64_t rawFilePersistedBytes = 0;
uint32_t lastHealthMetaMs = 0;
bool stopPending = false;
bool stopPendingClean = true;
uint64_t stopRequestUs = 0;
uint16_t stopCommandSequence = 0;
bool startPending = false;
uint64_t startRequestUs = 0;
uint16_t startCommandSequence = 0;
bool displayPageChanged = true;'''


HELPERS = r'''
static uint16_t appendTvm1String(uint8_t *payload, uint16_t offset, uint16_t capacity, const char *value) {
  if (value == nullptr) value = "";
  size_t length = strlen(value);
  if (length > 255U) length = 255U;
  if ((uint32_t)offset + 2U + length > capacity) return 0xFFFFU;
  tvm1PutLe16(payload + offset, (uint16_t)length);
  offset += 2;
  if (length) memcpy(payload + offset, value, length);
  return (uint16_t)(offset + length);
}

bool enqueueMetaRecord(uint16_t recordType, uint8_t streamId, uint8_t flags,
                       uint64_t timeUs, const uint8_t *payload, uint16_t payloadLen) {
  if (!loggingActive || !metaFile || payloadLen > META_PAYLOAD_MAX || metaQueueCount >= META_QUEUE_LENGTH) {
    ++metaQueueDrops;
    return false;
  }
  PendingMetaRecord &slot = metaQueueRecords[metaQueueTail];
  slot.type = recordType;
  slot.streamId = streamId;
  slot.flags = flags;
  slot.timeUs = timeUs;
  slot.payloadLen = payloadLen;
  if (payloadLen && payload != nullptr) memcpy(slot.payload, payload, payloadLen);
  metaQueueTail = (uint8_t)((metaQueueTail + 1U) % META_QUEUE_LENGTH);
  ++metaQueueCount;
  return true;
}

bool appendMetaDirect(uint16_t recordType, uint8_t streamId, uint8_t flags,
                      uint64_t timeUs, const uint8_t *payload = nullptr, uint16_t payloadLen = 0) {
  if (!metaFile || !tvm1Writer.valid()) return false;
  if (!tvm1Writer.append(recordType, streamId, flags, timeUs, payload, payloadLen)) {
    ++metaWriteErrors;
    Serial.printf("# META WRITE ERROR,type=0x%04X,seq=%lu\n", recordType,
                  (unsigned long)(tvm1Writer.sequence() + 1U));
    return false;
  }
  return true;
}

void serviceMetaQueue() {
  if (!loggingActive || !metaFile) return;
  while (metaQueueCount) {
    PendingMetaRecord &slot = metaQueueRecords[metaQueueHead];
    if (!appendMetaDirect(slot.type, slot.streamId, slot.flags, slot.timeUs,
                          slot.payload, slot.payloadLen)) return;
    metaQueueHead = (uint8_t)((metaQueueHead + 1U) % META_QUEUE_LENGTH);
    --metaQueueCount;
  }
}

static bool emitSessionStart(uint64_t timeUs) {
  uint8_t payload[180] = {};
  uint16_t offset = 0;
  offset = appendTvm1String(payload, offset, sizeof(payload), "Toyota Hybrid CYD35 CAN Logger");
  if (offset == 0xFFFFU) return false;
  offset = appendTvm1String(payload, offset, sizeof(payload), "2.6.0-dev");
  if (offset == 0xFFFFU) return false;
  offset = appendTvm1String(payload, offset, sizeof(payload), CYD_BOARD_PROFILE);
  if (offset == 0xFFFFU) return false;
  offset = appendTvm1String(payload, offset, sizeof(payload), "RC2-bbc7421-derived");
  if (offset == 0xFFFFU) return false;
  offset = appendTvm1String(payload, offset, sizeof(payload), "");
  if (offset == 0xFFFFU) return false;
  return appendMetaDirect(TVM1_SESSION_START, TVM1_STREAM_SESSION, 0, timeUs, payload, offset);
}

static bool emitCanStreamRegister(uint64_t timeUs) {
  uint8_t payload[12] = {1, 1, 1, 0, 0x03, 0, 0, 0, 0, 0, 0, 0};
  tvm1PutLe32(payload + 8, CAN_BITRATE);
  return appendMetaDirect(TVM1_STREAM_REGISTER, TVM1_STREAM_CAN, 0, timeUs, payload, sizeof(payload));
}

static bool emitStreamFileOpen(uint64_t timeUs, uint16_t index) {
  char basename[20];
  snprintf(basename, sizeof(basename), "RAW_%03u.TCB", index);
  uint8_t payload[32] = {};
  tvm1PutLe16(payload, index);
  uint16_t length = appendTvm1String(payload, 2, sizeof(payload), basename);
  return length != 0xFFFFU && appendMetaDirect(TVM1_STREAM_FILE_OPEN, TVM1_STREAM_CAN, 0, timeUs, payload, length);
}

static bool emitStreamFileClose(uint64_t timeUs, uint16_t index, uint16_t reason) {
  uint8_t payload[20] = {};
  tvm1PutLe16(payload + 0, index);
  tvm1PutLe16(payload + 2, reason);
  tvm1PutLe64(payload + 4, rawFilePersistedRecords);
  tvm1PutLe64(payload + 12, rawFilePersistedBytes);
  return appendMetaDirect(TVM1_STREAM_FILE_CLOSE, TVM1_STREAM_CAN, 0, timeUs, payload, sizeof(payload));
}

static void emitStreamCounters(bool directWrite) {
  uint8_t payload[48] = {};
  tvm1PutLe64(payload + 0, (uint64_t)(receivedFrameCount - sessionStartReceivedFrames));
  tvm1PutLe64(payload + 8, (uint64_t)(transmittedFrameCount - sessionStartTransmittedFrames));
  tvm1PutLe64(payload + 16, rawSequence);
  tvm1PutLe64(payload + 24, canQueueDrops);
  tvm1PutLe64(payload + 32, sdLogDroppedFrames);
  tvm1PutLe32(payload + 40, canQueueHighWater);
  tvm1PutLe32(payload + 44, twaiBusErrorCount);
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  if (directWrite) appendMetaDirect(TVM1_STREAM_COUNTERS, TVM1_STREAM_CAN, 0, nowUs, payload, sizeof(payload));
  else enqueueMetaRecord(TVM1_STREAM_COUNTERS, TVM1_STREAM_CAN, 0, nowUs, payload, sizeof(payload));
}

static uint16_t appendMetric(uint8_t *payload, uint16_t offset, uint16_t capacity,
                             uint16_t id, uint16_t flags, uint64_t value) {
  if ((uint32_t)offset + 12U > capacity) return offset;
  tvm1PutLe16(payload + offset, id);
  tvm1PutLe16(payload + offset + 2, flags);
  tvm1PutLe64(payload + offset + 4, value);
  return (uint16_t)(offset + 12U);
}

static void emitHealthSnapshot(bool directWrite) {
  uint8_t payload[128] = {};
  tvm1PutLe16(payload, 1);
  uint16_t offset = 4;
  uint16_t count = 0;
#define ADD_HEALTH(ID, FLAGS, VALUE) do { offset = appendMetric(payload, offset, sizeof(payload), ID, FLAGS, (uint64_t)(VALUE)); ++count; } while (0)
  ADD_HEALTH(1, 0, ESP.getFreeHeap());
  ADD_HEALTH(2, 0, heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
  ADD_HEALTH(3, 1, heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT));
  ADD_HEALTH(4, 1, mainLoopMaxUs);
  ADD_HEALTH(5, 1, uxTaskGetStackHighWaterMark(nullptr) * sizeof(StackType_t));
  ADD_HEALTH(6, 1, canReceiveTaskHandle ? uxTaskGetStackHighWaterMark(canReceiveTaskHandle) * sizeof(StackType_t) : 0);
  ADD_HEALTH(7, 1, tftRenderMaxUs);
  ADD_HEALTH(8, 0, rawWriteCount ? rawWriteTotalUs / rawWriteCount : 0);
  ADD_HEALTH(9, 1, rawWriteMaxUs);
  ADD_HEALTH(10, 1, rawFlushMaxUs > metaFlushMaxUs ? rawFlushMaxUs : metaFlushMaxUs);
  ADD_HEALTH(11, 0, rawFlushCount + metaFlushCount);
#undef ADD_HEALTH
  tvm1PutLe16(payload + 2, count);
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  if (directWrite) appendMetaDirect(TVM1_HEALTH_SNAPSHOT, 0, 0, nowUs, payload, offset);
  else enqueueMetaRecord(TVM1_HEALTH_SNAPSHOT, 0, 0, nowUs, payload, offset);
}

static void emitStorageHealth(bool directWrite) {
  uint8_t payload[80] = {};
  tvm1PutLe16(payload, 1);
  uint16_t offset = 4;
  uint16_t count = 0;
#define ADD_STORAGE(ID, FLAGS, VALUE) do { offset = appendMetric(payload, offset, sizeof(payload), ID, FLAGS, (uint64_t)(VALUE)); ++count; } while (0)
  uint64_t total = sdReady ? SD.totalBytes() : 0;
  uint64_t used = sdReady ? SD.usedBytes() : 0;
  ADD_STORAGE(1, 0, total);
  ADD_STORAGE(2, 0, total >= used ? total - used : 0);
  ADD_STORAGE(3, 0, sdLogDrops + metaWriteErrors);
  ADD_STORAGE(4, 0, rawShortWriteCount);
  ADD_STORAGE(5, 0, 0);
  ADD_STORAGE(6, 0, 0);
#undef ADD_STORAGE
  tvm1PutLe16(payload + 2, count);
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  if (directWrite) appendMetaDirect(TVM1_STORAGE_HEALTH, 0, 0, nowUs, payload, offset);
  else enqueueMetaRecord(TVM1_STORAGE_HEALTH, 0, 0, nowUs, payload, offset);
}

static bool captureUnderPressure() {
  if (canQueue == nullptr) return false;
  UBaseType_t depth = uxQueueMessagesWaiting(canQueue);
  if (depth > canQueueHighWater) canQueueHighWater = depth;
  return depth >= (CAN_QUEUE_LENGTH * 3U) / 4U;
}

static void emitPeriodicHealth() {
  if (!loggingActive || captureUnderPressure()) return;
  uint32_t nowMs = millis();
  if (nowMs - lastHealthMetaMs < 5000U) return;
  lastHealthMetaMs = nowMs;
  emitStreamCounters(false);
  emitHealthSnapshot(false);
  emitStorageHealth(false);
}

static uint8_t eventSeverityCode(const char *severity) {
  if (severity && strcmp(severity, "FATAL") == 0) return 3;
  if (severity && strcmp(severity, "ERROR") == 0) return 2;
  if (severity && strcmp(severity, "WARN") == 0) return 1;
  if (severity && strcmp(severity, "WARNING") == 0) return 1;
  return 0;
}

static uint16_t eventCodeForName(const char *name) {
  if (!name) return 65535;
  if (!strcmp(name, "LOGGING_STARTED")) return 1;
  if (!strcmp(name, "LOGGING_STOP_REQUESTED")) return 2;
  if (!strcmp(name, "LOGGING_STOPPED")) return 3;
  if (!strcmp(name, "CAN_TRAFFIC_STARTED")) return 4;
  if (!strcmp(name, "RAW_ROTATION_FAILED")) return 5;
  if (!strcmp(name, "EXTERNAL_TESTER_DETECTED")) return 6;
  if (!strcmp(name, "TWAI_START_FAILED")) return 7;
  if (!strcmp(name, "TWAI_TRANSMIT_BLOCKED")) return 8;
  if (!strcmp(name, "TWAI_TRANSMIT_FAILED")) return 9;
  if (!strcmp(name, "TWAI_MODE_CHANGE_FAILED")) return 10;
  if (!strcmp(name, "BLE_CAPTURE_START")) return 11;
  if (!strcmp(name, "BLE_CAPTURE_STOP")) return 12;
  if (!strcmp(name, "BLE_MARKER")) return 13;
  if (!strcmp(name, "DIAGNOSTIC_ENABLE_REJECTED")) return 14;
  if (!strcmp(name, "DIAGNOSTIC_IDENTITY_UNRESOLVED")) return 15;
  if (!strcmp(name, "DIAGNOSTIC_RUNTIME_DECODE_MISSING")) return 16;
  if (!strcmp(name, "DATABASE_PROFILE_EVIDENCE")) return 17;
  if (!strcmp(name, "PROFILE_CHANGE")) return 18;
  if (!strcmp(name, "DIAGNOSTIC_IDENTITY_FALLBACK")) return 19;
  return 65535;
}

static void emitDiagnosticState(uint16_t stateCode, uint16_t reasonCode,
                                uint32_t value0 = 0, uint32_t value1 = 0) {
  uint8_t payload[12] = {};
  tvm1PutLe16(payload, stateCode);
  tvm1PutLe16(payload + 2, reasonCode);
  tvm1PutLe32(payload + 4, value0);
  tvm1PutLe32(payload + 8, value1);
  enqueueMetaRecord(TVM1_DIAGNOSTIC_STATE, TVM1_STREAM_CAN, 0,
                    (uint64_t)esp_timer_get_time(), payload, sizeof(payload));
}

bool externalTesterInterlockActive() {
  uint64_t lastUs = externalTesterLastUs;
  if (lastUs == 0) return false;
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  return nowUs >= lastUs && nowUs - lastUs < (uint64_t)EXTERNAL_TESTER_HOLD_MS * 1000ULL;
}

void configureTouchForBoard() {
  if (!CYD_TOUCH_AUTO_CALIBRATE) {
    tft.setTouch(touchCalibration);
    return;
  }
  Preferences touchPrefs;
  bool loaded = false;
  if (touchPrefs.begin("tftcal26", false)) {
    if (touchPrefs.getBytesLength("e32r35t") == sizeof(touchCalibration)) {
      loaded = touchPrefs.getBytes("e32r35t", touchCalibration, sizeof(touchCalibration)) == sizeof(touchCalibration);
    }
    if (!loaded) {
      tft.fillScreen(TFT_BLACK);
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
      tft.drawString("E32R35T TOUCH CALIBRATION", 35, 20, 2);
      tft.calibrateTouch(touchCalibration, TFT_MAGENTA, TFT_BLACK, 15);
      touchPrefs.putBytes("e32r35t", touchCalibration, sizeof(touchCalibration));
    }
    touchPrefs.end();
  }
  tft.setTouch(touchCalibration);
}

bool isNativeTvm1SessionClean(const String &sessionPath) {
  String metaPath = sessionPath + "/SESSION.META";
  if (!SD.exists(metaPath.c_str())) return false;
  File file = SD.open(metaPath.c_str(), FILE_READ);
  if (!file || file.size() < TVM1_HEADER_SIZE) { if (file) file.close(); return false; }
  uint8_t header[TVM1_HEADER_SIZE];
  if (file.read(header, sizeof(header)) != sizeof(header)) { file.close(); return false; }
  if (memcmp(header, TVM1_MAGIC, 4) != 0 || tvm1GetLe16(header + 6) != TVM1_HEADER_SIZE ||
      tvm1GetLe32(header + 24) != tvm1Crc32(header, 24)) { file.close(); return false; }
  bool clean = false;
  while ((size_t)(file.size() - file.position()) >= TVM1_MIN_RECORD_SIZE) {
    uint8_t envelope[20];
    if (file.read(envelope, sizeof(envelope)) != sizeof(envelope)) break;
    uint16_t total = tvm1GetLe16(envelope + 2);
    uint16_t type = tvm1GetLe16(envelope + 4);
    if (tvm1GetLe16(envelope) != TVM1_RECORD_SYNC || total < TVM1_MIN_RECORD_SIZE || total > TVM1_MAX_RECORD_SIZE) break;
    uint16_t payloadLen = (uint16_t)(total - TVM1_MIN_RECORD_SIZE);
    if ((size_t)(file.size() - file.position()) < (size_t)payloadLen + 4U) break;
    if (type == TVM1_SESSION_CLOSE && payloadLen == 8) {
      uint8_t payload[8]; uint8_t crcBytes[4];
      if (file.read(payload, sizeof(payload)) != sizeof(payload) || file.read(crcBytes, 4) != 4) break;
      uint32_t crc = tvm1Crc32Update(0xFFFFFFFFUL, envelope, sizeof(envelope));
      crc = tvm1Crc32Update(crc, payload, sizeof(payload)) ^ 0xFFFFFFFFUL;
      if (crc == tvm1GetLe32(crcBytes) && payload[2] == 1) clean = true;
    } else {
      if (!file.seek(file.position() + payloadLen + 4U)) break;
    }
  }
  file.close();
  return clean;
}

bool isSessionClosedForWifi(const String &sessionPath) {
  String metaPath = sessionPath + "/SESSION.META";
  if (SD.exists(metaPath.c_str())) return isNativeTvm1SessionClean(sessionPath);
  String legacyMarker = sessionPath + "/SESSION.OPEN";
  return !SD.exists(legacyMarker.c_str());
}

void drawDirtyField(int16_t x, int16_t y, int16_t w, int16_t h,
                    const char *text, char *cache, size_t cacheSize, bool force = false) {
  if (!force && strncmp(cache, text, cacheSize) == 0) return;
  tft.fillRect(x, y, w, h, TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString(text, x, y, 2);
  strncpy(cache, text, cacheSize - 1);
  cache[cacheSize - 1] = '\0';
}
'''


START_LOGGING_BODY = r'''  if (loggingActive || !sdReady) return loggingActive;
  if (!createSessionDirectory()) return failLogStart("SESSION_DIRECTORY");

  // Explicitly discard any pre-session residue so it cannot be silently
  // attributed to the new synchronized capture.
  uint32_t staleFrames = 0;
  CapturedFrame stale = {};
  while (canQueue != nullptr && xQueueReceive(canQueue, &stale, 0) == pdTRUE) ++staleFrames;
  while (diagnosticQueue != nullptr && xQueueReceive(diagnosticQueue, &stale, 0) == pdTRUE) {}

  rawFileIndex = 0;
  rawSequence = 0;
  rawFilePersistedRecords = 0;
  rawFilePersistedBytes = 0;
  metaQueueHead = metaQueueTail = metaQueueCount = 0;
  metaQueueDrops = metaWriteErrors = 0;
  canQueueHighWater = 0;
  mainLoopMaxUs = rawWriteCount = rawWriteTotalUs = rawWriteMaxUs = 0;
  rawFlushCount = rawFlushMaxUs = metaFlushCount = metaFlushMaxUs = 0;
  rawShortWriteCount = 0;
  lastHealthMetaMs = millis();
  sessionHasCanTraffic = false;
  sessionFirstCanUs = 0;
  sessionLastCanUs = 0;
  sessionStartReceivedFrames = receivedFrameCount;
  sessionStartTransmittedFrames = transmittedFrameCount;

  if (!openRawFile()) return failLogStart("RAW_000.TCB");
  char metaPath[64];
  snprintf(metaPath, sizeof(metaPath), "%s/SESSION.META", sessionDir);
  metaFile = SD.open(metaPath, FILE_WRITE);
  if (!metaFile) return failLogStart("SESSION.META");

  uint64_t createUs = startRequestUs ? startRequestUs : (uint64_t)esp_timer_get_time();
  if (!tvm1Writer.begin(metaFile, reservedSessionNumber, createUs)) return failLogStart("TVM1_HEADER");
  if (!emitSessionStart(createUs) || !emitCanStreamRegister(createUs) ||
      !appendMetaDirect(TVM1_STREAM_START, TVM1_STREAM_CAN, 0, createUs) ||
      !emitStreamFileOpen(createUs, rawFileIndex)) return failLogStart("TVM1_START_RECORDS");

  loggingActive = true;
  manifestClosed = false;
  setLoggerStatus("ARMED / WAIT CAN");
  if (staleFrames) {
    uint8_t payload[16] = {};
    tvm1PutLe16(payload, 65535);
    payload[2] = 1;
    payload[3] = 1;
    tvm1PutLe16(payload + 4, 4);
    tvm1PutLe16(payload + 6, 0);
    tvm1PutLe64(payload + 8, staleFrames);
    enqueueMetaRecord(TVM1_EVENT, TVM1_STREAM_CAN, 0, createUs, payload, sizeof(payload));
  }
  writeEvent("INFO", "LOGGING_STARTED", String(sessionDir));
  for (uint8_t i = 0; i < pendingSyncCount; ++i) writeSyncRecord(pendingSync[i], "BLE_PRESTART");
  pendingSyncCount = 0;
  startPending = false;
  startRequestUs = 0;
  Serial.printf("# LOG STARTED,%s,RAW+TVM1\n", sessionDir);
  return true;'''


RAW_BATCH_BODY = r'''  if (!loggingActive || !rawFile || count == 0) return;
  bool firstTrafficInBatch = false;
  for (size_t i = 0; i < count; ++i) {
    if (frames[i].direction != 0) continue;
    if (!sessionHasCanTraffic) {
      sessionHasCanTraffic = true;
      sessionFirstCanUs = frames[i].timeUs;
      firstTrafficInBatch = true;
      setLoggerStatus("LOGGING");
    }
    sessionLastCanUs = frames[i].timeUs;
  }
  const size_t bytes = count * sizeof(CapturedFrame);
  uint64_t startedUs = (uint64_t)esp_timer_get_time();
  size_t written = rawFile.write((const uint8_t *)frames, bytes);
  uint64_t elapsedUs = (uint64_t)esp_timer_get_time() - startedUs;
  ++rawWriteCount;
  rawWriteTotalUs += elapsedUs;
  if (elapsedUs > rawWriteMaxUs) rawWriteMaxUs = elapsedUs;
  size_t completeRecords = written / sizeof(CapturedFrame);
  rawSequence += completeRecords;
  rawFilePersistedRecords += completeRecords;
  rawFilePersistedBytes += completeRecords * sizeof(CapturedFrame);
  if (written != bytes) {
    ++sdLogDrops;
    ++rawShortWriteCount;
    sdLogDroppedFrames += (uint32_t)(count - completeRecords);
  }
  if (firstTrafficInBatch)
    writeEvent("INFO", "CAN_TRAFFIC_STARTED", "First received CAN frame committed to RAW");
  rotateRawFileIfNeeded();'''


ROTATE_BODY = r'''  if (!loggingActive || !rawFile || rawFile.size() < RAW_ROTATE_BYTES) return;
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  emitStreamFileClose(nowUs, rawFileIndex, 0);
  rawFile.flush();
  rawFile.close();
  ++rawFileIndex;
  rawFilePersistedRecords = 0;
  rawFilePersistedBytes = 0;
  if (!openRawFile()) {
    ++sdLogDrops;
    writeEvent("ERROR", "RAW_ROTATION_FAILED", String(rawFileIndex));
    return;
  }
  emitStreamFileOpen(nowUs, rawFileIndex);'''


FINALIZE_HELPER = r'''
void finalizePendingStop() {
  if (!stopPending || !loggingActive) return;
  if (canQueue != nullptr && uxQueueMessagesWaiting(canQueue) != 0) return;
  serviceMetaQueue();
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  emitStreamCounters(true);
  emitHealthSnapshot(true);
  emitStorageHealth(true);
  emitStreamFileClose(nowUs, rawFileIndex, 1);
  uint8_t stopPayload[2] = {0, 0};
  appendMetaDirect(TVM1_STREAM_STOP, TVM1_STREAM_CAN, 0, nowUs, stopPayload, sizeof(stopPayload));
  if (stopPendingClean) {
    uint8_t closePayload[8] = {};
    tvm1PutLe16(closePayload, 0);
    closePayload[2] = 1;
    tvm1PutLe16(closePayload + 4, 1);
    appendMetaDirect(TVM1_SESSION_CLOSE, TVM1_STREAM_SESSION, 0, nowUs, closePayload, sizeof(closePayload));
  }
  flushLogFiles();
  closeSessionFiles();
  loggingActive = false;
  manifestClosed = stopPendingClean;
  stopPending = false;
  char status[28];
  snprintf(status, sizeof(status), "%s CLOSED%s", sessionName(), sessionHasCanTraffic ? "" : " EMPTY");
  setLoggerStatus(status);
  Serial.printf("# LOG STOPPED,%s,raw=%llu,meta_seq=%lu\n", sessionDir,
                (unsigned long long)rawSequence, (unsigned long)tvm1Writer.sequence());
}
'''


LOOP_BODY = r'''  uint64_t loopStartUs = (uint64_t)esp_timer_get_time();
  if (applicationMode == APP_WIFI_FILES) {
    serviceWifiFileMode();
    return;
  }

  // BLE processing may only set start/stop state here; a stop is finalized
  // after the current RAW queue has been serviced.
  serviceBleSync();

  CapturedFrame batch[128];
  size_t count = 0;
  while (count < 128 && canQueue != nullptr && xQueueReceive(canQueue, &batch[count], 0) == pdTRUE) ++count;
  if (canQueue != nullptr) {
    UBaseType_t depth = uxQueueMessagesWaiting(canQueue);
    if (depth > canQueueHighWater) canQueueHighWater = depth;
  }

  if (count) writeRawBatch(batch, count);
  for (size_t i = 0; i < count; ++i) processCapturedFrame(batch[i]);

  drainDiagnosticQueue();
  emitPeriodicHealth();
  serviceMetaQueue();
  finalizePendingStop();

  uint32_t nowMs = millis();
  if (nowMs - lastProfileEvaluationMs >= 250) {
    evaluateVehicleProfile();
    lastProfileEvaluationMs = nowMs;
  }
  serviceDiagnosticScheduler();
  serviceTwaiHealth();
  handleTouch();

  if (applicationMode == APP_LOGGER && nowMs - lastDisplayMs >= DISPLAY_PERIOD_MS && !captureUnderPressure()) {
    updateDisplay();
    lastDisplayMs = nowMs;
  }
  if (loggingActive && nowMs - lastFlushMs >= FILE_FLUSH_PERIOD_MS && !captureUnderPressure()) {
    flushLogFiles();
    lastFlushMs = nowMs;
  }

  uint64_t loopUs = (uint64_t)esp_timer_get_time() - loopStartUs;
  if (loopUs > mainLoopMaxUs) mainLoopMaxUs = loopUs;
  delay(1);'''


UPDATE_DISPLAY_BODY = r'''  uint64_t startedUs = (uint64_t)esp_timer_get_time();
  static char cache0[32] = {};
  static char cache1[32] = {};
  static char cache2[32] = {};
  static char cache3[32] = {};
  static char cache4[32] = {};
  static char cache5[32] = {};
  static char cache6[32] = {};
  static char cache7[32] = {};
  static bool lastLogging = false;
  static bool lastDiag = false;
  bool force = displayPageChanged;

  if (force) {
    drawStaticUI();
    memset(cache0, 0, sizeof(cache0)); memset(cache1, 0, sizeof(cache1));
    memset(cache2, 0, sizeof(cache2)); memset(cache3, 0, sizeof(cache3));
    memset(cache4, 0, sizeof(cache4)); memset(cache5, 0, sizeof(cache5));
    memset(cache6, 0, sizeof(cache6)); memset(cache7, 0, sizeof(cache7));
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    if (displayPage == 0) {
      tft.drawString("TOYOTA HYBRID CAN LOGGER v2.6", 10, 8, 2);
      tft.drawString("Vehicle:", 10, 35, 2); tft.drawString("Evidence:", 10, 58, 2);
      tft.drawString("Mode:", 10, 81, 2); tft.drawString("SD:", 10, 104, 2);
      tft.drawString("RX/TX/Qdrop:", 10, 127, 2); tft.drawString("SOC:", 10, 150, 2);
      tft.drawString("Pack:", 10, 173, 2); tft.drawString("RAW/META:", 10, 196, 2);
    } else {
      tft.drawString("LIVE TEMPERATURES / SPEED", 10, 8, 2);
      tft.drawString("Engine RPM:", 10, 35, 2); tft.drawString("Coolant F:", 10, 58, 2);
      tft.drawString("Intake F:", 10, 81, 2); tft.drawString("HV T1/T2/T3 F:", 10, 104, 2);
      tft.drawString("MG1/MG2 Inv F:", 10, 127, 2); tft.drawString("MG1/MG2 RPM:", 10, 150, 2);
      tft.drawString("Block min/max:", 10, 173, 2); tft.drawString("Queue HWM:", 10, 196, 2);
    }
  }

  char text[64];
  uint32_t nowMs = millis();
  if (displayPage == 0) {
    snprintf(text, sizeof(text), "%s (%u%%)", profileLabel(vehicleProfile), profileConfidence);
    drawDirtyField(175, 35, 295, 20, text, cache0, sizeof(cache0), force);
    drawDirtyField(175, 58, 295, 20, dataQualityLabel(), cache1, sizeof(cache1), force);
    snprintf(text, sizeof(text), "%s / %s", twaiNormalMode ? "NORMAL" : "LISTEN", diagnosticEnabled ? "DIAG" : "PASSIVE");
    drawDirtyField(175, 81, 295, 20, text, cache2, sizeof(cache2), force);
    snprintf(text, sizeof(text), "%s %s", sdReady ? "READY" : "NO SD", loggingActive ? "LOGGING" : "STOPPED");
    drawDirtyField(175, 104, 295, 20, text, cache3, sizeof(cache3), force);
    snprintf(text, sizeof(text), "%lu/%lu/%lu", (unsigned long)receivedFrameCount, (unsigned long)transmittedFrameCount, (unsigned long)canQueueDrops);
    drawDirtyField(175, 127, 295, 20, text, cache4, sizeof(cache4), force);
    bool socFresh = (live.ceValid && nowMs - live.ceMs < 2000) || (live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000);
    if (socFresh) snprintf(text, sizeof(text), "%.1f%%", live.socPct); else snprintf(text, sizeof(text), "---");
    drawDirtyField(175, 150, 295, 20, text, cache5, sizeof(cache5), force);
    bool electrical = (live.ceValid && nowMs - live.ceMs < 2000) || (live.c3Valid && nowMs - live.c3Ms < 2000) || (live.passiveElectricalValid && nowMs - live.passiveElectricalMs < 2000);
    if (electrical) snprintf(text, sizeof(text), "%.1fV %.1fA", live.packVolts, live.packAmps); else snprintf(text, sizeof(text), "---");
    drawDirtyField(175, 173, 295, 20, text, cache6, sizeof(cache6), force);
    snprintf(text, sizeof(text), "%llu / %lu", (unsigned long long)rawSequence, (unsigned long)tvm1Writer.sequence());
    drawDirtyField(175, 196, 295, 20, text, cache7, sizeof(cache7), force);
  } else {
    if (live.engineRPMValid && nowMs - live.engineRPMMs < 2000) snprintf(text, sizeof(text), "%ld", (long)live.engineRPM); else snprintf(text, sizeof(text), "---");
    drawDirtyField(175, 35, 295, 20, text, cache0, sizeof(cache0), force);
    if (live.coolantValid && nowMs - live.coolantMs < 2000) snprintf(text, sizeof(text), "%.1f", live.engineCoolantF); else snprintf(text, sizeof(text), "---");
    drawDirtyField(175, 58, 295, 20, text, cache1, sizeof(cache1), force);
    if (live.engineIntakeValid && nowMs - live.engineIntakeMs < 2000) snprintf(text, sizeof(text), "%.1f", live.engineIntakeAirF); else snprintf(text, sizeof(text), "---");
    drawDirtyField(175, 81, 295, 20, text, cache2, sizeof(cache2), force);
    snprintf(text, sizeof(text), "%.1f / %.1f / %.1f", live.hvTemp1F, live.hvTemp2F, live.hvTemp3F);
    drawDirtyField(175, 104, 295, 20, text, cache3, sizeof(cache3), force);
    snprintf(text, sizeof(text), "%.1f / %.1f", live.mg1InvF, live.mg2InvF);
    drawDirtyField(175, 127, 295, 20, text, cache4, sizeof(cache4), force);
    snprintf(text, sizeof(text), "%ld / %ld", (long)live.mg1RPM, (long)live.mg2RPM);
    drawDirtyField(175, 150, 295, 20, text, cache5, sizeof(cache5), force);
    snprintf(text, sizeof(text), "%.2f / %.2f", live.blockMinV, live.blockMaxV);
    drawDirtyField(175, 173, 295, 20, text, cache6, sizeof(cache6), force);
    snprintf(text, sizeof(text), "%lu", (unsigned long)canQueueHighWater);
    drawDirtyField(175, 196, 295, 20, text, cache7, sizeof(cache7), force);
  }
  if (force || lastLogging != loggingActive || lastDiag != diagnosticEnabled) drawButtons();
  lastLogging = loggingActive; lastDiag = diagnosticEnabled;
  displayPageChanged = false;
  ++tftRenderCount;
  uint64_t elapsed = (uint64_t)esp_timer_get_time() - startedUs;
  if (elapsed > tftRenderMaxUs) tftRenderMaxUs = elapsed;'''


def _transform_source(source: str) -> str:
    source = source.replace("v2.5.0-rc.2", "v2.6.0-dev").replace("v2.5 RC2", "v2.6 DEV")
    source = _replace_once(source, '#include "driver/twai.h"', '#include "driver/twai.h"\n#include "TVM1Meta.h"', "TVM1 include")

    board_start = source.find("// Touch-controller flag/orientation differs")
    board_end = source.find("#endif", board_start)
    if board_start < 0 or board_end < 0:
        raise ValueError("board profile block not found")
    board_end += len("#endif")
    source = source[:board_start] + BOARD_BLOCK + source[board_end:]
    source = source.replace("constexpr uint8_t SD_MAX_OPEN_FILES = 10;", "constexpr uint8_t SD_MAX_OPEN_FILES = 5;")

    old_files = "File rawFile;\nFile decodedFile;\nFile diagnosticFile;\nFile eventFile;\nFile syncFile;\nFile externalDiagnosticFile;"
    source = _replace_once(source, old_files, META_GLOBALS, "session file globals")

    # Put helpers after the existing logger-status utility so all global state and
    # the nowMicros64 declaration/definition are already visible to later code.
    marker = "bool sessionTrafficRecent() {"
    if marker not in source:
        raise ValueError("helper insertion marker missing")
    source = source.replace(marker, HELPERS + "\n\n" + marker, 1)

    source = _replace_function(source, "void closeSessionFiles()", r'''  if (rawFile) rawFile.close();
  if (metaFile) metaFile.close();
  tvm1Writer.detach();''')

    source = _replace_function(source, "void cleanupFailedSession()", r'''  closeSessionFiles();
  if (sessionDir[0] == 0) return;
  char path[72];
  snprintf(path, sizeof(path), "%s/SESSION.META", sessionDir);
  if (SD.exists(path)) SD.remove(path);
  for (uint16_t i = 0; i <= rawFileIndex; ++i) {
    snprintf(path, sizeof(path), "%s/RAW_%03u.TCB", sessionDir, i);
    if (SD.exists(path)) SD.remove(path);
  }
  SD.rmdir(sessionDir);
  sessionDir[0] = '\0';''')

    source = _replace_function(source, "bool startLogging()", START_LOGGING_BODY)
    source = _replace_function(source, "void stopLogging(bool closedCleanly)", r'''  if (!loggingActive || stopPending) return;
  stopPending = true;
  stopPendingClean = closedCleanly;
  stopRequestUs = (uint64_t)esp_timer_get_time();
  writeEvent("INFO", "LOGGING_STOP_REQUESTED", String("requested_us=") + String((unsigned long long)stopRequestUs));
  setLoggerStatus("STOP PENDING");''')

    source = _replace_function(source, "void rotateRawFileIfNeeded()", ROTATE_BODY)
    source = _replace_function(source, "void writeRawBatch(const CapturedFrame *frames, size_t count)", RAW_BATCH_BODY)
    source = _replace_function(source, "void writeDecodedSample()", "  // Live decoding remains in RAM; archival decoded rows are regenerated offline.")

    source = _replace_function(source, "void writeDiagnosticRecord(const char *status, uint64_t completeTimeUs)", r'''  ++diagnosticSequence;
  if (!loggingActive) return;
  uint16_t state = 2;
  if (status && strcmp(status, "TIMEOUT") == 0) state = 3;
  else if (status && strstr(status, "NEGATIVE") != nullptr) state = 4;
  else if (status && strcmp(status, "OK") != 0) state = 5;
  emitDiagnosticState(state, 0, diag.responseId, diag.receivedLength);
  (void)completeTimeUs;''')

    source = _replace_function(source, "void writeExternalDiagnosticFrame(const CapturedFrame &frame, const char *classification)", r'''  // External request/response bytes are already authoritative in TCB1 RAW.
  (void)frame;
  (void)classification;''')

    source = _replace_function(source, "void writeEvent(const char *severity, const char *eventName, const String &details)", r'''  uint64_t eventUs = (uint64_t)esp_timer_get_time();
  Serial.printf("# EVENT,%llu,%s,%s,%s\n", (unsigned long long)eventUs,
                severity ? severity : "INFO", eventName ? eventName : "OTHER", details.c_str());
  if (!loggingActive) return;
  uint8_t payload[4] = {};
  tvm1PutLe16(payload, eventCodeForName(eventName));
  payload[2] = eventSeverityCode(severity);
  payload[3] = 0;
  enqueueMetaRecord(TVM1_EVENT, TVM1_STREAM_SESSION, 0, eventUs, payload, sizeof(payload));''')

    for sig in ("void writeReadme()", "void writeSignalsDictionary()", "void writeManifest(bool closedCleanly)", "void writeCheckpoint(bool closedCleanly)"):
        source = _replace_function(source, sig, "  // Reconstructed by the validated offline TVM1 preprocessor.\n  (void)0;")

    source = _replace_function(source, "void writeSyncRecord(const BleSyncRecord &record, const char *source)", r'''  if (!loggingActive) return;
  uint8_t payload[12] = {};
  tvm1PutLe16(payload, record.sequence);
  payload[2] = (source && strcmp(source, "BLE_PRESTART") == 0) ? 1 : 0;
  payload[3] = 0;
  tvm1PutLe64(payload + 4, record.sendUs);
  enqueueMetaRecord(TVM1_CLOCK_SYNC, TVM1_STREAM_SESSION, 0, record.receiveUs, payload, sizeof(payload));''')

    source = _replace_function(source, "void flushLogFiles()", r'''  if (!loggingActive) return;
  if (rawFile) {
    uint64_t started = (uint64_t)esp_timer_get_time(); rawFile.flush();
    uint64_t elapsed = (uint64_t)esp_timer_get_time() - started;
    ++rawFlushCount; if (elapsed > rawFlushMaxUs) rawFlushMaxUs = elapsed;
  }
  if (metaFile) {
    uint64_t started = (uint64_t)esp_timer_get_time(); tvm1Writer.flush();
    uint64_t elapsed = (uint64_t)esp_timer_get_time() - started;
    ++metaFlushCount; if (elapsed > metaFlushMaxUs) metaFlushMaxUs = elapsed;
  }''')

    # BLE commands preserve protocol framing but no longer close files in the BLE callback path.
    source = _replace_function(source, "void processBleCommand(const BleCommand &command)", r'''  ++bleCommandCount;
  if (command.opcode == 1) {
    if (diagnosticEnabled || twaiNormalMode)
      setDiagnosticCapture(false, "BLE synchronized capture requested");
    startPending = true;
    startRequestUs = command.receiveUs;
    startCommandSequence = command.sequence;
    if (!loggingActive && sdReady) startLogging();
    uint64_t eventUs = (uint64_t)esp_timer_get_time();
    if (loggingActive) {
      writeEvent("INFO", "BLE_CAPTURE_START", "sequence=" + String(command.sequence));
      sendBleControlResponse(command, 0, eventUs);
    } else sendBleControlResponse(command, sdReady ? 3 : 2, eventUs);
    return;
  }
  if (command.opcode == 2) {
    uint64_t eventUs = (uint64_t)esp_timer_get_time();
    if (loggingActive && !stopPending) {
      stopPending = true;
      stopPendingClean = true;
      stopRequestUs = command.receiveUs;
      stopCommandSequence = command.sequence;
      writeEvent("INFO", "BLE_CAPTURE_STOP", "sequence=" + String(command.sequence));
      setLoggerStatus("STOP PENDING");
      sendBleControlResponse(command, 0, eventUs);
    } else sendBleControlResponse(command, loggingActive ? 0 : 3, eventUs);
    return;
  }
  if (command.opcode == 3) {
    uint64_t eventUs = (uint64_t)esp_timer_get_time();
    if (loggingActive) {
      uint8_t payload[8] = {};
      tvm1PutLe16(payload, command.sequence);
      tvm1PutLe16(payload + 2, 0);
      tvm1PutLe32(payload + 4, command.marker);
      enqueueMetaRecord(TVM1_USER_MARKER, TVM1_STREAM_SESSION, 0, command.receiveUs, payload, sizeof(payload));
      writeEvent("INFO", "BLE_MARKER", "marker=" + String(command.marker));
      sendBleControlResponse(command, 0, eventUs);
    } else sendBleControlResponse(command, 3, eventUs);
    return;
  }
  sendBleControlResponse(command, 1, (uint64_t)esp_timer_get_time());''')

    source = _prepend_function(source, "bool transmitCAN(", "  if (externalTesterInterlockActive()) {\n    writeEvent(\"WARN\", \"TWAI_TRANSMIT_BLOCKED\", \"external tester interlock\");\n    return false;\n  }")
    source = _prepend_function(source, "void serviceDiagnosticScheduler()", "  if (externalTesterInterlockActive()) {\n    if (diag.active) completeDiagnostic(\"EXTERNAL_INTERLOCK\");\n    return;\n  }")

    # Inject finalizer before loop and replace loop with RAW-first order.
    loop_marker = "void loop() {"
    if loop_marker not in source:
        raise ValueError("loop marker missing")
    source = source.replace(loop_marker, FINALIZE_HELPER + "\n\n" + loop_marker, 1)
    source = _replace_function(source, "void loop()", LOOP_BODY)

    source = _replace_function(source, "void updateDisplay()", UPDATE_DISPLAY_BODY)
    source = source.replace("displayPage ^= 1;\n    updateDisplay();", "displayPage ^= 1;\n    displayPageChanged = true;\n    updateDisplay();", 1)

    # E32R35T gets first-boot calibration rather than guessed legacy constants.
    source = source.replace("tft.setTouch(touchCalibration);\n  Serial.printf(\"# CYD BOARD,%s,touch_flags=%u,rotation=1\\n\",", "configureTouchForBoard();\n  Serial.printf(\"# CYD BOARD,%s,touch_flags=%u,rotation=1\\n\",", 1)

    # Native TVM1 clean-state replaces marker semantics while legacy folders retain marker support.
    old_list = '''        String marker = path + "/SESSION.OPEN";\n        if (!first) client.print(',');\n        client.printf("{\\\"name\\\":\\\"%s\\\",\\\"files\\\":%lu,\\\"bytes\\\":%llu,\\\"closed\\\":%s}",\n                      name.c_str(), (unsigned long)files, (unsigned long long)bytes,\n                      SD.exists(marker.c_str()) ? "false" : "true");'''
    new_list = '''        bool closed = isSessionClosedForWifi(path);\n        if (!first) client.print(',');\n        client.printf("{\\\"name\\\":\\\"%s\\\",\\\"files\\\":%lu,\\\"bytes\\\":%llu,\\\"closed\\\":%s}",\n                      name.c_str(), (unsigned long)files, (unsigned long long)bytes,\n                      closed ? "true" : "false");'''
    if old_list not in source:
        raise ValueError("Wi-Fi session-list legacy marker block not found")
    source = source.replace(old_list, new_list, 1)

    old_delete = '''  String openMarker = sessionPath + "/SESSION.OPEN";\n  if (SD.exists(openMarker.c_str())) {\n    wifiServer->send(409, "application/json", "{\\\"message\\\":\\\"Unclean/open sessions cannot be deleted\\\"}");\n    return;\n  }'''
    new_delete = '''  if (!isSessionClosedForWifi(sessionPath)) {\n    wifiServer->send(409, "application/json", "{\\\"message\\\":\\\"Unclean/open sessions cannot be deleted\\\"}");\n    return;\n  }'''
    if old_delete not in source:
        raise ValueError("Wi-Fi delete legacy marker block not found")
    source = source.replace(old_delete, new_delete, 1)

    forbidden = [
        "File decodedFile;", "File diagnosticFile;", "File eventFile;", "File syncFile;",
        "File externalDiagnosticFile;", "DECODED.CSV", "DIAGNOSTICS.CSV",
        "EXTERNAL_DIAGNOSTICS.CSV", "EVENTS.CSV", "SYNC.CSV", "SIGNALS.CSV",
        "README.TXT", "MANIFEST.JSON", "CHECKPOINT.JSON", "PLOT.CSV", "E32N35T", "TCM1",
    ]
    leftovers = [token for token in forbidden if token in source]
    if leftovers:
        raise ValueError("forbidden v2.6 tokens remain: " + ", ".join(leftovers))
    return source


def generate(rc2_dir: Path | str, out_root: Path | str) -> Path:
    rc2_dir = Path(rc2_dir)
    out_root = Path(out_root)
    if not (rc2_dir / OLD_INO).exists():
        raise FileNotFoundError(rc2_dir / OLD_INO)
    out_dir = out_root / OUT_DIR_NAME
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(rc2_dir, out_dir)
    old_ino = out_dir / OLD_INO
    source = old_ino.read_text(encoding="utf-8")
    source = _transform_source(source)
    new_ino = out_dir / NEW_INO
    new_ino.write_text(source, encoding="utf-8", newline="\n")
    old_ino.unlink()
    (out_dir / "TVM1Meta.h").write_text(TVM1_META_H, encoding="utf-8", newline="\n")

    readme = (out_dir / "README.md").read_text(encoding="utf-8") if (out_dir / "README.md").exists() else ""
    readme = readme.replace("v2.5.0-rc.2", "v2.6.0-dev").replace("v2.5.0", "v2.6.0")
    readme += """\n\n## v2.6 simplified native capture\n\nNormal capture writes only `RAW_nnn.TCB` plus canonical `SESSION.META` (TVM1).\nEvidence Builder compatibility products are regenerated by the validated Toyota Vehicle Bus Session Preprocessor.\nThe default build target is Dorhea. For E32R35T select `CYD_BOARD_PROFILE_SELECT=CYD_BOARD_PROFILE_E32R35T`; first boot runs TFT_eSPI touch calibration and stores it in NVS instead of guessing legacy calibration constants.\nRC2 remains the vehicle rollback until physical Dorhea and E32R35T validation is complete.\n"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    (out_dir / "VERSION.txt").write_text("2.6.0-dev\nTVM1 RAW+META simplified capture\nRC2 baseline bbc7421da2bfc684324123b3232895cdcfd6c23d\n", encoding="utf-8", newline="\n")
    return out_dir


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("rc2_dir", type=Path)
    parser.add_argument("out_root", type=Path)
    args = parser.parse_args()
    print(generate(args.rc2_dir, args.out_root))
