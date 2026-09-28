from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

BASE_PATH = Path(__file__).with_name("build_v2_6_0_firmware.py")
_spec = importlib.util.spec_from_file_location("v260_base", BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_base)

BASE_OUT_DIR = "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0"
BASE_INO = "Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino"
OUT_DIR_NAME = "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0"
NEW_INO = "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0.ino"


def _find_function(text: str, signature: str) -> tuple[int, int, int]:
    search_from = 0
    while True:
        start = text.find(signature, search_from)
        if start < 0:
            raise ValueError(f"function definition not found: {signature}")
        brace = text.find("{", start)
        semicolon = text.find(";", start)
        if brace < 0:
            raise ValueError(f"opening brace not found: {signature}")
        if 0 <= semicolon < brace:
            search_from = semicolon + 1
            continue
        break

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
    start, brace, end = _find_function(text, signature)
    prefix = text[start:brace]
    return text[:start] + prefix + "{\n" + body.rstrip() + "\n}" + text[end:]


def _append_to_function(text: str, signature: str, code: str) -> str:
    _start, _brace, end = _find_function(text, signature)
    return text[: end - 1] + "\n" + code.rstrip() + "\n" + text[end - 1 :]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


BTH1_RAW_H = r'''#pragma once

#include <Arduino.h>
#include <FS.h>

static constexpr char BTH1_MAGIC[4] = {'B', 'T', 'H', '1'};
static constexpr uint8_t BTH1_MAJOR = 1;
static constexpr uint8_t BTH1_MINOR = 0;
static constexpr uint16_t BTH1_HEADER_SIZE = 32;
static constexpr uint16_t BTH1_RECORD_SYNC = 0xB7B1;
static constexpr uint16_t BTH1_MAX_PAYLOAD = 64;
static constexpr uint32_t BTH1_CRC32_POLYNOMIAL = 0xEDB88320UL;

static constexpr uint16_t BTH1_STATUS_PARITY = 1U << 0;
static constexpr uint16_t BTH1_STATUS_FRAME = 1U << 1;
static constexpr uint16_t BTH1_STATUS_BREAK = 1U << 2;
static constexpr uint16_t BTH1_STATUS_FIFO_OVERFLOW = 1U << 3;
static constexpr uint16_t BTH1_STATUS_BUFFER_FULL = 1U << 4;

inline void bth1PutLe16(uint8_t *dst, uint16_t value) {
  dst[0] = (uint8_t)(value & 0xFFU);
  dst[1] = (uint8_t)((value >> 8) & 0xFFU);
}

inline void bth1PutLe32(uint8_t *dst, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) dst[i] = (uint8_t)((value >> (8U * i)) & 0xFFU);
}

inline void bth1PutLe64(uint8_t *dst, uint64_t value) {
  for (uint8_t i = 0; i < 8; ++i) dst[i] = (uint8_t)((value >> (8U * i)) & 0xFFU);
}

inline uint32_t bth1Crc32Update(uint32_t crc, const uint8_t *data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (BTH1_CRC32_POLYNOMIAL & (uint32_t)-(int32_t)(crc & 1U));
  }
  return crc;
}

inline uint32_t bth1Crc32(const uint8_t *data, size_t length) {
  return bth1Crc32Update(0xFFFFFFFFUL, data, length) ^ 0xFFFFFFFFUL;
}

class Bth1Writer {
 public:
  Bth1Writer() : file_(nullptr) {}

  bool begin(File &file, uint32_t baud, uint8_t dataBits, uint8_t parity,
             uint8_t stopBitsX2, bool rxInverted, uint64_t startUs) {
    file_ = &file;
    uint8_t header[BTH1_HEADER_SIZE] = {};
    memcpy(header, BTH1_MAGIC, sizeof(BTH1_MAGIC));
    header[4] = BTH1_MAJOR;
    header[5] = BTH1_MINOR;
    bth1PutLe16(header + 6, BTH1_HEADER_SIZE);
    bth1PutLe32(header + 8, baud);
    header[12] = dataBits;
    header[13] = parity;
    header[14] = stopBitsX2;
    header[15] = rxInverted ? 1U : 0U;
    bth1PutLe64(header + 16, startUs);
    bth1PutLe32(header + 24, bth1Crc32(header, 24));
    bth1PutLe32(header + 28, 0);
    return file_->write(header, sizeof(header)) == sizeof(header);
  }

  bool append(uint32_t sequence, uint64_t observedTimeUs, uint16_t status,
              const uint8_t *payload, uint16_t payloadLen) {
    if (file_ == nullptr || !(*file_) || payload == nullptr || payloadLen == 0 ||
        payloadLen > BTH1_MAX_PAYLOAD) return false;
    uint8_t envelope[20] = {};
    const uint16_t total = (uint16_t)(24U + payloadLen);
    bth1PutLe16(envelope + 0, BTH1_RECORD_SYNC);
    bth1PutLe16(envelope + 2, total);
    bth1PutLe32(envelope + 4, sequence);
    bth1PutLe64(envelope + 8, observedTimeUs);
    bth1PutLe16(envelope + 16, status);
    bth1PutLe16(envelope + 18, payloadLen);
    uint32_t crc = bth1Crc32Update(0xFFFFFFFFUL, envelope, sizeof(envelope));
    crc = bth1Crc32Update(crc, payload, payloadLen) ^ 0xFFFFFFFFUL;
    uint8_t crcBytes[4];
    bth1PutLe32(crcBytes, crc);
    if (file_->write(envelope, sizeof(envelope)) != sizeof(envelope)) return false;
    if (file_->write(payload, payloadLen) != payloadLen) return false;
    return file_->write(crcBytes, sizeof(crcBytes)) == sizeof(crcBytes);
  }

  bool flush() {
    if (file_ == nullptr || !(*file_)) return false;
    file_->flush();
    return true;
  }

  void detach() { file_ = nullptr; }

 private:
  File *file_;
};
'''


BTH_CONFIG = r'''#define BTH_RX_PIN GPIO_NUM_35
#ifndef ENABLE_BTH_CAPTURE
#define ENABLE_BTH_CAPTURE 0
#endif
constexpr bool BTH_CAPTURE_ENABLED = ENABLE_BTH_CAPTURE != 0;
constexpr uart_port_t BTH_UART_PORT = UART_NUM_2;
constexpr uint32_t BTH_BAUD = 19200;
constexpr bool BTH_RX_INVERT = false;
constexpr uint16_t CAN_BATCH_LENGTH = 128;
constexpr uint8_t BTH_QUEUE_LENGTH = 32;
constexpr uint16_t BTH_UART_RX_BUFFER_BYTES = 1024;
constexpr uint8_t BTH_UART_EVENT_QUEUE_LENGTH = 16;
constexpr uint32_t BTH_ROTATE_BYTES = 25UL * 1024UL * 1024UL;
constexpr uint8_t TVM1_STREAM_TYPE_BTH = 2;
constexpr uint8_t TVM1_RAW_FORMAT_BTH1 = 2;'''


BTH_GLOBALS = r'''
struct BthChunk {
  uint64_t observedTimeUs;
  uint16_t status;
  uint16_t length;
  uint8_t data[BTH1_MAX_PAYLOAD];
};

QueueHandle_t bthQueue = nullptr;
QueueHandle_t bthUartEventQueue = nullptr;
TaskHandle_t bthRxTaskHandle = nullptr;
File bthFile;
Bth1Writer bth1Writer;
volatile uint64_t bthRxBytes = 0;
uint64_t bthPersistedBytes = 0;
volatile uint32_t bthRxChunks = 0;
uint32_t bthPersistedChunks = 0;
volatile uint32_t bthQueueDrops = 0;
volatile uint32_t bthQueueHighWater = 0;
volatile uint32_t bthFifoOverflow = 0;
volatile uint32_t bthBufferFull = 0;
volatile uint32_t bthParityErrors = 0;
volatile uint32_t bthFrameErrors = 0;
volatile uint32_t bthBreakErrors = 0;
uint32_t bthShortWriteCount = 0;
uint64_t bthWriteCount = 0;
uint64_t bthWriteTotalUs = 0;
uint64_t bthWriteMaxUs = 0;
uint64_t bthFlushCount = 0;
uint64_t bthFlushMaxUs = 0;
uint16_t bthFileIndex = 0;
uint32_t bthChunkSequence = 0;
volatile uint16_t bthPendingStatus = 0;
volatile bool bthSessionAccepting = false;'''


BTH_HELPERS = r'''
static bool emitBthStreamRegister(uint64_t timeUs) {
  if (!BTH_CAPTURE_ENABLED) return true;
  uint8_t payload[16] = {};
  payload[0] = TVM1_STREAM_TYPE_BTH;
  payload[1] = TVM1_RAW_FORMAT_BTH1;
  payload[2] = 1;
  payload[3] = BTH_RX_INVERT ? 1 : 0;
  tvm1PutLe32(payload + 4, BTH_BAUD);
  payload[8] = 8;
  payload[9] = 1;
  payload[10] = 2;
  payload[11] = (uint8_t)BTH_RX_PIN;
  return appendMetaDirect(TVM1_STREAM_REGISTER, TVM1_STREAM_BTH, 0, timeUs, payload, sizeof(payload));
}

static bool emitBthFileOpen(uint64_t timeUs, uint16_t index) {
  if (!BTH_CAPTURE_ENABLED) return true;
  char basename[20];
  snprintf(basename, sizeof(basename), "BTH_%03u.BTH", index);
  uint8_t payload[32] = {};
  tvm1PutLe16(payload, index);
  uint16_t length = appendTvm1String(payload, 2, sizeof(payload), basename);
  return length != 0xFFFFU && appendMetaDirect(TVM1_STREAM_FILE_OPEN, TVM1_STREAM_BTH, 0, timeUs, payload, length);
}

static bool emitBthFileClose(uint64_t timeUs, uint16_t index, uint16_t reason) {
  if (!BTH_CAPTURE_ENABLED) return true;
  uint8_t payload[20] = {};
  tvm1PutLe16(payload + 0, index);
  tvm1PutLe16(payload + 2, reason);
  tvm1PutLe64(payload + 4, bthPersistedChunks);
  tvm1PutLe64(payload + 12, bthPersistedBytes);
  return appendMetaDirect(TVM1_STREAM_FILE_CLOSE, TVM1_STREAM_BTH, 0, timeUs, payload, sizeof(payload));
}

static void emitBthCounters(uint64_t timeUs) {
  if (!BTH_CAPTURE_ENABLED || !loggingActive) return;
  uint8_t payload[64] = {};
  tvm1PutLe64(payload + 0, bthRxBytes);
  tvm1PutLe64(payload + 8, bthPersistedBytes);
  tvm1PutLe32(payload + 16, bthRxChunks);
  tvm1PutLe32(payload + 20, bthPersistedChunks);
  tvm1PutLe32(payload + 24, bthQueueDrops);
  tvm1PutLe32(payload + 28, bthQueueHighWater);
  tvm1PutLe32(payload + 32, bthFifoOverflow);
  tvm1PutLe32(payload + 36, bthBufferFull);
  tvm1PutLe32(payload + 40, bthParityErrors);
  tvm1PutLe32(payload + 44, bthFrameErrors);
  tvm1PutLe32(payload + 48, bthBreakErrors);
  tvm1PutLe32(payload + 52, bthShortWriteCount);
  tvm1PutLe32(payload + 56, (uint32_t)bthFileIndex);
  tvm1PutLe32(payload + 60, (uint32_t)bthChunkSequence);
  enqueueMetaRecord(TVM1_STREAM_COUNTERS, TVM1_STREAM_BTH, 0, timeUs, payload, sizeof(payload));
}

void bthRxTask(void *parameter) {
  (void)parameter;
  uart_event_t event;
  uint8_t scratch[BTH1_MAX_PAYLOAD];
  for (;;) {
    if (bthUartEventQueue == nullptr || xQueueReceive(bthUartEventQueue, &event, portMAX_DELAY) != pdTRUE) continue;
    uint64_t observedUs = (uint64_t)esp_timer_get_time();
    if (event.type == UART_DATA) {
      size_t remaining = (size_t)event.size;
      while (remaining) {
        size_t request = remaining > BTH1_MAX_PAYLOAD ? BTH1_MAX_PAYLOAD : remaining;
        int got = uart_read_bytes(BTH_UART_PORT, scratch, request, 0);
        if (got <= 0) break;
        remaining -= (size_t)got;
        if (!loggingActive || !bthSessionAccepting || bthQueue == nullptr) continue;
        BthChunk chunk = {};
        chunk.observedTimeUs = observedUs;
        chunk.status = bthPendingStatus;
        bthPendingStatus = 0;
        chunk.length = (uint16_t)got;
        memcpy(chunk.data, scratch, (size_t)got);
        bthRxBytes += (uint64_t)got;
        ++bthRxChunks;
        if (xQueueSend(bthQueue, &chunk, 0) != pdTRUE) {
          ++bthQueueDrops;
        } else {
          UBaseType_t depth = uxQueueMessagesWaiting(bthQueue);
          if (depth > bthQueueHighWater) bthQueueHighWater = depth;
        }
      }
    } else if (event.type == UART_FIFO_OVF) {
      ++bthFifoOverflow;
      bthPendingStatus |= BTH1_STATUS_FIFO_OVERFLOW;
      uart_flush_input(BTH_UART_PORT);
      if (bthUartEventQueue) xQueueReset(bthUartEventQueue);
    } else if (event.type == UART_BUFFER_FULL) {
      ++bthBufferFull;
      bthPendingStatus |= BTH1_STATUS_BUFFER_FULL;
      uart_flush_input(BTH_UART_PORT);
      if (bthUartEventQueue) xQueueReset(bthUartEventQueue);
    } else if (event.type == UART_PARITY_ERR) {
      ++bthParityErrors;
      bthPendingStatus |= BTH1_STATUS_PARITY;
    } else if (event.type == UART_FRAME_ERR) {
      ++bthFrameErrors;
      bthPendingStatus |= BTH1_STATUS_FRAME;
    } else if (event.type == UART_BREAK) {
      ++bthBreakErrors;
      bthPendingStatus |= BTH1_STATUS_BREAK;
    }
  }
}

bool initializeBthRuntime() {
  if (!BTH_CAPTURE_ENABLED) return true;
  if (bthQueue != nullptr) return true;
  bthQueue = xQueueCreate(BTH_QUEUE_LENGTH, sizeof(BthChunk));
  if (bthQueue == nullptr) return false;
  uart_config_t config = {};
  config.baud_rate = (int)BTH_BAUD;
  config.data_bits = UART_DATA_8_BITS;
  config.parity = UART_PARITY_ODD;
  config.stop_bits = UART_STOP_BITS_1;
  config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  config.rx_flow_ctrl_thresh = 0;
  config.source_clk = UART_SCLK_APB;
  if (uart_param_config(BTH_UART_PORT, &config) != ESP_OK) return false;
  if (uart_set_pin(BTH_UART_PORT, UART_PIN_NO_CHANGE, BTH_RX_PIN,
                   UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) != ESP_OK) return false;
  if (uart_driver_install(BTH_UART_PORT, BTH_UART_RX_BUFFER_BYTES, 0,
                          BTH_UART_EVENT_QUEUE_LENGTH, &bthUartEventQueue, 0) != ESP_OK) return false;
  if (uart_set_line_inverse(BTH_UART_PORT, BTH_RX_INVERT ? UART_SIGNAL_RXD_INV : 0) != ESP_OK) return false;
  if (xTaskCreatePinnedToCore(bthRxTask, "bthRx", 3072, nullptr,
                              configMAX_PRIORITIES - 4, &bthRxTaskHandle, 1) != pdPASS) return false;
  return true;
}

void shutdownBthRuntime() {
  bthSessionAccepting = false;
  if (bthRxTaskHandle != nullptr) {
    vTaskDelete(bthRxTaskHandle);
    bthRxTaskHandle = nullptr;
  }
  if (BTH_CAPTURE_ENABLED) uart_driver_delete(BTH_UART_PORT);
  bthUartEventQueue = nullptr;
  if (bthQueue != nullptr) {
    vQueueDelete(bthQueue);
    bthQueue = nullptr;
  }
}

static bool openBthFile(uint64_t startUs) {
  if (!BTH_CAPTURE_ENABLED) return true;
  char path[64];
  snprintf(path, sizeof(path), "%s/BTH_%03u.BTH", sessionDir, bthFileIndex);
  bthFile = SD.open(path, FILE_WRITE);
  if (!bthFile) return false;
  if (!bth1Writer.begin(bthFile, BTH_BAUD, 8, 1, 2, BTH_RX_INVERT, startUs)) {
    bthFile.close();
    bth1Writer.detach();
    return false;
  }
  return true;
}

static bool startBthSession(uint64_t startUs) {
  if (!BTH_CAPTURE_ENABLED) return true;
  if (!initializeBthRuntime()) return false;
  if (bthQueue) xQueueReset(bthQueue);
  bthRxBytes = 0;
  bthPersistedBytes = 0;
  bthRxChunks = 0;
  bthPersistedChunks = 0;
  bthQueueDrops = 0;
  bthQueueHighWater = 0;
  bthFifoOverflow = 0;
  bthBufferFull = 0;
  bthParityErrors = 0;
  bthFrameErrors = 0;
  bthBreakErrors = 0;
  bthShortWriteCount = 0;
  bthWriteCount = bthWriteTotalUs = bthWriteMaxUs = 0;
  bthFlushCount = bthFlushMaxUs = 0;
  bthFileIndex = 0;
  bthChunkSequence = 0;
  bthPendingStatus = 0;
  if (!openBthFile(startUs)) return false;
  if (!emitBthStreamRegister(startUs) ||
      !appendMetaDirect(TVM1_STREAM_START, TVM1_STREAM_BTH, 0, startUs) ||
      !emitBthFileOpen(startUs, bthFileIndex)) return false;
  bthSessionAccepting = true;
  return true;
}

static void rotateBthFileIfNeeded() {
  if (!BTH_CAPTURE_ENABLED || !loggingActive || !bthFile || bthFile.size() < BTH_ROTATE_BYTES) return;
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  emitBthFileClose(nowUs, bthFileIndex, 0);
  bthFile.flush();
  bthFile.close();
  ++bthFileIndex;
  if (!openBthFile(nowUs)) {
    ++bthShortWriteCount;
    bthSessionAccepting = false;
    writeEvent("ERROR", "BTH_ROTATION_FAILED", "native BTH file open failed");
    return;
  }
  emitBthFileOpen(nowUs, bthFileIndex);
}

void serviceBthPersistence() {
  if (!BTH_CAPTURE_ENABLED || !loggingActive || !bthFile || bthQueue == nullptr) return;
  BthChunk chunk = {};
  uint8_t serviced = 0;
  while (serviced < 8 && xQueueReceive(bthQueue, &chunk, 0) == pdTRUE) {
    uint64_t startedUs = (uint64_t)esp_timer_get_time();
    bool ok = bth1Writer.append(++bthChunkSequence, chunk.observedTimeUs,
                                chunk.status, chunk.data, chunk.length);
    uint64_t elapsedUs = (uint64_t)esp_timer_get_time() - startedUs;
    ++bthWriteCount;
    bthWriteTotalUs += elapsedUs;
    if (elapsedUs > bthWriteMaxUs) bthWriteMaxUs = elapsedUs;
    if (!ok) {
      ++bthShortWriteCount;
    } else {
      bthPersistedBytes += chunk.length;
      ++bthPersistedChunks;
    }
    ++serviced;
  }
  rotateBthFileIfNeeded();
}
'''


DRAW_BUTTONS_BODY = r'''  uint16_t logColor = !loggingActive ? TFT_DARKGREY :
                      (sessionTrafficRecent() ? TFT_GREEN : TFT_ORANGE);
  bool externalRecent = externalTesterInterlockActive();
  bool diagnosticAvailable = loggingActive && vehicleProfile == PROFILE_PRIUS_GEN2 &&
                             profileConfidence >= 80 && !externalRecent;
  uint16_t diagColor = diagnosticEnabled ? TFT_RED : (diagnosticAvailable ? TFT_BLUE : TFT_DARKGREY);
  uint16_t wifiColor = sdReady && !loggingActive ? TFT_DARKCYAN : TFT_DARKGREY;
  tft.fillRoundRect(CYD_WIFI_BTN_X, CYD_WIFI_BTN_Y, CYD_WIFI_BTN_W, CYD_WIFI_BTN_H, 6, wifiColor);
  tft.drawRoundRect(CYD_WIFI_BTN_X, CYD_WIFI_BTN_Y, CYD_WIFI_BTN_W, CYD_WIFI_BTN_H, 6, TFT_WHITE);
  tft.fillRoundRect(CYD_LOG_BTN_X, CYD_LOG_BTN_Y, CYD_LOG_BTN_W, CYD_LOG_BTN_H, 6, logColor);
  tft.drawRoundRect(CYD_LOG_BTN_X, CYD_LOG_BTN_Y, CYD_LOG_BTN_W, CYD_LOG_BTN_H, 6, TFT_WHITE);
  tft.fillRoundRect(CYD_DIAG_BTN_X, CYD_DIAG_BTN_Y, CYD_DIAG_BTN_W, CYD_DIAG_BTN_H, 6, diagColor);
  tft.drawRoundRect(CYD_DIAG_BTN_X, CYD_DIAG_BTN_Y, CYD_DIAG_BTN_W, CYD_DIAG_BTN_H, 6, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE);
  tft.drawString("WIFI FILES", CYD_WIFI_BTN_X + CYD_WIFI_BTN_W / 2, 283, 2);
  tft.drawString(loggingActive ? "STOP LOG" : "START LOG", CYD_LOG_BTN_X + CYD_LOG_BTN_W / 2, 283, 2);
  tft.drawString(diagnosticEnabled ? "DIAG ON" : (diagnosticAvailable ? "DIAG OFF" : "DIAG N/A"), CYD_DIAG_BTN_X + CYD_DIAG_BTN_W / 2, 283, 2);
  tft.setTextDatum(TL_DATUM);'''


UPDATE_DISPLAY_BODY = r'''  uint64_t startedUs = (uint64_t)esp_timer_get_time();
  static char cache[8][40] = {};
  static uint32_t priorMs = 0;
  static uint32_t priorCanRx = 0;
  static uint64_t priorRaw = 0;
  static uint64_t priorBth = 0;
  static float canRxRate = 0.0f;
  static float canRawRate = 0.0f;
  static float bthByteRate = 0.0f;
  bool force = displayPageChanged;
  uint32_t nowMs = millis();
  uint32_t deltaMs = nowMs - priorMs;
  if (priorMs == 0 || deltaMs >= 500) {
    if (priorMs != 0 && deltaMs != 0) {
      canRxRate = (receivedFrameCount - priorCanRx) * 1000.0f / deltaMs;
      canRawRate = (rawSequence - priorRaw) * 1000.0f / deltaMs;
      bthByteRate = (bthRxBytes - priorBth) * 1000.0f / deltaMs;
    }
    priorMs = nowMs;
    priorCanRx = receivedFrameCount;
    priorRaw = rawSequence;
    priorBth = bthRxBytes;
  }

  if (force) {
    drawStaticUI();
    memset(cache, 0, sizeof(cache));
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("CAN+BTH ACQUISITION v2.6", 10, 8, 2);
    tft.drawString("CAN RX:", 10, 35, 2);
    tft.drawString("CAN Q:", 10, 58, 2);
    tft.drawString("BTH RX:", 10, 81, 2);
    tft.drawString("BTH Q:", 10, 104, 2);
    tft.drawString("SD:", 10, 127, 2);
    tft.drawString("BLE:", 10, 150, 2);
    tft.drawString("DIAG:", 10, 173, 2);
    tft.drawString("MEM:", 10, 196, 2);
  }

  char text[64];
  snprintf(text, sizeof(text), "%.0f in / %.0f raw fps", canRxRate, canRawRate);
  drawDirtyField(115, 35, 355, 20, text, cache[0], sizeof(cache[0]), force);
  UBaseType_t canDepth = canQueue ? uxQueueMessagesWaiting(canQueue) : 0;
  snprintf(text, sizeof(text), "%u/%u H%lu drop%lu", (unsigned)canDepth, (unsigned)CAN_QUEUE_LENGTH,
           (unsigned long)canQueueHighWater, (unsigned long)canQueueDrops);
  drawDirtyField(115, 58, 355, 20, text, cache[1], sizeof(cache[1]), force);
  snprintf(text, sizeof(text), BTH_CAPTURE_ENABLED ? "%.0f B/s err %lu/%lu" : "OFF (CAN baseline)",
           bthByteRate, (unsigned long)bthParityErrors, (unsigned long)bthFrameErrors);
  drawDirtyField(115, 81, 355, 20, text, cache[2], sizeof(cache[2]), force);
  UBaseType_t bthDepth = bthQueue ? uxQueueMessagesWaiting(bthQueue) : 0;
  snprintf(text, sizeof(text), BTH_CAPTURE_ENABLED ? "%u/%u H%lu drop%lu" : "not allocated",
           (unsigned)bthDepth, (unsigned)BTH_QUEUE_LENGTH, (unsigned long)bthQueueHighWater,
           (unsigned long)bthQueueDrops);
  drawDirtyField(115, 104, 355, 20, text, cache[3], sizeof(cache[3]), force);
  uint64_t rawAvg = rawWriteCount ? rawWriteTotalUs / rawWriteCount : 0;
  snprintf(text, sizeof(text), "%s wr avg/max %llu/%llu us", sdReady ? "READY" : "NO SD",
           (unsigned long long)rawAvg, (unsigned long long)rawWriteMaxUs);
  drawDirtyField(115, 127, 355, 20, text, cache[4], sizeof(cache[4]), force);
  snprintf(text, sizeof(text), "%s sync%lu", bleStateLabel(), (unsigned long)bleSyncSamples);
  drawDirtyField(115, 150, 355, 20, text, cache[5], sizeof(cache[5]), force);
  snprintf(text, sizeof(text), "%s %s", diagnosticEnabled ? "ON" : "OFF",
           externalTesterInterlockActive() ? "EXT HOLD" : "READY");
  drawDirtyField(115, 173, 355, 20, text, cache[6], sizeof(cache[6]), force);
  snprintf(text, sizeof(text), "free%u largest%u loop%llu us", (unsigned)ESP.getFreeHeap(),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
           (unsigned long long)mainLoopMaxUs);
  drawDirtyField(115, 196, 355, 20, text, cache[7], sizeof(cache[7]), force);

  drawButtons();
  displayPageChanged = false;
  ++tftRenderCount;
  uint64_t elapsed = (uint64_t)esp_timer_get_time() - startedUs;
  if (elapsed > tftRenderMaxUs) tftRenderMaxUs = elapsed;'''


HANDLE_TOUCH_BODY = r'''  uint32_t nowMs = millis();
  uint16_t x = 0, y = 0;
  digitalWrite(SD_CS_PIN, HIGH);
  bool pressed = tft.getTouch(&x, &y);

  if (pressed) {
    if (!touchWasDown) {
      touchWasDown = true;
      touchDownX = x;
      touchDownY = y;
      Serial.printf("# TOUCH DOWN,%u,%u\n", x, y);
    }
    return;
  }
  if (!touchWasDown) return;
  touchWasDown = false;
  if (nowMs - lastTouchMs < 250) return;
  lastTouchMs = nowMs;

  if (applicationMode == APP_WIFI_CONFIRM) {
    bool cancel = touchDownX >= WIFI_CONFIRM_CANCEL_X &&
                  touchDownX < WIFI_CONFIRM_CANCEL_X + WIFI_CONFIRM_BTN_W &&
                  touchDownY >= WIFI_CONFIRM_BTN_Y &&
                  touchDownY < WIFI_CONFIRM_BTN_Y + WIFI_CONFIRM_BTN_H;
    bool start = touchDownX >= WIFI_CONFIRM_START_X &&
                 touchDownX < WIFI_CONFIRM_START_X + WIFI_CONFIRM_BTN_W &&
                 touchDownY >= WIFI_CONFIRM_BTN_Y &&
                 touchDownY < WIFI_CONFIRM_BTN_Y + WIFI_CONFIRM_BTN_H;
    if (cancel) {
      applicationMode = APP_LOGGER;
      drawStaticUI();
      updateDisplay();
    } else if (start) {
      if (!startWifiFileMode()) {
        applicationMode = APP_LOGGER;
        setLoggerStatus(loggingActive ? "STOP LOG FOR WIFI" : "WIFI START FAILED");
        drawStaticUI();
        updateDisplay();
      }
    }
    return;
  }

  if (applicationMode == APP_WIFI_FILES) {
    if (wifiTransferActive) return;
    bool refresh = touchDownX >= WIFI_REFRESH_BTN_X &&
                   touchDownX < WIFI_REFRESH_BTN_X + WIFI_MODE_BTN_W &&
                   touchDownY >= WIFI_MODE_BTN_Y &&
                   touchDownY < WIFI_MODE_BTN_Y + WIFI_MODE_BTN_H;
    bool exitMode = touchDownX >= WIFI_EXIT_BTN_X &&
                    touchDownX < WIFI_EXIT_BTN_X + WIFI_MODE_BTN_W &&
                    touchDownY >= WIFI_MODE_BTN_Y &&
                    touchDownY < WIFI_MODE_BTN_Y + WIFI_MODE_BTN_H;
    if (refresh) updateWifiFileScreen();
    else if (exitMode) restartLoggerFromWifi();
    return;
  }

  bool logButton = touchDownX >= CYD_LOG_BTN_X &&
                   touchDownX < CYD_LOG_BTN_X + CYD_LOG_BTN_W &&
                   touchDownY >= CYD_LOG_BTN_Y &&
                   touchDownY < CYD_LOG_BTN_Y + CYD_LOG_BTN_H;
  bool diagButton = touchDownX >= CYD_DIAG_BTN_X &&
                    touchDownX < CYD_DIAG_BTN_X + CYD_DIAG_BTN_W &&
                    touchDownY >= CYD_DIAG_BTN_Y &&
                    touchDownY < CYD_DIAG_BTN_Y + CYD_DIAG_BTN_H;
  bool wifiButton = touchDownX >= CYD_WIFI_BTN_X &&
                    touchDownX < CYD_WIFI_BTN_X + CYD_WIFI_BTN_W &&
                    touchDownY >= CYD_WIFI_BTN_Y &&
                    touchDownY < CYD_WIFI_BTN_Y + CYD_WIFI_BTN_H;

  if (wifiButton) {
    if (sdReady && !loggingActive) {
      applicationMode = APP_WIFI_CONFIRM;
      drawWifiConfirmScreen();
    } else {
      setLoggerStatus(loggingActive ? "STOP LOG FOR WIFI" : "SD NOT READY");
    }
  } else if (logButton) {
    if (loggingActive) stopLogging(true);
    else startLogging();
  } else if (diagButton) {
    if (vehicleProfile == PROFILE_PRIUS_GEN2 && profileConfidence >= 80) {
      setDiagnosticCapture(!diagnosticEnabled, "Touchscreen user action");
    } else if (nowMs - lastDiagRejectMs >= 2000) {
      writeEvent("WARNING", "DIAGNOSTIC_ENABLE_REJECTED", "Strong Prius Gen 2 profile required; Camry remains passive-only");
      lastDiagRejectMs = nowMs;
    }
  }
  if (applicationMode == APP_LOGGER) drawButtons();'''


LOOP_BODY = r'''  uint64_t loopStartUs = (uint64_t)esp_timer_get_time();
  if (applicationMode == APP_WIFI_FILES) {
    serviceWifiFileMode();
    return;
  }

  serviceBleSync();

  CapturedFrame batch[CAN_BATCH_LENGTH];
  size_t count = 0;
  while (count < CAN_BATCH_LENGTH && canQueue != nullptr &&
         xQueueReceive(canQueue, &batch[count], 0) == pdTRUE) ++count;
  if (canQueue != nullptr) {
    UBaseType_t depth = uxQueueMessagesWaiting(canQueue);
    if (depth > canQueueHighWater) canQueueHighWater = depth;
  }

  if (count) writeRawBatch(batch, count);
  serviceBthPersistence();
  for (size_t i = 0; i < count; ++i) processCapturedFrame(batch[i]);

  drainDiagnosticQueue();
  emitPeriodicHealth();
  if (BTH_CAPTURE_ENABLED && loggingActive && millis() - lastHealthMetaMs >= 5000)
    emitBthCounters((uint64_t)esp_timer_get_time());
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


FINALIZE_BODY = r'''  if (!stopPending || !loggingActive) return;
  if (canQueue != nullptr && uxQueueMessagesWaiting(canQueue) != 0) return;
  if (BTH_CAPTURE_ENABLED && bthQueue != nullptr && uxQueueMessagesWaiting(bthQueue) != 0) return;
  serviceMetaQueue();
  uint64_t nowUs = (uint64_t)esp_timer_get_time();
  emitStreamCounters(true);
  emitHealthSnapshot(true);
  emitStorageHealth(true);
  if (BTH_CAPTURE_ENABLED) emitBthCounters(nowUs);
  emitStreamFileClose(nowUs, rawFileIndex, 1);
  uint8_t stopPayload[2] = {0, 0};
  appendMetaDirect(TVM1_STREAM_STOP, TVM1_STREAM_CAN, 0, nowUs, stopPayload, sizeof(stopPayload));
  if (BTH_CAPTURE_ENABLED) {
    emitBthFileClose(nowUs, bthFileIndex, 1);
    appendMetaDirect(TVM1_STREAM_STOP, TVM1_STREAM_BTH, 0, nowUs, stopPayload, sizeof(stopPayload));
  }
  if (stopPendingClean) {
    uint8_t closePayload[8] = {};
    tvm1PutLe16(closePayload, 0);
    closePayload[2] = 1;
    tvm1PutLe16(closePayload + 4, BTH_CAPTURE_ENABLED ? 2 : 1);
    appendMetaDirect(TVM1_SESSION_CLOSE, TVM1_STREAM_SESSION, 0, nowUs, closePayload, sizeof(closePayload));
  }
  flushLogFiles();
  uint32_t finalMetaSequence = tvm1Writer.sequence();
  closeSessionFiles();
  loggingActive = false;
  manifestClosed = stopPendingClean;
  stopPending = false;
  char status[28];
  snprintf(status, sizeof(status), "%s CLOSED%s", sessionName(), sessionHasCanTraffic ? "" : " EMPTY");
  setLoggerStatus(status);
  Serial.printf("# LOG STOPPED,%s,raw=%llu,meta_seq=%lu,bth_bytes=%llu\n", sessionDir,
                (unsigned long long)rawSequence, (unsigned long)finalMetaSequence,
                (unsigned long long)bthPersistedBytes);'''


FLUSH_BODY = r'''  if (!loggingActive) return;
  if (rawFile) {
    uint64_t started = (uint64_t)esp_timer_get_time();
    rawFile.flush();
    uint64_t elapsed = (uint64_t)esp_timer_get_time() - started;
    ++rawFlushCount;
    if (elapsed > rawFlushMaxUs) rawFlushMaxUs = elapsed;
  }
  if (BTH_CAPTURE_ENABLED && bthFile) {
    uint64_t started = (uint64_t)esp_timer_get_time();
    bth1Writer.flush();
    uint64_t elapsed = (uint64_t)esp_timer_get_time() - started;
    ++bthFlushCount;
    if (elapsed > bthFlushMaxUs) bthFlushMaxUs = elapsed;
  }
  if (metaFile) {
    uint64_t started = (uint64_t)esp_timer_get_time();
    tvm1Writer.flush();
    uint64_t elapsed = (uint64_t)esp_timer_get_time() - started;
    ++metaFlushCount;
    if (elapsed > metaFlushMaxUs) metaFlushMaxUs = elapsed;
  }'''


def _transform(source: str) -> str:
    source = source.replace("Diagnostic CAN Logger", "CAN+BTH Logger")
    source = _replace_once(
        source,
        '#include "TVM1Meta.h"',
        '#include "TVM1Meta.h"\n#include "BTH1Raw.h"\n#include "driver/uart.h"',
        "BTH includes",
    )
    source = _replace_once(
        source,
        "#define CAN_RX_PIN GPIO_NUM_32",
        "#define CAN_RX_PIN GPIO_NUM_32\n" + BTH_CONFIG,
        "BTH config",
    )
    source = source.replace("constexpr uint16_t CAN_QUEUE_LENGTH = 1024;", "constexpr uint16_t CAN_QUEUE_LENGTH = 768;")
    source = _replace_once(
        source,
        "QueueHandle_t diagnosticQueue = nullptr;",
        "QueueHandle_t diagnosticQueue = nullptr;\n" + BTH_GLOBALS,
        "BTH globals",
    )

    old_buttons = '''constexpr int CYD_LOG_BTN_X = 245;\nconstexpr int CYD_LOG_BTN_Y = 258;\nconstexpr int CYD_LOG_BTN_W = 105;\nconstexpr int CYD_LOG_BTN_H = 50;\nconstexpr int CYD_DIAG_BTN_X = 365;\nconstexpr int CYD_DIAG_BTN_Y = 258;\nconstexpr int CYD_DIAG_BTN_W = 105;\nconstexpr int CYD_DIAG_BTN_H = 50;\nconstexpr int CYD_PAGE_BTN_X = 10;\nconstexpr int CYD_PAGE_BTN_Y = 258;\nconstexpr int CYD_PAGE_BTN_W = 105;\nconstexpr int CYD_PAGE_BTN_H = 50;\nconstexpr int CYD_WIFI_BTN_X = 125;\nconstexpr int CYD_WIFI_BTN_Y = 258;\nconstexpr int CYD_WIFI_BTN_W = 105;\nconstexpr int CYD_WIFI_BTN_H = 50;'''
    new_buttons = '''constexpr int CYD_WIFI_BTN_X = 10;\nconstexpr int CYD_WIFI_BTN_Y = 258;\nconstexpr int CYD_WIFI_BTN_W = 145;\nconstexpr int CYD_WIFI_BTN_H = 50;\nconstexpr int CYD_LOG_BTN_X = 170;\nconstexpr int CYD_LOG_BTN_Y = 258;\nconstexpr int CYD_LOG_BTN_W = 145;\nconstexpr int CYD_LOG_BTN_H = 50;\nconstexpr int CYD_DIAG_BTN_X = 330;\nconstexpr int CYD_DIAG_BTN_Y = 258;\nconstexpr int CYD_DIAG_BTN_W = 140;\nconstexpr int CYD_DIAG_BTN_H = 50;'''
    source = _replace_once(source, old_buttons, new_buttons, "three-button layout")

    marker = "bool startLogging() {"
    if marker not in source:
        raise ValueError("startLogging definition marker missing")
    source = source.replace(marker, BTH_HELPERS + "\n\n" + marker, 1)

    source = _replace_once(
        source,
        "  loggingActive = true;",
        "  if (!startBthSession(createUs)) return failLogStart(\"BTH_000.BTH\");\n  loggingActive = true;",
        "BTH session start",
    )

    stop_body = r'''  if (!loggingActive || stopPending) return;
  bthSessionAccepting = false;
  stopPending = true;
  stopPendingClean = closedCleanly;
  stopRequestUs = (uint64_t)esp_timer_get_time();
  writeEvent("INFO", "LOGGING_STOP_REQUESTED", String("requested_us=") + String((unsigned long long)stopRequestUs));
  setLoggerStatus("STOP PENDING");'''
    source = _replace_function(source, "void stopLogging(bool closedCleanly)", stop_body)
    source = _replace_function(source, "void finalizePendingStop()", FINALIZE_BODY)
    source = _replace_function(source, "void flushLogFiles()", FLUSH_BODY)
    source = _replace_function(source, "void loop()", LOOP_BODY)
    source = _replace_function(source, "void drawButtons()", DRAW_BUTTONS_BODY)
    source = _replace_function(source, "void updateDisplay()", UPDATE_DISPLAY_BODY)
    source = _replace_function(source, "void handleTouch()", HANDLE_TOUCH_BODY)

    close_body = r'''  if (rawFile) rawFile.close();
  if (bthFile) bthFile.close();
  if (metaFile) metaFile.close();
  bth1Writer.detach();
  tvm1Writer.detach();'''
    source = _replace_function(source, "void closeSessionFiles()", close_body)

    # Failed start cleanup must remove any partially-created native BTH files too.
    cleanup_start, cleanup_brace, cleanup_end = _find_function(source, "void cleanupFailedSession()")
    cleanup_body = source[cleanup_brace + 1 : cleanup_end - 1]
    needle = "  SD.rmdir(sessionDir);"
    if needle not in cleanup_body:
        raise ValueError("cleanup rmdir marker missing")
    cleanup_body = cleanup_body.replace(
        needle,
        "  for (uint16_t i = 0; i <= bthFileIndex; ++i) {\n"
        "    snprintf(path, sizeof(path), \"%s/BTH_%03u.BTH\", sessionDir, i);\n"
        "    if (SD.exists(path)) SD.remove(path);\n"
        "  }\n" + needle,
        1,
    )
    source = source[:cleanup_start] + source[cleanup_start:cleanup_brace] + "{\n" + cleanup_body.strip("\n") + "\n}" + source[cleanup_end:]

    # Wi-Fi remains exclusive; stop the UART task/driver before the AP starts.
    source = _replace_once(
        source,
        '  printHeapStage("WIFI_LOGGER_SERVICES_STOPPED");',
        '  shutdownBthRuntime();\n  printHeapStage("WIFI_LOGGER_SERVICES_STOPPED");',
        "Wi-Fi BTH shutdown",
    )

    # Initialize the optional UART runtime at the end of setup. In the default
    # CAN-only build this returns before allocating any resource.
    source = _append_to_function(
        source,
        "void setup()",
        '  if (!initializeBthRuntime()) Serial.println("# BTH INIT ERROR,disabled for this boot");',
    )

    for forbidden in ("CYD_PAGE_BTN", '"PAGE"', "LIVE TEMPERATURES", "TEMP PAGE", "STATUS PAGE"):
        if forbidden in source:
            raise ValueError(f"forbidden acquisition UI token remains: {forbidden}")
    return source


def generate(rc2_dir: Path | str, out_root: Path | str) -> Path:
    rc2_dir = Path(rc2_dir)
    out_root = Path(out_root)
    out_dir = out_root / OUT_DIR_NAME
    if out_dir.exists():
        shutil.rmtree(out_dir)

    with tempfile.TemporaryDirectory() as temp_name:
        temp_root = Path(temp_name)
        base_dir = _base.generate(rc2_dir, temp_root)
        if base_dir.name != BASE_OUT_DIR:
            raise ValueError(f"unexpected base output directory: {base_dir}")
        shutil.copytree(base_dir, out_dir)

    base_ino = out_dir / BASE_INO
    source = base_ino.read_text(encoding="utf-8")
    source = _transform(source)
    new_ino = out_dir / NEW_INO
    new_ino.write_text(source, encoding="utf-8", newline="\n")
    base_ino.unlink()
    (out_dir / "BTH1Raw.h").write_text(BTH1_RAW_H, encoding="utf-8", newline="\n")

    readme_path = out_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    readme += """

## CAN + BTH acquisition profile

This build is acquisition-first. The default checked-in configuration is **CAN-only performance baseline** with `ENABLE_BTH_CAPTURE=0`. In that mode the BTH UART driver, event queue, BTH chunk queue, task, and BTH file are not allocated.

When the receive-only SN75HVD12 interface is installed, set `ENABLE_BTH_CAPTURE=1` to enable UART2 GPIO35 capture at 19200 8O1 into native `BTH_nnn.BTH` BTH1 files. GPIO39 remains unused.

TVM1 stream identities are CAN=1 and BTH=2. `SESSION_CLOSE.registered_stream_count` is 1 in the CAN-only baseline and 2 when BTH is enabled. Wi-Fi file maintenance enumerates files actually present, so BTH native files are transferred without being mislabeled as CAN.

The first vehicle validation must compare CAN retention in the default CAN-only build against prior v2.5/DEV logger sessions before enabling BTH.
"""
    readme_path.write_text(readme, encoding="utf-8", newline="\n")

    version_path = out_dir / "VERSION.txt"
    version = version_path.read_text(encoding="utf-8") if version_path.exists() else ""
    version += "\nprofile=CAN_BTH_ACQUISITION\nbth_default=OFF\ncan_queue=768\n"
    version_path.write_text(version, encoding="utf-8", newline="\n")
    return out_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("rc2_dir", type=Path)
    parser.add_argument("out_root", type=Path)
    args = parser.parse_args()
    print(generate(args.rc2_dir, args.out_root))
