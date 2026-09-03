/*
  Toyota Hybrid CYD 3.5-inch Diagnostic CAN Logger v2.4.2

  Target hardware:
    - ESP32-3248S035R / E32N35T resistive-touch display
    - SN65HVD230 / VP230 CAN transceiver
    - ESP32 GPIO25 -> VP230 TXD, GPIO32 <- VP230 RXD
    - OBD-II pin 6 CAN-H, pin 14 CAN-L
    - Do NOT add 120-ohm termination when attached to the intact vehicle bus.

  Safety model:
    - TWAI starts in LISTEN-ONLY mode. Normal mode is entered only after an
      explicit touchscreen diagnostic enable on a strongly identified Gen 2.
    - No fan commands, actuator commands, writes, clears, resets, or coding commands exist.
    - BLE can synchronize clocks, add markers, and start/stop SD logging. BLE
      has no CAN-transmit command and a BLE start forces passive capture.

  Arduino libraries:
    - TFT_eSPI (configured for this board)
    - SD and SPI (included with ESP32 Arduino core)
    - Native ESP32 TWAI driver
*/

#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <TFT_eSPI.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "driver/twai.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"

// --------------------------- Hardware configuration --------------------------
TFT_eSPI tft = TFT_eSPI();
// Validated arrangement: TFT_eSPI keeps its normal SPI controller while the
// onboard microSD uses a separate HSPI instance routed through the GPIO matrix.
SPIClass sdSPI(HSPI);

#define TFT_BL_PIN 27
#define CAN_TX_PIN GPIO_NUM_25
#define CAN_RX_PIN GPIO_NUM_32

#define SD_CS_PIN   5
#define SD_SCK_PIN 18
#define SD_MISO_PIN 19
#define SD_MOSI_PIN 23

constexpr uint32_t CAN_BITRATE = 500000;
constexpr uint32_t USB_BAUD = 115200;
constexpr bool AUTO_START_LOGGING = false;
constexpr bool USB_DECODED_CSV = false;
constexpr bool PRINT_SD_DIRECTORY_AT_BOOT = false;
constexpr bool ENABLE_GEN2_PASSIVE_CANDIDATES = true;
constexpr bool ENABLE_CAMRY_AHV40_PASSIVE_CANDIDATES = true;
constexpr uint32_t RAW_ROTATE_BYTES = 25UL * 1024UL * 1024UL;
constexpr uint32_t DIAGNOSTIC_TIMEOUT_US = 500000;
constexpr uint32_t DIAGNOSTIC_GAP_MS = 200;
constexpr uint32_t DECODED_PERIOD_MS = 100;
constexpr uint32_t DISPLAY_PERIOD_MS = 250;
constexpr uint32_t FILE_FLUSH_PERIOD_MS = 1000;
constexpr uint32_t MANIFEST_CHECKPOINT_PERIOD_MS = 5000;
constexpr uint32_t TWAI_STATUS_PERIOD_MS = 1000;
constexpr uint64_t MIN_SD_FREE_BYTES = 8ULL * 1024ULL * 1024ULL;
constexpr uint32_t SD_SPI_FREQUENCY = 4000000;
// Six session streams remain open. Ten descriptors cover those streams plus
// temporary manifest/checkpoint/directory operations without the excessive
// mount-time resource reservation observed with 16 on this non-PSRAM ESP32.
constexpr uint8_t SD_MAX_OPEN_FILES = 10;
// A 1024-record queue still buffers 24 KiB of raw CAN data while preserving a
// larger contiguous block for the ESP32 BLE controller and host stack.
constexpr uint16_t CAN_QUEUE_LENGTH = 1024;
constexpr uint64_t CAN_TRAFFIC_RECENT_US = 3000000ULL;
constexpr uint32_t EXTERNAL_TESTER_HOLD_MS = 5000;
constexpr uint8_t BLE_PROTOCOL_VERSION = 1;

// BLE carries only clock/session metadata. It cannot inject CAN frames or
// enable diagnostic polling.
constexpr char BLE_SERVICE_UUID[] = "6ed9f000-4f21-4c8c-a8a7-923c86b40001";
constexpr char BLE_COMMAND_UUID[] = "6ed9f000-4f21-4c8c-a8a7-923c86b40002";
constexpr char BLE_RESPONSE_UUID[] = "6ed9f000-4f21-4c8c-a8a7-923c86b40003";

constexpr int CYD_LOG_BTN_X = 245;
constexpr int CYD_LOG_BTN_Y = 258;
constexpr int CYD_LOG_BTN_W = 105;
constexpr int CYD_LOG_BTN_H = 50;
constexpr int CYD_DIAG_BTN_X = 365;
constexpr int CYD_DIAG_BTN_Y = 258;
constexpr int CYD_DIAG_BTN_W = 105;
constexpr int CYD_DIAG_BTN_H = 50;
constexpr int CYD_PAGE_BTN_X = 10;
constexpr int CYD_PAGE_BTN_Y = 258;
constexpr int CYD_PAGE_BTN_W = 105;
constexpr int CYD_PAGE_BTN_H = 50;

// ------------------------------- Data types ----------------------------------
enum VehicleProfile : uint8_t {
  PROFILE_SCANNING = 0,
  PROFILE_PRIUS_GEN2,
  PROFILE_PRIUS_GEN3,
  PROFILE_PRIUS_PHV_GEN1,
  PROFILE_CAMRY_HYBRID_GEN1,
  PROFILE_PRIUS_GEN3_OR_PHV,
  PROFILE_UNKNOWN,
  PROFILE_CONFLICT
};

enum BleLinkState : uint8_t {
  BLE_LINK_STARTING = 0,
  BLE_LINK_ADVERTISING,
  BLE_LINK_CONNECTED,
  BLE_LINK_ERROR
};

struct __attribute__((packed)) CapturedFrame {
  uint64_t timeUs;
  uint32_t identifier;
  uint8_t data[8];
  uint8_t dlc;
  uint8_t extended;
  uint8_t rtr;
  uint8_t direction; // 0=RX, 1=TX
};

static_assert(sizeof(CapturedFrame) == 24, "Binary CAN record must remain 24 bytes");

struct DiagnosticRequest {
  uint32_t requestId;
  uint8_t service;
  uint8_t pid;
  const char *name;
};

struct DiagnosticTransaction {
  bool active;
  bool multiFrame;
  uint32_t requestId;
  uint32_t responseId;
  uint8_t service;
  uint8_t pid;
  uint64_t requestTimeUs;
  uint64_t lastActivityUs;
  uint16_t expectedLength;
  uint16_t receivedLength;
  uint8_t nextSequence;
  uint8_t frameCount;
  uint8_t payload[96];
};

struct BleSyncRecord {
  uint16_t sequence;
  uint64_t receiveUs;
  uint64_t sendUs;
};

struct BleCommand {
  uint16_t sequence;
  uint8_t opcode;  // 1=start passive, 2=stop, 3=marker
  uint8_t flags;
  uint16_t marker;
  uint64_t receiveUs;
};

struct LiveSignals {
  float socPct;
  float packVolts;
  float packAmps;
  float packKW;
  int32_t mg1RPM;
  int32_t mg2RPM;
  int32_t engineRPM;
  float mg1InvF;
  float mg2InvF;
  float mg1StatorF;
  float mg2StatorF;
  float engineCoolantF;
  float engineIntakeAirF;
  float catalystB1S1F;
  float converterTempF;
  float hvTemp1F;
  float hvTemp2F;
  float hvTemp3F;
  float hvAvgF;
  float intakeTempF;
  float auxVolts;
  float deltaSocPct;
  uint8_t fanLevel;
  uint8_t gearCode;
  uint8_t gearRedundantCode;
  float blockVolts[14];
  float blockMinV;
  float blockMaxV;
  float blockDeltaV;
  uint8_t blockMinNumber;
  uint8_t blockMaxNumber;
  float internalResistance[14];
  uint32_t passiveElectricalMs;
  uint32_t passiveSocTempMs;
  uint32_t engineRPMMs;
  uint32_t c3Ms;
  uint32_t c4Ms;
  uint32_t coolantMs;
  uint32_t engineIntakeMs;
  uint32_t catalystMs;
  uint32_t ceMs;
  uint32_t cfMs;
  uint32_t d0Ms;
  uint32_t camryGearMs;
  uint32_t camryEngineMs;
  uint32_t camryCoolantMs;
  bool passiveElectricalValid;
  bool passiveSocTempValid;
  bool engineRPMValid;
  bool c3Valid;
  bool c4Valid;
  bool coolantValid;
  bool engineIntakeValid;
  bool catalystValid;
  bool ceValid;
  bool cfValid;
  bool d0Valid;
  bool camryGearValid;
  bool camryGearRedundantValid;
  bool camryEngineValid;
  bool camryCoolantValid;
};

// ------------------------- Vehicle fingerprint data --------------------------
const uint16_t PRIUS_G2_FINGERPRINT_IDS[] = {
  0x527,0x528,0x529,0x52C,0x540,0x553,0x554,0x56D,0x57F,0x591,
  0x5A4,0x5B2,0x5B6,0x5C8,0x5CC,0x5D4,0x5EC,0x5ED,0x5F8,0x602
};
const uint16_t CAMRY_AHV40_FINGERPRINT_IDS[] = {
  0x03D,0x383,0x38B,0x394,0x398,0x39B,0x3A0,0x3A1,0x3B0,0x3B1,0x3B3,0x3B4,
  0x3B6,0x3B7,0x3B9,0x3C1,0x420,0x440,0x442,0x4DC,0x4DD,0x610,0x611
};
bool priusSeen[sizeof(PRIUS_G2_FINGERPRINT_IDS) / sizeof(uint16_t)] = {};
bool camrySeen[sizeof(CAMRY_AHV40_FINGERPRINT_IDS) / sizeof(uint16_t)] = {};
uint8_t priusScore = 0;
uint8_t camryScore = 0;
VehicleProfile vehicleProfile = PROFILE_SCANNING;
uint8_t profileConfidence = 0;
uint32_t detectionStartedMs = 0;

// Read-only diagnostic whitelist. No control/write services are present.
const DiagnosticRequest DIAGNOSTIC_REQUESTS[] = {
  {0x7E0, 0x01, 0x0C, "ENGINE_RPM"},
  {0x7E0, 0x01, 0x05, "ENGINE_COOLANT"},
  {0x7E0, 0x01, 0x0F, "ENGINE_INTAKE_AIR"},
  {0x7E0, 0x01, 0x3C, "CATALYST_B1S1"},
  {0x7E2, 0x21, 0xC3, "HYBRID_C3"},
  {0x7E2, 0x21, 0xC4, "HYBRID_C4"},
  {0x7E3, 0x21, 0xCE, "BATTERY_CE"},
  {0x7E3, 0x21, 0xCF, "BATTERY_CF"},
  {0x7E3, 0x21, 0xD0, "BATTERY_D0"}
};

// ------------------------------- Global state --------------------------------
QueueHandle_t canQueue = nullptr;
QueueHandle_t diagnosticQueue = nullptr;
QueueHandle_t bleSyncQueue = nullptr;
QueueHandle_t bleCommandQueue = nullptr;
TaskHandle_t canReceiveTaskHandle = nullptr;
LiveSignals live = {};
DiagnosticTransaction diag = {};

volatile uint32_t canQueueDrops = 0;
volatile uint32_t diagnosticQueueDrops = 0;
volatile uint32_t isotpFlowControlCount = 0;
volatile uint32_t isotpFlowControlFailures = 0;
volatile uint32_t isotpFlowControlMaxUs = 0;
volatile uint64_t isotpFlowControlTotalUs = 0;
uint32_t sdLogDrops = 0;
uint32_t sdLogDroppedFrames = 0;
uint64_t rawSequence = 0;
uint32_t diagnosticSequence = 0;
volatile uint32_t receivedFrameCount = 0;
volatile uint32_t transmittedFrameCount = 0;
volatile bool fastDiagActive = false;
volatile uint32_t fastDiagResponseId = 0;
volatile uint64_t fastDiagRequestTimeUs = 0;
uint32_t diagnosticTimeouts = 0;
uint32_t diagnosticNegativeResponses = 0;
uint32_t diagnosticIndex = 0;
uint32_t lastDiagnosticCompleteMs = 0;
uint32_t lastDecodedMs = 0;
uint32_t lastDisplayMs = 0;
uint32_t lastFlushMs = 0;
uint32_t lastManifestCheckpointMs = 0;
uint32_t lastTwaiStatusMs = 0;
uint32_t lastProfileEvaluationMs = 0;
uint32_t lastTouchMs = 0;
bool touchWasDown = false;
uint16_t touchDownX = 0;
uint16_t touchDownY = 0;
bool diagnosticEnabled = false;
bool sdReady = false;
bool loggingActive = false;
bool manifestClosed = false;
uint8_t displayPage = 0;
bool twaiRecovering = false;
uint32_t twaiRxMissedCount = 0;
uint32_t twaiRxOverrunCount = 0;
uint32_t twaiTxFailedCount = 0;
uint32_t twaiArbLostCount = 0;
uint32_t twaiBusErrorCount = 0;
uint32_t twaiRxQueued = 0;
uint32_t twaiTxQueued = 0;
uint32_t twaiBusOffEvents = 0;
uint32_t lastDiagRejectMs = 0;
volatile uint64_t externalTesterLastUs = 0;
uint64_t lastExternalTesterEventUs = 0;
uint64_t lastExternalDiagnosticLoggedUs = 0;
uint32_t lastExternalDiagnosticLoggedId = 0;
uint32_t externalDiagnosticFrames = 0;
uint32_t externalTesterEvents = 0;
bool twaiNormalMode = false;
bool bleConnected = false;
volatile BleLinkState bleLinkState = BLE_LINK_STARTING;
bool bleStackInitialized = false;
bool bleServiceReady = false;
char bleDeviceName[24] = {0};
uint32_t bleSyncSamples = 0;
uint32_t bleCommandCount = 0;
bool sessionHasCanTraffic = false;
uint64_t sessionStartUs = 0;
uint64_t sessionFirstCanUs = 0;
uint64_t sessionLastCanUs = 0;
uint32_t sessionStartReceivedFrames = 0;
uint32_t sessionStartTransmittedFrames = 0;
char loggerStatus[28] = "READY / STOPPED";
BleSyncRecord pendingSync[32] = {};
uint8_t pendingSyncCount = 0;

BLEServer *bleServer = nullptr;
BLECharacteristic *bleResponseCharacteristic = nullptr;

File rawFile;
File decodedFile;
File diagnosticFile;
File eventFile;
File syncFile;
File externalDiagnosticFile;
char sessionDir[32] = {0};
char rawPath[48] = {0};
uint16_t rawFileIndex = 0;

// ---------------------------- Explicit prototypes ----------------------------
// Explicit declarations prevent Arduino's auto-prototype generator from placing
// declarations before custom enum/struct definitions.
const char *profileLabel(VehicleProfile profile);
const char *dataQualityLabel();
const char *bleStateLabel();
const char *sessionName();
bool sessionTrafficRecent();
void setLoggerStatus(const char *status);
uint64_t nowMicros64();
uint16_t wordBE(uint8_t highByte, uint8_t lowByte);
int16_t signExtend12(uint16_t raw);
float rawTemperatureF(uint8_t highByte, uint8_t lowByte);
void canReceiveTask(void *parameter);
bool configureTwai(twai_mode_t mode);
bool setDiagnosticCapture(bool enable, const char *source);
bool sendIsoTpFlowControlFast(const CapturedFrame &firstFrame);
void processCapturedFrame(const CapturedFrame &frame);
void writeRawBatch(const CapturedFrame *frames, size_t count);
void observeFingerprint(uint32_t identifier);
void evaluateVehicleProfile();
void parsePassiveGen2(const CapturedFrame &frame);
void parsePassiveCamry(const CapturedFrame &frame);
const char *gearLabel(uint8_t gearCode);
bool transmitCAN(uint32_t identifier, const uint8_t *data, uint8_t dlc, const char *source);
void serviceDiagnosticScheduler();
void startDiagnosticRequest(const DiagnosticRequest &request);
void processDiagnosticFrame(const CapturedFrame &frame);
bool isExternalDiagnosticRequest(const CapturedFrame &frame);
void writeExternalDiagnosticFrame(const CapturedFrame &frame, const char *classification);
void completeDiagnostic(const char *status);
void decodeDiagnosticPayload(uint32_t responseId, const uint8_t *payload, uint16_t length);
void decodeC3(const uint8_t *data, uint16_t length);
void decodeC4(const uint8_t *data, uint16_t length);
void decodeCE(const uint8_t *data, uint16_t length);
void decodeCF(const uint8_t *data, uint16_t length);
void decodeD0(const uint8_t *data, uint16_t length);
bool initializeSD();
bool createSessionDirectory();
bool openRawFile();
void closeSessionFiles();
void cleanupFailedSession();
bool failLogStart(const char *stage);
void rotateRawFileIfNeeded();
void writeDecodedSample();
void writeDiagnosticRecord(const char *status, uint64_t completeTimeUs);
void writeEvent(const char *severity, const char *eventName, const String &details);
void writeReadme();
void writeSignalsDictionary();
void writeManifest(bool closedCleanly);
void writeCheckpoint(bool closedCleanly);
bool startLogging();
void stopLogging(bool closedCleanly);
void flushLogFiles();
void printSDDirectory(const char *dirname, uint8_t levels);
void printSDCardSummary();
void serviceTwaiHealth();
void drainDiagnosticQueue();
void drawStaticUI();
void updateDisplay();
void drawButtons();
void handleTouch();
void printHeapStage(const char *stage);
void disableBleSync(const char *stage);
bool initializeBleSync();
bool startBleAdvertising();
void serviceBleSync();
void writeSyncRecord(const BleSyncRecord &record, const char *source);
void sendBleControlResponse(const BleCommand &command, uint8_t status, uint64_t eventUs);
void processBleCommand(const BleCommand &command);
void printCsvFloat(File &file, bool valid, float value, uint8_t decimals);
void printCsvInt(File &file, bool valid, int32_t value);

static uint16_t readLe16(const uint8_t *p) {
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static void writeLe16(uint8_t *p, uint16_t value) {
  p[0] = value & 0xFF;
  p[1] = (value >> 8) & 0xFF;
}

static void writeLe64(uint8_t *p, uint64_t value) {
  for (uint8_t i = 0; i < 8; ++i) p[i] = (value >> (8 * i)) & 0xFF;
}

static void writeLe32(uint8_t *p, uint32_t value) {
  for (uint8_t i = 0; i < 4; ++i) p[i] = (value >> (8 * i)) & 0xFF;
}

class LoggerBleServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    (void)server;
    bleConnected = true;
    bleLinkState = BLE_LINK_CONNECTED;
    Serial.println("# BLE CONNECTED");
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    bleConnected = false;
    if (bleServiceReady) {
      bleLinkState = BLE_LINK_ADVERTISING;
      BLEDevice::startAdvertising();
      Serial.println("# BLE DISCONNECTED,ADVERTISING");
    } else {
      bleLinkState = BLE_LINK_ERROR;
      Serial.println("# BLE DISCONNECTED,DISABLED");
    }
  }
};

class LoggerBleCommandCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    const uint8_t *value = characteristic->getData();
    size_t length = characteristic->getLength();
    if (value == nullptr || length < 4 || value[1] != BLE_PROTOCOL_VERSION) return;

    uint64_t receiveUs = nowMicros64();
    uint16_t sequence = readLe16(&value[2]);
    if (value[0] == 0x01) {
      // The client retains T1 and records T4. The 20-byte reply fits the
      // default BLE ATT payload and contains the two ESP32 timestamps.
      uint8_t reply[20] = {};
      reply[0] = 0x81;
      reply[1] = BLE_PROTOCOL_VERSION;
      writeLe16(&reply[2], sequence);
      writeLe64(&reply[4], receiveUs);
      uint64_t sendUs = nowMicros64();
      writeLe64(&reply[12], sendUs);
      if (bleResponseCharacteristic != nullptr) {
        bleResponseCharacteristic->setValue(reply, sizeof(reply));
        bleResponseCharacteristic->notify();
      }
      BleSyncRecord record = {sequence, receiveUs, sendUs};
      if (bleSyncQueue != nullptr) xQueueSend(bleSyncQueue, &record, 0);
      return;
    }

    if (value[0] == 0x02 && length >= 8) {
      BleCommand command = {};
      command.sequence = sequence;
      command.opcode = value[4];
      command.flags = value[5];
      command.marker = readLe16(&value[6]);
      command.receiveUs = receiveUs;
      if (bleCommandQueue != nullptr) xQueueSend(bleCommandQueue, &command, 0);
    }
  }
};

// ---------------------------------- Setup -------------------------------------
void setup() {
  Serial.begin(USB_BAUD);
  delay(100);
  Serial.println("# ToyotaHybridCAN Diagnostic Logger v2.4.2");
  printHeapStage("BOOT");

  pinMode(TFT_BL_PIN, OUTPUT);
  digitalWrite(TFT_BL_PIN, HIGH);
  tft.init();
  tft.setRotation(1);
  tft.invertDisplay(false);
  tft.fillScreen(TFT_BLACK);
  // Measured on this E32R35T with the microSD card inserted.
  uint16_t calibration[5] = {295, 3524, 310, 3487, 7};
  tft.setTouch(calibration);
  drawStaticUI();
  printHeapStage("TFT_READY");

  // BLE must reserve its contiguous controller/host memory before the large
  // CAN queue, TWAI driver, and FAT filesystem are initialized. Advertising is
  // deliberately delayed until all subsystems are ready, so callbacks cannot
  // start a session during setup.
  bleSyncQueue = xQueueCreate(64, sizeof(BleSyncRecord));
  bleCommandQueue = xQueueCreate(16, sizeof(BleCommand));
  if (bleSyncQueue == nullptr || bleCommandQueue == nullptr) {
    if (bleSyncQueue != nullptr) vQueueDelete(bleSyncQueue);
    if (bleCommandQueue != nullptr) vQueueDelete(bleCommandQueue);
    bleSyncQueue = nullptr;
    bleCommandQueue = nullptr;
    bleLinkState = BLE_LINK_ERROR;
    Serial.println("# BLE ERROR,QUEUE_ALLOC");
  } else {
    initializeBleSync();
  }
  printHeapStage("BLE_SERVICE");

  canQueue = xQueueCreate(CAN_QUEUE_LENGTH, sizeof(CapturedFrame));
  diagnosticQueue = xQueueCreate(64, sizeof(CapturedFrame));
  if (canQueue == nullptr || diagnosticQueue == nullptr) {
    tft.fillScreen(TFT_RED);
    tft.drawString("QUEUE ALLOC FAILED", 40, 120, 4);
    Serial.println("# FATAL,CAN_QUEUE_ALLOC");
    while (true) delay(1000);
  }
  printHeapStage("CAN_QUEUES");

  sdReady = initializeSD();
  if (sdReady) printSDCardSummary();
  if (sdReady && AUTO_START_LOGGING) startLogging();
  printHeapStage("SD_STAGE");

  if (!configureTwai(TWAI_MODE_LISTEN_ONLY)) {
    tft.fillScreen(TFT_RED);
    tft.setTextColor(TFT_WHITE, TFT_RED);
    tft.drawString("TWAI START FAILED", 40, 120, 4);
    if (loggingActive) writeEvent("ERROR", "TWAI_START_FAILED", "Driver install or start failed");
    while (true) delay(1000);
  }
  diagnosticEnabled = false;
  detectionStartedMs = millis();
  printHeapStage("TWAI_READY");
  if (bleServiceReady) startBleAdvertising();
  printHeapStage("SETUP_COMPLETE");
  writeEvent("INFO", "TWAI_READY", "500 kbps LISTEN_ONLY; GPIO25 TX; GPIO32 RX");
  updateDisplay();
}

// -------------------------------- Main loop -----------------------------------
void loop() {
  serviceBleSync();
  drainDiagnosticQueue();

  CapturedFrame batch[128];
  size_t count = 0;
  while (count < 128 && xQueueReceive(canQueue, &batch[count], 0) == pdTRUE) ++count;
  for (size_t i = 0; i < count; ++i) processCapturedFrame(batch[i]);
  if (count) writeRawBatch(batch, count);

  // Frames may have arrived while the SD batch was written. Finish diagnostic
  // reassembly before evaluating timeouts or touchscreen disable requests.
  drainDiagnosticQueue();

  uint32_t nowMs = millis();
  if (nowMs - lastProfileEvaluationMs >= 1000) {
    evaluateVehicleProfile();
    lastProfileEvaluationMs = nowMs;
  }

  serviceDiagnosticScheduler();
  serviceTwaiHealth();
  handleTouch();
  serviceBleSync();

  if (nowMs - lastDecodedMs >= DECODED_PERIOD_MS) {
    writeDecodedSample();
    lastDecodedMs = nowMs;
  }
  if (nowMs - lastDisplayMs >= DISPLAY_PERIOD_MS) {
    updateDisplay();
    lastDisplayMs = nowMs;
  }
  if (nowMs - lastFlushMs >= FILE_FLUSH_PERIOD_MS) {
    flushLogFiles();
    lastFlushMs = nowMs;
  }
  if (loggingActive && nowMs - lastManifestCheckpointMs >= MANIFEST_CHECKPOINT_PERIOD_MS) {
    writeCheckpoint(false);
    lastManifestCheckpointMs = nowMs;
  }
  delay(1);
}

// ------------------------------- CAN capture ---------------------------------
uint64_t nowMicros64() {
  return (uint64_t)esp_timer_get_time();
}

bool configureTwai(twai_mode_t mode) {
  if (canReceiveTaskHandle != nullptr) {
    vTaskDelete(canReceiveTaskHandle);
    canReceiveTaskHandle = nullptr;
  }

  // These calls legitimately fail before the first installation.
  twai_stop();
  twai_driver_uninstall();

  twai_general_config_t general = TWAI_GENERAL_CONFIG_DEFAULT(CAN_TX_PIN, CAN_RX_PIN, mode);
  general.tx_queue_len = mode == TWAI_MODE_NORMAL ? 20 : 0;
  general.rx_queue_len = 100;
  twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&general, &timing, &filter) != ESP_OK) return false;
  if (twai_start() != ESP_OK) {
    twai_driver_uninstall();
    return false;
  }
  twai_reconfigure_alerts(TWAI_ALERT_RX_QUEUE_FULL | TWAI_ALERT_BUS_OFF |
                          TWAI_ALERT_BUS_RECOVERED | TWAI_ALERT_ABOVE_ERR_WARN |
                          TWAI_ALERT_ERR_PASS | TWAI_ALERT_TX_FAILED |
                          TWAI_ALERT_ARB_LOST | TWAI_ALERT_BUS_ERROR, nullptr);
  twaiNormalMode = mode == TWAI_MODE_NORMAL;
  if (xTaskCreatePinnedToCore(canReceiveTask, "CAN_RX", 4096, nullptr, 20,
                             &canReceiveTaskHandle, 0) != pdPASS) {
    twai_stop();
    twai_driver_uninstall();
    canReceiveTaskHandle = nullptr;
    return false;
  }
  return true;
}

bool setDiagnosticCapture(bool enable, const char *source) {
  if (enable) {
    if (!loggingActive || vehicleProfile != PROFILE_PRIUS_GEN2 || profileConfidence < 80) return false;
    if (externalTesterLastUs != 0 &&
        (nowMicros64() - externalTesterLastUs) / 1000ULL < EXTERNAL_TESTER_HOLD_MS) {
      writeEvent("WARNING", "DIAGNOSTIC_ENABLE_REJECTED", "External diagnostic tester recently observed");
      return false;
    }
    if (!twaiNormalMode && !configureTwai(TWAI_MODE_NORMAL)) {
      writeEvent("ERROR", "TWAI_MODE_CHANGE_FAILED", "Could not enter NORMAL diagnostic mode");
      return false;
    }
    diagnosticEnabled = true;
    writeEvent("INFO", "DIAGNOSTIC_ENABLED", String(source) + "; TWAI=NORMAL; read-only whitelist");
    return true;
  }

  fastDiagActive = false;
  if (diag.active) completeDiagnostic("DIAGNOSTIC_DISABLED");
  diagnosticEnabled = false;
  if (twaiNormalMode && !configureTwai(TWAI_MODE_LISTEN_ONLY)) {
    writeEvent("ERROR", "TWAI_MODE_CHANGE_FAILED", "Could not restore LISTEN_ONLY mode");
    return false;
  }
  writeEvent("INFO", "DIAGNOSTIC_DISABLED", String(source) + "; TWAI=LISTEN_ONLY");
  return true;
}

void canReceiveTask(void *parameter) {
  (void)parameter;
  twai_message_t message;
  for (;;) {
    if (twai_receive(&message, pdMS_TO_TICKS(100)) == ESP_OK) {
      CapturedFrame frame = {};
      frame.timeUs = nowMicros64();
      frame.identifier = message.identifier;
      frame.dlc = message.data_length_code;
      frame.extended = message.extd;
      frame.rtr = message.rtr;
      frame.direction = 0;
      memcpy(frame.data, message.data, 8);
      ++receivedFrameCount;
      if (isExternalDiagnosticRequest(frame)) {
        externalTesterLastUs = frame.timeUs;
        fastDiagActive = false;
      }
      bool rawQueued = false;
      if (!frame.extended && !frame.rtr &&
          (frame.identifier == 0x7E8 || frame.identifier == 0x7EA || frame.identifier == 0x7EB)) {
        // Preserve chronological RX-before-TX order in the raw queue. This
        // nonblocking RAM copy adds only microseconds before flow control.
        if (xQueueSend(canQueue, &frame, 0) != pdTRUE) ++canQueueDrops;
        rawQueued = true;
        // ISO-TP flow control is sent here on the high-priority receive task,
        // before TFT or SD work can delay it. Full reassembly remains in loop().
        if (fastDiagActive && frame.identifier == fastDiagResponseId && frame.timeUs >= fastDiagRequestTimeUs &&
            frame.dlc >= 2 && (frame.data[0] >> 4) == 0x1)
          sendIsoTpFlowControlFast(frame);
        if (xQueueSend(diagnosticQueue, &frame, 0) != pdTRUE) ++diagnosticQueueDrops;
      }
      if (!rawQueued && xQueueSend(canQueue, &frame, 0) != pdTRUE) ++canQueueDrops;
    }
  }
}

bool sendIsoTpFlowControlFast(const CapturedFrame &firstFrame) {
  if (!diagnosticEnabled || !twaiNormalMode) return false;
  uint16_t expected = ((uint16_t)(firstFrame.data[0] & 0x0F) << 8) | firstFrame.data[1];
  if (expected <= 7 || expected > sizeof(diag.payload)) return false;

  twai_message_t message = {};
  message.identifier = firstFrame.identifier - 8;
  message.data_length_code = 8;
  message.data[0] = 0x30;
  esp_err_t result = twai_transmit(&message, pdMS_TO_TICKS(5));
  if (result != ESP_OK) {
    ++isotpFlowControlFailures;
    return false;
  }

  uint64_t sentUs = nowMicros64();
  uint32_t latencyUs = (uint32_t)(sentUs - firstFrame.timeUs);
  ++isotpFlowControlCount;
  isotpFlowControlTotalUs += latencyUs;
  if (latencyUs > isotpFlowControlMaxUs) isotpFlowControlMaxUs = latencyUs;
  ++transmittedFrameCount;

  CapturedFrame tx = {};
  tx.timeUs = sentUs;
  tx.identifier = message.identifier;
  tx.dlc = 8;
  tx.direction = 1;
  memcpy(tx.data, message.data, 8);
  if (xQueueSend(canQueue, &tx, 0) != pdTRUE) ++canQueueDrops;
  return true;
}

void drainDiagnosticQueue() {
  CapturedFrame frame;
  while (xQueueReceive(diagnosticQueue, &frame, 0) == pdTRUE)
    processDiagnosticFrame(frame);
}

void processCapturedFrame(const CapturedFrame &frame) {
  if (!frame.extended && !frame.rtr) {
    if (isExternalDiagnosticRequest(frame)) {
      bool newObservation = lastExternalTesterEventUs == 0 ||
                            frame.timeUs - lastExternalTesterEventUs > EXTERNAL_TESTER_HOLD_MS * 1000ULL;
      lastExternalTesterEventUs = frame.timeUs;
      if (newObservation) {
        ++externalTesterEvents;
        writeEvent("INFO", "EXTERNAL_TESTER_DETECTED", "Passive observation; logger diagnostics forced off");
      }
      writeExternalDiagnosticFrame(frame, "EXTERNAL_REQUEST");
      if (diagnosticEnabled || twaiNormalMode) setDiagnosticCapture(false, "External diagnostic tester detected");
    } else if (externalTesterLastUs != 0 &&
               frame.timeUs >= externalTesterLastUs &&
               frame.timeUs - externalTesterLastUs <= EXTERNAL_TESTER_HOLD_MS * 1000ULL &&
               frame.identifier >= 0x7E8 && frame.identifier <= 0x7EF) {
      writeExternalDiagnosticFrame(frame, "EXTERNAL_RESPONSE");
    }
    observeFingerprint(frame.identifier);
    if (vehicleProfile == PROFILE_PRIUS_GEN2) parsePassiveGen2(frame);
    else if (vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1) parsePassiveCamry(frame);
  }
}

bool isExternalDiagnosticRequest(const CapturedFrame &frame) {
  if (frame.direction != 0 || frame.extended || frame.rtr || frame.dlc < 3) return false;
  if (!(frame.identifier == 0x7DF || (frame.identifier >= 0x7E0 && frame.identifier <= 0x7E7))) return false;
  uint8_t pciType = frame.data[0] >> 4;
  return pciType == 0x0 || pciType == 0x1;
}

void writeExternalDiagnosticFrame(const CapturedFrame &frame, const char *classification) {
  if (frame.timeUs == lastExternalDiagnosticLoggedUs && frame.identifier == lastExternalDiagnosticLoggedId) return;
  lastExternalDiagnosticLoggedUs = frame.timeUs;
  lastExternalDiagnosticLoggedId = frame.identifier;
  ++externalDiagnosticFrames;
  if (!loggingActive || !externalDiagnosticFile) return;
  externalDiagnosticFile.printf("%llu,%03lX,%u,", (unsigned long long)frame.timeUs,
                                (unsigned long)frame.identifier, frame.dlc);
  for (uint8_t i = 0; i < frame.dlc && i < 8; ++i) {
    if (frame.data[i] < 16) externalDiagnosticFile.print('0');
    externalDiagnosticFile.print(frame.data[i], HEX);
  }
  externalDiagnosticFile.print(',');
  externalDiagnosticFile.println(classification);
}

bool transmitCAN(uint32_t identifier, const uint8_t *data, uint8_t dlc, const char *source) {
  if (!diagnosticEnabled || !twaiNormalMode) {
    writeEvent("WARNING", "TWAI_TRANSMIT_BLOCKED", String(source) + "; passive mode active");
    return false;
  }
  twai_message_t message = {};
  message.identifier = identifier;
  message.extd = 0;
  message.rtr = 0;
  message.data_length_code = dlc;
  memcpy(message.data, data, dlc);
  esp_err_t result = twai_transmit(&message, pdMS_TO_TICKS(20));
  if (result != ESP_OK) {
    writeEvent("ERROR", "TWAI_TRANSMIT_FAILED", String(identifier, HEX) + ",err=" + String((int)result));
    return false;
  }

  ++transmittedFrameCount;
  CapturedFrame frame = {};
  frame.timeUs = nowMicros64();
  frame.identifier = identifier;
  frame.dlc = dlc;
  frame.direction = 1;
  memcpy(frame.data, data, dlc);
  (void)source;
  if (xQueueSend(canQueue, &frame, 0) != pdTRUE) ++canQueueDrops;
  return true;
}

// --------------------------- Vehicle identification --------------------------
const char *profileLabel(VehicleProfile profile) {
  switch (profile) {
    case PROFILE_PRIUS_GEN2: return "PRIUS GEN 2";
    case PROFILE_PRIUS_GEN3: return "PRIUS GEN 3";
    case PROFILE_PRIUS_PHV_GEN1: return "PRIUS PHV G1";
    case PROFILE_CAMRY_HYBRID_GEN1: return "CAMRY HYB G1";
    case PROFILE_PRIUS_GEN3_OR_PHV: return "GEN3/PHV AMBIG";
    case PROFILE_UNKNOWN: return "UNKNOWN";
    case PROFILE_CONFLICT: return "CONFLICT";
    default: return "SCANNING";
  }
}

void observeFingerprint(uint32_t identifier) {
  for (size_t i = 0; i < sizeof(PRIUS_G2_FINGERPRINT_IDS) / sizeof(uint16_t); ++i) {
    if (identifier == PRIUS_G2_FINGERPRINT_IDS[i] && !priusSeen[i]) {
      priusSeen[i] = true;
      ++priusScore;
    }
  }
  for (size_t i = 0; i < sizeof(CAMRY_AHV40_FINGERPRINT_IDS) / sizeof(uint16_t); ++i) {
    if (identifier == CAMRY_AHV40_FINGERPRINT_IDS[i] && !camrySeen[i]) {
      camrySeen[i] = true;
      ++camryScore;
    }
  }
}

void evaluateVehicleProfile() {
  VehicleProfile next = PROFILE_SCANNING;
  uint8_t confidence = 0;
  bool strongPrius = priusScore >= 4;
  bool strongCamry = camryScore >= 4;

  if (strongPrius && strongCamry) {
    next = PROFILE_CONFLICT;
  } else if (strongCamry) {
    next = PROFILE_CAMRY_HYBRID_GEN1;
    confidence = (uint8_t)min(95, 55 + (int)camryScore * 5);
  } else if (strongPrius) {
    next = PROFILE_PRIUS_GEN2;
    confidence = (uint8_t)min(85, 45 + (int)priusScore * 5);
  } else if (millis() - detectionStartedMs >= 10000) {
    next = PROFILE_UNKNOWN;
  }

  if (next != vehicleProfile || confidence != profileConfidence) {
    String details = String(profileLabel(vehicleProfile)) + " to " + profileLabel(next) +
                     ";P=" + String(priusScore) + ";C=" + String(camryScore) +
                     ";confidence=" + String(confidence);
    vehicleProfile = next;
    profileConfidence = confidence;
    writeEvent("INFO", "PROFILE_CHANGE", details);
    if (vehicleProfile != PROFILE_PRIUS_GEN2 && diagnosticEnabled) {
      setDiagnosticCapture(false, "Vehicle profile is not strong Prius Gen 2");
    }
  }
}

// --------------------------- Passive Gen 2 decoding --------------------------
uint16_t wordBE(uint8_t highByte, uint8_t lowByte) {
  return ((uint16_t)highByte << 8) | lowByte;
}

int16_t signExtend12(uint16_t raw) {
  raw &= 0x0FFF;
  return (raw & 0x0800) ? (int16_t)(raw | 0xF000) : (int16_t)raw;
}

float rawTemperatureF(uint8_t highByte, uint8_t lowByte) {
  return wordBE(highByte, lowByte) * 9.0f / 500.0f - 557.824f;
}

void parsePassiveGen2(const CapturedFrame &frame) {
  if (!ENABLE_GEN2_PASSIVE_CANDIDATES) return;
  uint32_t nowMs = millis();

  if (frame.identifier == 0x03B && frame.dlc == 5) {
    int16_t rawCurrent = signExtend12(((uint16_t)(frame.data[0] & 0x0F) << 8) | frame.data[1]);
    float amps = rawCurrent * 0.1f;
    float volts = wordBE(frame.data[2], frame.data[3]);
    if (amps >= -500.0f && amps <= 500.0f && volts >= 100.0f && volts <= 400.0f) {
      if (!live.ceValid || nowMs - live.ceMs > 1000) {
        live.packAmps = amps;
        live.packVolts = volts;
        live.packKW = volts * amps / 1000.0f;
      }
      live.passiveElectricalMs = nowMs;
      live.passiveElectricalValid = true;
    }
  }

  if (frame.identifier == 0x3CB && frame.dlc == 7) {
    float soc = frame.data[3] * 0.5f;
    int t1C = frame.data[4];
    int t2C = frame.data[5];
    if (soc >= 0.0f && soc <= 100.0f && t1C <= 100 && t2C <= 100) {
      if (!live.ceValid || nowMs - live.ceMs > 1000) live.socPct = soc;
      if (!live.cfValid || nowMs - live.cfMs > 1000) {
        live.hvTemp1F = t1C * 1.8f + 32.0f;
        live.hvTemp2F = t2C * 1.8f + 32.0f;
        live.hvAvgF = (live.hvTemp1F + live.hvTemp2F) / 2.0f;
      }
      live.passiveSocTempMs = nowMs;
      live.passiveSocTempValid = true;
    }
  }
}

// ---------------------- Passive Camry AHV40 candidates ----------------------
// These read-only candidates were derived from the supplied 2007 Camry capture.
// They are intentionally profile-gated and labelled PROBABLE in SIGNALS.CSV.
const char *gearLabel(uint8_t gearCode) {
  switch (gearCode) {
    case 0: return "P";
    case 1: return "R";
    case 2: return "N";
    case 3: return "D";
    default: return "?";
  }
}

void parsePassiveCamry(const CapturedFrame &frame) {
  if (!ENABLE_CAMRY_AHV40_PASSIVE_CANDIDATES) return;
  uint32_t nowMs = millis();

  if (frame.identifier == 0x120 && frame.dlc >= 6) {
    uint8_t code = frame.data[5] & 0x0F;
    if (code <= 3) {
      live.gearCode = code;
      live.camryGearMs = nowMs;
      live.camryGearValid = true;
    }
  }

  if (frame.identifier == 0x2D0 && frame.dlc >= 3) {
    uint8_t redundant = frame.data[2];
    uint8_t code = 0xFF;
    if (redundant == 0x01) code = 0;
    else if (redundant == 0x02) code = 1;
    else if (redundant == 0x04) code = 2;
    else if (redundant == 0x10) code = 3;
    if (code <= 3) {
      live.gearRedundantCode = code;
      live.camryGearRedundantValid = true;
    }
  }

  if (frame.identifier == 0x2C4 && frame.dlc >= 2) {
    uint16_t rpm = wordBE(frame.data[0], frame.data[1]);
    if (rpm <= 8000) {
      live.engineRPM = rpm;
      live.camryEngineMs = nowMs;
      live.camryEngineValid = true;
    }
  }

  if (frame.identifier == 0x3B9 && frame.dlc >= 1 && frame.data[0] <= 130) {
    live.engineCoolantF = frame.data[0] * 1.8f + 32.0f;
    live.camryCoolantMs = nowMs;
    live.camryCoolantValid = true;
  }
}

// ------------------------------ Diagnostics ----------------------------------
void serviceDiagnosticScheduler() {
  if (diag.active) {
    if (!diagnosticEnabled) {
      completeDiagnostic("USER_DISABLED");
      return;
    }
    if (nowMicros64() - diag.lastActivityUs > DIAGNOSTIC_TIMEOUT_US) {
      ++diagnosticTimeouts;
      completeDiagnostic("TIMEOUT");
    }
    return;
  }
  if (!loggingActive || !diagnosticEnabled || !twaiNormalMode ||
      vehicleProfile != PROFILE_PRIUS_GEN2 || profileConfidence < 80) return;
  if (millis() - lastDiagnosticCompleteMs < DIAGNOSTIC_GAP_MS) return;

  const size_t count = sizeof(DIAGNOSTIC_REQUESTS) / sizeof(DiagnosticRequest);
  startDiagnosticRequest(DIAGNOSTIC_REQUESTS[diagnosticIndex % count]);
  diagnosticIndex = (diagnosticIndex + 1) % count;
}

void startDiagnosticRequest(const DiagnosticRequest &request) {
  memset(&diag, 0, sizeof(diag));
  diag.active = true;
  diag.requestId = request.requestId;
  diag.responseId = request.requestId + 8;
  diag.service = request.service;
  diag.pid = request.pid;
  diag.requestTimeUs = nowMicros64();
  diag.lastActivityUs = diag.requestTimeUs;
  fastDiagResponseId = diag.responseId;
  fastDiagRequestTimeUs = diag.requestTimeUs;
  fastDiagActive = true;

  uint8_t data[8] = {0x02, request.service, request.pid, 0, 0, 0, 0, 0};
  if (!transmitCAN(request.requestId, data, 8, "DIAGNOSTIC_REQUEST")) {
    fastDiagActive = false;
    diag.active = false;
    lastDiagnosticCompleteMs = millis();
  }
}

void processDiagnosticFrame(const CapturedFrame &frame) {
  if (!diag.active || frame.identifier != diag.responseId || frame.timeUs < diag.requestTimeUs) return;
  if (frame.dlc == 0) return;
  uint8_t pciType = frame.data[0] >> 4;

  if (pciType == 0x0) {
    uint8_t length = frame.data[0] & 0x0F;
    if (length > 7 || length > frame.dlc - 1) {
      completeDiagnostic("BAD_SINGLE_FRAME");
      return;
    }
    bool positiveMatch = length >= 2 && frame.data[1] == diag.service + 0x40 && frame.data[2] == diag.pid;
    bool negativeMatch = length >= 3 && frame.data[1] == 0x7F && frame.data[2] == diag.service;
    if (!positiveMatch && !negativeMatch) {
      writeExternalDiagnosticFrame(frame, "EXTERNAL_DIAGNOSTIC_TRAFFIC");
      return; // Do not abort or extend the logger's active transaction.
    }
    diag.lastActivityUs = frame.timeUs;
    ++diag.frameCount;
    memcpy(diag.payload, &frame.data[1], length);
    diag.receivedLength = length;
    diag.expectedLength = length;
    if (length >= 3 && diag.payload[0] == 0x7F && diag.payload[2] == 0x78) {
      // UDS response-pending: retain the transaction and extend its inactivity
      // timeout. This does not transmit any additional request.
      return;
    }
    if (length >= 3 && diag.payload[0] == 0x7F) {
      ++diagnosticNegativeResponses;
      completeDiagnostic("NEGATIVE_RESPONSE");
    } else if (length < 2 || diag.payload[0] != diag.service + 0x40 || diag.payload[1] != diag.pid) {
      completeDiagnostic("RESPONSE_VALIDATION_ERROR");
    } else {
      completeDiagnostic("OK");
    }
    return;
  }

  if (pciType == 0x1) {
    if (frame.dlc >= 4 && (frame.data[2] != diag.service + 0x40 || frame.data[3] != diag.pid)) {
      writeExternalDiagnosticFrame(frame, "EXTERNAL_DIAGNOSTIC_TRAFFIC");
      return;
    }
    diag.lastActivityUs = frame.timeUs;
    ++diag.frameCount;
    diag.expectedLength = ((uint16_t)(frame.data[0] & 0x0F) << 8) | frame.data[1];
    if (diag.expectedLength <= 7 || frame.dlc < 8) {
      completeDiagnostic("BAD_FIRST_FRAME");
      return;
    }
    if (diag.expectedLength > sizeof(diag.payload)) {
      completeDiagnostic("PAYLOAD_TOO_LARGE");
      return;
    }
    diag.multiFrame = true;
    diag.receivedLength = min((uint16_t)6, diag.expectedLength);
    memcpy(diag.payload, &frame.data[2], diag.receivedLength);
    diag.nextSequence = 1;
    // Flow control was already sent immediately by the high-priority CAN_RX
    // task. Keeping it out of loop() avoids the 12-173 ms SD/TFT latency seen
    // in the supplied Prius capture and prevents duplicate FC frames.
    return;
  }

  if (pciType == 0x2 && diag.multiFrame) {
    diag.lastActivityUs = frame.timeUs;
    ++diag.frameCount;
    uint8_t sequence = frame.data[0] & 0x0F;
    if (sequence != diag.nextSequence) {
      completeDiagnostic("SEQUENCE_ERROR");
      return;
    }
    diag.nextSequence = (diag.nextSequence + 1) & 0x0F;
    uint16_t remaining = diag.expectedLength - diag.receivedLength;
    uint16_t count = min((uint16_t)7, remaining);
    memcpy(&diag.payload[diag.receivedLength], &frame.data[1], count);
    diag.receivedLength += count;
    if (diag.receivedLength >= diag.expectedLength) {
      if (diag.expectedLength < 2 || diag.payload[0] != diag.service + 0x40 || diag.payload[1] != diag.pid) {
        writeExternalDiagnosticFrame(frame, "EXTERNAL_DIAGNOSTIC_TRAFFIC");
        completeDiagnostic("REASSEMBLY_MISMATCH");
      } else {
        completeDiagnostic("OK");
      }
    }
  }
}

void completeDiagnostic(const char *status) {
  uint64_t completeTimeUs = nowMicros64();
  fastDiagActive = false;
  if (strcmp(status, "OK") == 0)
    decodeDiagnosticPayload(diag.responseId, diag.payload, diag.receivedLength);
  writeDiagnosticRecord(status, completeTimeUs);
  diag.active = false;
  lastDiagnosticCompleteMs = millis();
}

void decodeDiagnosticPayload(uint32_t responseId, const uint8_t *payload, uint16_t length) {
  (void)responseId;
  if (length < 2) return;
  uint8_t expectedService = diag.service + 0x40;
  if (payload[0] != expectedService || payload[1] != diag.pid) return;
  const uint8_t *data = &payload[2]; // A is data[0], B is data[1], etc.
  uint16_t dataLength = length - 2;

  if (diag.service == 0x01 && diag.pid == 0x0C && dataLength >= 2) {
    live.engineRPM = wordBE(data[0], data[1]) / 4;
    live.engineRPMMs = millis();
    live.engineRPMValid = true;
    return;
  }
  if (diag.service == 0x01 && diag.pid == 0x05 && dataLength >= 1) {
    live.engineCoolantF = (data[0] - 40.0f) * 1.8f + 32.0f;
    live.coolantMs = millis(); live.coolantValid = true; return;
  }
  if (diag.service == 0x01 && diag.pid == 0x0F && dataLength >= 1) {
    live.engineIntakeAirF = (data[0] - 40.0f) * 1.8f + 32.0f;
    live.engineIntakeMs = millis(); live.engineIntakeValid = true; return;
  }
  if (diag.service == 0x01 && diag.pid == 0x3C && dataLength >= 2) {
    live.catalystB1S1F = (wordBE(data[0], data[1]) / 10.0f - 40.0f) * 1.8f + 32.0f;
    live.catalystMs = millis(); live.catalystValid = true; return;
  }
  if (diag.service != 0x21) return;
  if (diag.pid == 0xC3) decodeC3(data, dataLength);
  else if (diag.pid == 0xC4) decodeC4(data, dataLength);
  else if (diag.pid == 0xCE) decodeCE(data, dataLength);
  else if (diag.pid == 0xCF) decodeCF(data, dataLength);
  else if (diag.pid == 0xD0) decodeD0(data, dataLength);
}

void decodeC3(const uint8_t *d, uint16_t n) {
  if (n < 31) return; // Through AE.
  live.mg2RPM = (int32_t)wordBE(d[0], d[1]) - 16383;
  live.mg1RPM = (int32_t)wordBE(d[6], d[7]) - 16383;
  live.engineRPM = wordBE(d[14], d[15]);
  live.engineRPMMs = millis();
  live.engineRPMValid = true;
  live.socPct = 0.392f * d[18];
  live.mg1InvF = 1.8f * d[24] - 58.0f;
  live.mg2InvF = 1.8f * d[25] - 58.0f;
  live.mg1StatorF = 1.8f * d[26] - 58.0f;
  live.mg2StatorF = 1.8f * d[27] - 58.0f;
  live.packVolts = 2.0f * d[28];
  live.packAmps = 2.0f * d[30] - 256.0f;
  live.packKW = live.packVolts * live.packAmps / 1000.0f;
  live.c3Ms = millis();
  live.c3Valid = true;
}

void decodeC4(const uint8_t *d, uint16_t n) {
  if (n < 6) return;
  float beforeBoost = 2.0f * d[3];
  float afterBoost = 2.0f * d[4];
  float converterF = 1.8f * d[5] - 58.0f;
  if (beforeBoost < 0 || afterBoost < 0 || converterF < -1000) return;
  live.converterTempF = converterF;
  live.c4Ms = millis();
  live.c4Valid = true;
}

void decodeCE(const uint8_t *d, uint16_t n) {
  if (n < 31) return;
  live.socPct = 0.5f * d[0];
  live.packAmps = 2.56f * d[1] + 0.01f * d[2] - 327.68f;
  float sum = 0.0f;
  for (uint8_t i = 0; i < 14; ++i) {
    uint8_t p = 3 + i * 2;
    live.blockVolts[i] = 2.56f * d[p] + 0.01f * d[p + 1] - 327.68f;
    sum += live.blockVolts[i];
  }
  live.packVolts = sum;
  live.packKW = live.packVolts * live.packAmps / 1000.0f;
  live.ceMs = millis();
  live.ceValid = true;
}

void decodeCF(const uint8_t *d, uint16_t n) {
  if (n < 16) return;
  live.intakeTempF = rawTemperatureF(d[0], d[1]);
  live.auxVolts = 0.2f * d[3] - 25.6f;
  live.deltaSocPct = 0.01f * d[6];
  live.fanLevel = d[8];
  live.hvTemp1F = rawTemperatureF(d[10], d[11]);
  live.hvTemp2F = rawTemperatureF(d[12], d[13]);
  live.hvTemp3F = rawTemperatureF(d[14], d[15]);
  live.hvAvgF = (live.hvTemp1F + live.hvTemp2F + live.hvTemp3F) / 3.0f;
  live.cfMs = millis();
  live.cfValid = true;
}

void decodeD0(const uint8_t *d, uint16_t n) {
  if (n < 29) return;
  live.blockMinV = 2.56f * d[9] + 0.01f * d[10] - 327.68f;
  live.blockMinNumber = d[11] + 1;
  live.blockMaxV = 2.56f * d[12] + 0.01f * d[13] - 327.68f;
  live.blockMaxNumber = d[14] + 1;
  live.blockDeltaV = live.blockMaxV - live.blockMinV;
  for (uint8_t i = 0; i < 14; ++i) live.internalResistance[i] = 0.001f * d[15 + i];
  live.d0Ms = millis();
  live.d0Valid = true;
}

// -------------------------------- SD logging ---------------------------------
const char *sessionName() {
  return sessionDir[0] ? &sessionDir[8] : "NONE";
}

void setLoggerStatus(const char *status) {
  if (status == nullptr) status = "UNKNOWN";
  strncpy(loggerStatus, status, sizeof(loggerStatus) - 1);
  loggerStatus[sizeof(loggerStatus) - 1] = '\0';
}

bool sessionTrafficRecent() {
  if (!loggingActive || !sessionHasCanTraffic || sessionLastCanUs == 0) return false;
  uint64_t nowUs = nowMicros64();
  return nowUs >= sessionLastCanUs && nowUs - sessionLastCanUs <= CAN_TRAFFIC_RECENT_US;
}

bool initializeSD() {
  sdSPI.begin(SD_SCK_PIN, SD_MISO_PIN, SD_MOSI_PIN, SD_CS_PIN);
  // v2.4.0 used the SD library default of five descriptors while retaining six
  // session files and opening metadata files. Ten provides measured peak-seven
  // headroom without reserving the 16 descriptors that starved BLE in v2.4.1.
  if (!SD.begin(SD_CS_PIN, sdSPI, SD_SPI_FREQUENCY, "/sd", SD_MAX_OPEN_FILES, false)) {
    Serial.println("# SD initialization failed");
    setLoggerStatus("SD MOUNT FAILED");
    return false;
  }
  if (!SD.exists("/CANLOG") && !SD.mkdir("/CANLOG")) {
    Serial.println("# SD /CANLOG creation failed");
    setLoggerStatus("SD DIR FAILED");
    return false;
  }
  // A powered bench test no longer consumes a session number or creates files.
  sessionDir[0] = '\0';
  setLoggerStatus("READY / STOPPED");
  Serial.printf("# SD READY,max_open_files=%u,session=deferred\n", SD_MAX_OPEN_FILES);
  return true;
}

bool createSessionDirectory() {
  for (uint16_t i = 1; i <= 9999; ++i) {
    snprintf(sessionDir, sizeof(sessionDir), "/CANLOG/S%04u", i);
    if (!SD.exists(sessionDir)) {
      if (SD.mkdir(sessionDir)) return true;
      sessionDir[0] = '\0';
      return false;
    }
  }
  sessionDir[0] = '\0';
  return false;
}

bool openRawFile() {
  if (rawFile) rawFile.close();
  snprintf(rawPath, sizeof(rawPath), "%s/RAW_%03u.TCB", sessionDir, rawFileIndex);
  rawFile = SD.open(rawPath, FILE_WRITE);
  if (!rawFile) return false;
  const uint8_t header[16] = {'T','C','B','1', 1,24,0,0, 0,0,0,0, 0,0,0,0};
  if (rawFile.write(header, sizeof(header)) != sizeof(header)) {
    rawFile.close();
    return false;
  }
  return true;
}

void closeSessionFiles() {
  if (rawFile) rawFile.close();
  if (decodedFile) decodedFile.close();
  if (diagnosticFile) diagnosticFile.close();
  if (eventFile) eventFile.close();
  if (syncFile) syncFile.close();
  if (externalDiagnosticFile) externalDiagnosticFile.close();
}

void cleanupFailedSession() {
  closeSessionFiles();
  if (sessionDir[0] == 0) return;
  const char *fileNames[] = {
    "RAW_000.TCB", "DECODED.CSV", "DIAGNOSTICS.CSV", "EVENTS.CSV",
    "SYNC.CSV", "EXTERNAL_DIAGNOSTICS.CSV", "SESSION.OPEN"
  };
  char path[72];
  for (const char *name : fileNames) {
    snprintf(path, sizeof(path), "%s/%s", sessionDir, name);
    if (SD.exists(path)) SD.remove(path);
  }
  SD.rmdir(sessionDir);
  sessionDir[0] = '\0';
  rawPath[0] = '\0';
}

bool failLogStart(const char *stage) {
  Serial.printf("# LOG START FAILED,%s\n", stage);
  cleanupFailedSession();
  manifestClosed = true;
  setLoggerStatus("LOG START FAILED");
  return false;
}

bool startLogging() {
  if (loggingActive) return true;
  if (!sdReady) {
    Serial.println("# LOG START FAILED,SD_NOT_READY");
    setLoggerStatus("SD NOT READY");
    return false;
  }

  uint64_t cardBytes = SD.cardSize();
  uint64_t usedBytes = SD.usedBytes();
  uint64_t freeBytes = cardBytes > usedBytes ? cardBytes - usedBytes : 0;
  if (freeBytes < MIN_SD_FREE_BYTES) {
    Serial.printf("# LOG START FAILED,SD_SPACE_LOW,%llu\n", (unsigned long long)freeBytes);
    setLoggerStatus("SD SPACE LOW");
    return false;
  }

  sessionDir[0] = '\0';
  if (!createSessionDirectory()) return failLogStart("CREATE_SESSION_DIRECTORY");
  rawFileIndex = 0;
  if (!openRawFile()) return failLogStart("RAW_000.TCB");

  char path[64];
  snprintf(path, sizeof(path), "%s/DECODED.CSV", sessionDir);
  decodedFile = SD.open(path, FILE_WRITE);
  snprintf(path, sizeof(path), "%s/DIAGNOSTICS.CSV", sessionDir);
  diagnosticFile = SD.open(path, FILE_WRITE);
  snprintf(path, sizeof(path), "%s/EVENTS.CSV", sessionDir);
  eventFile = SD.open(path, FILE_WRITE);
  snprintf(path, sizeof(path), "%s/SYNC.CSV", sessionDir);
  syncFile = SD.open(path, FILE_WRITE);
  snprintf(path, sizeof(path), "%s/EXTERNAL_DIAGNOSTICS.CSV", sessionDir);
  externalDiagnosticFile = SD.open(path, FILE_WRITE);
  if (!decodedFile || !diagnosticFile || !eventFile || !syncFile || !externalDiagnosticFile) {
    return failLogStart("SESSION_FILE_OPEN");
  }

  decodedFile.println("Time_ms,Profile,ProfileConfidence,SOC_pct,Pack_V,Pack_A,Pack_kW,MG1_RPM,MG2_RPM,Engine_RPM,Gear_Candidate,Engine_Coolant_F,Engine_Intake_Air_F,Catalyst_B1S1_F,Converter_Temp_F,MG1_Inv_F,MG2_Inv_F,MG1_Temp_F,MG2_Temp_F,HV_T1_F,HV_T2_F,HV_T3_F,HV_Avg_F,Battery_Intake_F,Aux_V,Fan_Level,Delta_SOC_pct,Block_Min_V,Block_Min_Number,Block_Max_V,Block_Max_Number,Block_Delta_V,B01_V,B02_V,B03_V,B04_V,B05_V,B06_V,B07_V,B08_V,B09_V,B10_V,B11_V,B12_V,B13_V,B14_V,DataQuality");
  diagnosticFile.println("Transaction,RequestTime_us,CompleteTime_us,RequestID,ResponseID,Service,PID,Status,PayloadLength,PayloadHex,FrameCount,ResponseTime_ms");
  eventFile.println("Time_us,Severity,Event,Details");
  syncFile.println("Sequence,ESP_Receive_us,ESP_Send_us,Source");
  externalDiagnosticFile.println("Time_us,CAN_ID,DLC,DataHex,Classification");

  rawSequence = 0;
  diagnosticSequence = 0;
  sdLogDrops = 0;
  sdLogDroppedFrames = 0;
  sessionHasCanTraffic = false;
  sessionStartUs = nowMicros64();
  sessionFirstCanUs = 0;
  sessionLastCanUs = 0;
  sessionStartReceivedFrames = receivedFrameCount;
  sessionStartTransmittedFrames = transmittedFrameCount;
  loggingActive = true;
  manifestClosed = false;
  setLoggerStatus("ARMED / WAIT CAN");
  snprintf(path, sizeof(path), "%s/SESSION.OPEN", sessionDir);
  File marker = SD.open(path, FILE_WRITE);
  if (marker) {
    marker.println("Capture was open. A clean stop removes this marker.");
    marker.close();
  }
  writeReadme();
  writeSignalsDictionary();
  writeManifest(false);
  writeCheckpoint(false);
  writeEvent("INFO", "LOGGING_STARTED", String(sessionDir) + ";state=ARMED_WAIT_CAN");
  for (uint8_t i = 0; i < pendingSyncCount; ++i) writeSyncRecord(pendingSync[i], "BLE_PRESTART");
  pendingSyncCount = 0;
  Serial.printf("# LOG STARTED,%s,ARMED_WAIT_CAN\n", sessionDir);
  return true;
}

void stopLogging(bool closedCleanly) {
  if (!loggingActive) return;
  if (diagnosticEnabled || twaiNormalMode)
    setDiagnosticCapture(false, "Logging stopped; unrecorded diagnostic traffic prevented");
  String stopDetails = closedCleanly ? "clean" : "unclean";
  stopDetails += sessionHasCanTraffic ? ";traffic=yes" : ";traffic=no;empty_bench_session=yes";
  writeEvent("INFO", "LOGGING_STOPPED", stopDetails);
  flushLogFiles();
  writeManifest(closedCleanly);
  writeCheckpoint(closedCleanly);
  closeSessionFiles();
  loggingActive = false;
  manifestClosed = true;
  if (closedCleanly) {
    char markerPath[64];
    snprintf(markerPath, sizeof(markerPath), "%s/SESSION.OPEN", sessionDir);
    if (SD.exists(markerPath)) SD.remove(markerPath);
  }
  char closedStatus[28];
  snprintf(closedStatus, sizeof(closedStatus), "%s CLOSED%s", sessionName(),
           sessionHasCanTraffic ? "" : " EMPTY");
  setLoggerStatus(closedStatus);
  Serial.printf("# LOG CLOSED,%s,records=%llu,traffic=%s\n", sessionDir,
                (unsigned long long)rawSequence, sessionHasCanTraffic ? "yes" : "no");
}

void printSDDirectory(const char *dirname, uint8_t levels) {
  File root = SD.open(dirname);
  if (!root || !root.isDirectory()) {
    Serial.printf("# SD DIR OPEN FAILED,%s\n", dirname);
    return;
  }
  File entry = root.openNextFile();
  while (entry) {
    String entryPath = entry.path();
    bool isDirectory = entry.isDirectory();
    uint64_t entrySize = entry.size();
    entry.close();
    if (isDirectory) {
      Serial.printf("# SD DIR,%s\n", entryPath.c_str());
      if (levels) printSDDirectory(entryPath.c_str(), levels - 1);
    } else {
      Serial.printf("# SD FILE,%s,%llu\n", entryPath.c_str(), entrySize);
    }
    entry = root.openNextFile();
  }
  root.close();
}

void printSDCardSummary() {
  Serial.printf("# SD CARD,%llu MB total,%llu MB used\n",
                SD.cardSize() / (1024ULL * 1024ULL),
                SD.usedBytes() / (1024ULL * 1024ULL));
  if (PRINT_SD_DIRECTORY_AT_BOOT) {
    Serial.println("# SD DIRECTORY LIST BEGIN");
    printSDDirectory("/", 3);
    Serial.println("# SD DIRECTORY LIST END");
  }
}

void rotateRawFileIfNeeded() {
  if (!loggingActive || !rawFile || rawFile.size() < RAW_ROTATE_BYTES) return;
  rawFile.flush();
  rawFile.close();
  ++rawFileIndex;
  if (!openRawFile()) {
    ++sdLogDrops;
    writeEvent("ERROR", "RAW_ROTATION_FAILED", String(rawFileIndex));
  }
}

void writeRawBatch(const CapturedFrame *frames, size_t count) {
  if (!loggingActive || !rawFile || count == 0) return;
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
  rawSequence += count;
  size_t bytes = count * sizeof(CapturedFrame);
  size_t written = rawFile.write((const uint8_t *)frames, bytes);
  if (written != bytes) {
    ++sdLogDrops;
    sdLogDroppedFrames += count - (written / sizeof(CapturedFrame));
  }
  if (firstTrafficInBatch)
    writeEvent("INFO", "CAN_TRAFFIC_STARTED", "First received CAN frame committed to RAW");
  rotateRawFileIfNeeded();
}

void printCsvFloat(File &file, bool valid, float value, uint8_t decimals) {
  if (valid) file.print(value, decimals);
}

void printCsvInt(File &file, bool valid, int32_t value) {
  if (valid) file.print(value);
}

const char *dataQualityLabel() {
  uint32_t nowMs = millis();
  if (vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1) {
    if ((live.camryGearValid && nowMs - live.camryGearMs < 2000) ||
        (live.camryEngineValid && nowMs - live.camryEngineMs < 2000) ||
        (live.camryCoolantValid && nowMs - live.camryCoolantMs < 2000))
      return "CAMRY_PASSIVE_PROBABLE";
    return "CAMRY_STALE";
  }
  if (vehicleProfile != PROFILE_PRIUS_GEN2) return "PROFILE_AMBIGUOUS";
  if (live.ceValid && live.cfValid && nowMs - live.ceMs < 2000 && nowMs - live.cfMs < 2000)
    return "DIAGNOSTIC_COMPLETE";
  if ((live.passiveElectricalValid && nowMs - live.passiveElectricalMs < 2000) ||
      (live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000))
    return "PASSIVE_CANDIDATE";
  return "STALE";
}

void writeDecodedSample() {
  uint32_t nowMs = millis();
  bool activeCanTraffic = sessionTrafficRecent();
  bool electrical = (live.ceValid && nowMs - live.ceMs < 2000) ||
                    (live.c3Valid && nowMs - live.c3Ms < 2000) ||
                    (live.passiveElectricalValid && nowMs - live.passiveElectricalMs < 2000);
  bool soc = (live.ceValid && nowMs - live.ceMs < 2000) ||
             (live.c3Valid && nowMs - live.c3Ms < 2000) ||
             (live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000);
  bool c3 = live.c3Valid && nowMs - live.c3Ms < 2000;
  bool c4 = live.c4Valid && nowMs - live.c4Ms < 5000;
  bool camryEngine = live.camryEngineValid && nowMs - live.camryEngineMs < 2000;
  bool camryGear = live.camryGearValid && nowMs - live.camryGearMs < 2000;
  bool camryCoolant = live.camryCoolantValid && nowMs - live.camryCoolantMs < 2000;
  bool engine = (live.engineRPMValid && nowMs - live.engineRPMMs < 5000) || camryEngine;
  bool coolant = (live.coolantValid && nowMs - live.coolantMs < 5000) || camryCoolant;
  bool engineIntake = live.engineIntakeValid && nowMs - live.engineIntakeMs < 5000;
  bool catalyst = live.catalystValid && nowMs - live.catalystMs < 5000;
  bool cf = live.cfValid && nowMs - live.cfMs < 2000;
  bool d0 = live.d0Valid && nowMs - live.d0Ms < 5000;
  bool ce = live.ceValid && nowMs - live.ceMs < 2000;
  bool passiveTemps = live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000;

  if (USB_DECODED_CSV && activeCanTraffic) {
    Serial.printf("D,%lu,%s,%u,", (unsigned long)nowMs, profileLabel(vehicleProfile), profileConfidence);
    if (soc) Serial.printf("%.1f", live.socPct);
    Serial.print(','); if (electrical) Serial.printf("%.1f", live.packVolts);
    Serial.print(','); if (electrical) Serial.printf("%.2f", live.packAmps);
    Serial.print(','); if (electrical) Serial.printf("%.3f", live.packKW);
    Serial.printf(",%s\n", dataQualityLabel());
  }

  // Do not fill an armed bench session with repeated UNKNOWN/empty rows. Raw
  // capture remains complete, and decoded sampling resumes with live traffic.
  if (!loggingActive || !decodedFile || !activeCanTraffic) return;
  decodedFile.print(nowMs); decodedFile.print(',');
  decodedFile.print(profileLabel(vehicleProfile)); decodedFile.print(',');
  decodedFile.print(profileConfidence); decodedFile.print(',');
  printCsvFloat(decodedFile, soc, live.socPct, 2); decodedFile.print(',');
  printCsvFloat(decodedFile, electrical, live.packVolts, 2); decodedFile.print(',');
  printCsvFloat(decodedFile, electrical, live.packAmps, 2); decodedFile.print(',');
  printCsvFloat(decodedFile, electrical, live.packKW, 3); decodedFile.print(',');
  printCsvInt(decodedFile, c3, live.mg1RPM); decodedFile.print(',');
  printCsvInt(decodedFile, c3, live.mg2RPM); decodedFile.print(',');
  printCsvInt(decodedFile, engine, live.engineRPM); decodedFile.print(',');
  if (camryGear) decodedFile.print(gearLabel(live.gearCode));
  decodedFile.print(',');
  printCsvFloat(decodedFile, coolant, live.engineCoolantF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, engineIntake, live.engineIntakeAirF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, catalyst, live.catalystB1S1F, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, c4, live.converterTempF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, c3, live.mg1InvF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, c3, live.mg2InvF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, c3, live.mg1StatorF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, c3, live.mg2StatorF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf || passiveTemps, live.hvTemp1F, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf || passiveTemps, live.hvTemp2F, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf, live.hvTemp3F, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf || passiveTemps, live.hvAvgF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf, live.intakeTempF, 1); decodedFile.print(',');
  printCsvFloat(decodedFile, cf, live.auxVolts, 2); decodedFile.print(',');
  printCsvInt(decodedFile, cf, live.fanLevel); decodedFile.print(',');
  printCsvFloat(decodedFile, cf, live.deltaSocPct, 2); decodedFile.print(',');
  printCsvFloat(decodedFile, d0, live.blockMinV, 2); decodedFile.print(',');
  printCsvInt(decodedFile, d0, live.blockMinNumber); decodedFile.print(',');
  printCsvFloat(decodedFile, d0, live.blockMaxV, 2); decodedFile.print(',');
  printCsvInt(decodedFile, d0, live.blockMaxNumber); decodedFile.print(',');
  printCsvFloat(decodedFile, d0, live.blockDeltaV, 3);
  for (uint8_t i = 0; i < 14; ++i) {
    decodedFile.print(',');
    printCsvFloat(decodedFile, ce, live.blockVolts[i], 2);
  }
  decodedFile.print(','); decodedFile.println(dataQualityLabel());
}

void writeDiagnosticRecord(const char *status, uint64_t completeTimeUs) {
  ++diagnosticSequence;
  if (!loggingActive || !diagnosticFile) return;
  diagnosticFile.print(diagnosticSequence); diagnosticFile.print(',');
  diagnosticFile.printf("%llu", (unsigned long long)diag.requestTimeUs); diagnosticFile.print(',');
  diagnosticFile.printf("%llu", (unsigned long long)completeTimeUs); diagnosticFile.print(',');
  diagnosticFile.print(diag.requestId, HEX); diagnosticFile.print(',');
  diagnosticFile.print(diag.responseId, HEX); diagnosticFile.print(',');
  if (diag.service < 16) diagnosticFile.print('0');
  diagnosticFile.print(diag.service, HEX); diagnosticFile.print(',');
  if (diag.pid < 16) diagnosticFile.print('0');
  diagnosticFile.print(diag.pid, HEX); diagnosticFile.print(',');
  diagnosticFile.print(status); diagnosticFile.print(',');
  diagnosticFile.print(diag.receivedLength); diagnosticFile.print(',');
  for (uint16_t i = 0; i < diag.receivedLength; ++i) {
    if (diag.payload[i] < 16) diagnosticFile.print('0');
    diagnosticFile.print(diag.payload[i], HEX);
  }
  diagnosticFile.print(','); diagnosticFile.print(diag.frameCount); diagnosticFile.print(',');
  diagnosticFile.println((completeTimeUs - diag.requestTimeUs) / 1000.0f, 3);
}

void writeEvent(const char *severity, const char *eventName, const String &details) {
  Serial.printf("# EVENT,%llu,%s,%s,%s\n", (unsigned long long)nowMicros64(), severity, eventName, details.c_str());
  if (!loggingActive || !eventFile) return;
  String clean = details;
  clean.replace('"', '\'');
  eventFile.printf("%llu", (unsigned long long)nowMicros64()); eventFile.print(',');
  eventFile.print(severity); eventFile.print(','); eventFile.print(eventName); eventFile.print(',');
  eventFile.print('"'); eventFile.print(clean); eventFile.println('"');
}

void writeReadme() {
  char path[64]; snprintf(path, sizeof(path), "%s/README.TXT", sessionDir);
  File file = SD.open(path, FILE_WRITE);
  if (!file) return;
  file.println("ToyotaHybridCAN Capture Package v1.4 / firmware v2.4.2");
  file.println("Upload the entire session folder plus the Android CAPTURE_SYNC.json and MP4 to the Windows processor or ChatGPT.");
  file.println("Session files: MANIFEST.JSON, CHECKPOINT.JSON, SIGNALS.CSV, RAW_nnn.TCB, DECODED.CSV, DIAGNOSTICS.CSV, EXTERNAL_DIAGNOSTICS.CSV, EVENTS.CSV and SYNC.CSV.");
  file.println("TCB1 format: 16-byte header, then packed 24-byte little-endian records: uint64 time_us, uint32 CAN_ID, uint8 data[8], uint8 DLC, uint8 extended, uint8 RTR, uint8 direction (0 RX, 1 TX).");
  file.println("If SESSION.OPEN remains, power was removed before a clean stop; use CHECKPOINT.JSON, or CHECKPOINT.OLD if JSON is absent, for the latest recoverable counters.");
  file.println("An explicitly started session may be ARMED / WAIT CAN before vehicle traffic. Empty decoded rows are suppressed until CAN arrives; RAW remains authoritative.");
  file.println("Camry AHV40 gear, engine RPM and coolant fields are passive PROBABLE candidates derived from the supplied 2007 capture, not confirmed DBC definitions.");
  file.println("SYNC.CSV uses the BLE protocol timestamps E2/E3. The companion CAPTURE_SYNC.json supplies Android T1/T4 and video anchors; fit every session independently.");
  file.println("Suggested request:");
  file.println("Decode this Toyota hybrid capture. Recalculate decoded signals from RAW and DIAGNOSTICS, compare passive and diagnostic values, identify timeouts/drops, and separate confirmed findings from candidates.");
  file.println("Safety: firmware contains read-only diagnostic requests; no actuator, fan-control, write, clear, reset or coding commands.");
  file.close();
}

void writeSignalsDictionary() {
  char path[64]; snprintf(path, sizeof(path), "%s/SIGNALS.CSV", sessionDir);
  File file = SD.open(path, FILE_WRITE);
  if (!file) return;
  file.println("Profile,SourceType,CAN_ID,RequestID,ResponseID,Service,PID,Signal,DataStart,Length,Endian,Signed,Scale,Offset,Unit,Formula,Confidence,Source,SafetyClass");
  file.println("PRIUS_GEN2,BROADCAST,03B,,,,,PACK_CURRENT,B0,12bit,BIG,YES,0.1,0,A,sign12(B0:B1)*0.1,CANDIDATE,2004_CAPTURE,PASSIVE_BROADCAST");
  file.println("PRIUS_GEN2,BROADCAST,03B,,,,,PACK_VOLTAGE,B2,2,BIG,NO,1,0,V,word(B2:B3),CANDIDATE,2004_CAPTURE,PASSIVE_BROADCAST");
  file.println("PRIUS_GEN2,BROADCAST,3CB,,,,,HV_SOC,B3,1,NONE,NO,0.5,0,percent,B3*0.5,CANDIDATE,2004_CAPTURE,PASSIVE_BROADCAST");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG2_RPM,A,2,BIG,YES,1,-16383,rpm,word(A:B)-16383,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG1_RPM,G,2,BIG,YES,1,-16383,rpm,word(G:H)-16383,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,ENGINE_RPM,O,2,BIG,NO,1,0,rpm,word(O:P),CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E0,7E8,01,05,ENGINE_COOLANT,A,1,NONE,NO,1.8,-40,F,(A-40)*1.8+32,PROBABLE,SAE_OBD_MODE01,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E0,7E8,01,0F,ENGINE_INTAKE_AIR,A,1,NONE,NO,1.8,-40,F,(A-40)*1.8+32,PROBABLE,SAE_OBD_MODE01,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E0,7E8,01,3C,CATALYST_B1S1,A,2,BIG,NO,0.18,-40,F,(word(A:B)/10-40)*1.8+32,PROBABLE,SAE_OBD_MODE01,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C4,CONVERTER_TEMP,F,1,NONE,NO,1.8,-58,F,F*1.8-58,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG1_INVERTER_TEMP,Y,1,NONE,NO,1.8,-58,F,Y*1.8-58,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG2_INVERTER_TEMP,Z,1,NONE,NO,1.8,-58,F,Z*1.8-58,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG1_TEMP,AA,1,NONE,NO,1.8,-58,F,AA*1.8-58,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E2,7EA,21,C3,MG2_TEMP,AB,1,NONE,NO,1.8,-58,F,AB*1.8-58,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E3,7EB,21,CE,HV_SOC,A,1,NONE,NO,0.5,0,percent,A*0.5,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E3,7EB,21,CE,HV_CURRENT,B,2,BIG,YES,0.01,-327.68,A,2.56*B+0.01*C-327.68,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E3,7EB,21,CF,HV_TEMP_1,K,2,BIG,NO,0.018,-557.824,F,word(K:L)*9/500-557.824,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E3,7EB,21,CF,HV_TEMP_2,M,2,BIG,NO,0.018,-557.824,F,word(M:N)*9/500-557.824,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("PRIUS_GEN2,DIAGNOSTIC,,7E3,7EB,21,CF,HV_TEMP_3,O,2,BIG,NO,0.018,-557.824,F,word(O:P)*9/500-557.824,CANDIDATE,gerdbremer_nhw20,READ_ONLY_DIAGNOSTIC");
  file.println("CAMRY_HYBRID_GEN1,BROADCAST,120,,,,,GEAR,B5_LOW_NIBBLE,1,NONE,NO,1,0,enum,0=P;1=R;2=N;3=D,PROBABLE,2007_AHV40_CAPTURE,PASSIVE_BROADCAST");
  file.println("CAMRY_HYBRID_GEN1,BROADCAST,2D0,,,,,GEAR_REDUNDANT,B2,1,NONE,NO,1,0,enum,01=P;02=R;04=N;10=D,PROBABLE,2007_AHV40_CAPTURE,PASSIVE_BROADCAST");
  file.println("CAMRY_HYBRID_GEN1,BROADCAST,2C4,,,,,ENGINE_RPM,B0,2,BIG,NO,1,0,rpm,word(B0:B1),PROBABLE,2007_AHV40_CAPTURE,PASSIVE_BROADCAST");
  file.println("CAMRY_HYBRID_GEN1,BROADCAST,3B9,,,,,ENGINE_COOLANT,B0,1,NONE,NO,1.8,32,F,B0*1.8+32,PROBABLE,2007_AHV40_CAPTURE,PASSIVE_BROADCAST");
  file.close();
}

void writeManifest(bool closedCleanly) {
  if (!sdReady || sessionDir[0] == 0) return;
  char path[64]; snprintf(path, sizeof(path), "%s/MANIFEST.JSON", sessionDir);
  if (SD.exists(path)) SD.remove(path);
  File file = SD.open(path, FILE_WRITE);
  if (!file) return;
  file.println("{");
  file.println("  \"format\": \"ToyotaHybridCAN-Capture\",");
  file.println("  \"format_version\": \"1.4\",");
  file.println("  \"firmware\": \"Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger\",");
  file.println("  \"firmware_version\": \"2.4.2\",");
  file.println("  \"raw_format\": \"TCB1_24_byte_records\",");
  file.println("  \"capture_date_utc\": null,");
  file.println("  \"time_source\": \"ESP32_microseconds_since_boot_with_optional_BLE_sync\",");
  file.println("  \"ble_sync_protocol\": \"ToyotaCYD-Sync/1\",");
  file.println("  \"ble_service_uuid\": \"6ed9f000-4f21-4c8c-a8a7-923c86b40001\",");
  file.println("  \"counter_scope\": \"since_boot\",");
  const char *sessionState = closedCleanly ? "CLOSED" :
                             (sessionHasCanTraffic ? "LOGGING" : "ARMED_WAIT_CAN");
  file.printf("  \"session_state\": \"%s\",\n", sessionState);
  file.printf("  \"session_had_can_traffic\": %s,\n", sessionHasCanTraffic ? "true" : "false");
  file.printf("  \"session_start_us\": %llu,\n", (unsigned long long)sessionStartUs);
  file.printf("  \"session_first_can_us\": %llu,\n", (unsigned long long)sessionFirstCanUs);
  file.printf("  \"session_last_can_us\": %llu,\n", (unsigned long long)sessionLastCanUs);
  file.printf("  \"session_duration_us\": %llu,\n",
              (unsigned long long)(nowMicros64() - sessionStartUs));
  file.printf("  \"vehicle_profile\": \"%s\",\n", profileLabel(vehicleProfile));
  file.printf("  \"profile_confidence_pct\": %u,\n", profileConfidence);
  const char *modelCode = vehicleProfile == PROFILE_PRIUS_GEN2 ? "NHW20 candidate" :
                          vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1 ? "AHV40 candidate" : "unresolved";
  file.printf("  \"vehicle_model_code\": \"%s\",\n", modelCode);
  file.println("  \"can_bitrate\": 500000,");
  file.printf("  \"twai_mode_at_close\": \"%s\",\n", twaiNormalMode ? "NORMAL_DIAGNOSTIC" : "LISTEN_ONLY");
  file.println("  \"twai_default_mode\": \"LISTEN_ONLY\",");
  file.println("  \"can_tx_gpio\": 25,");
  file.println("  \"can_rx_gpio\": 32,");
  file.println("  \"sd_spi_controller\": \"HSPI separate from TFT_eSPI\",");
  file.println("  \"sd_sck_gpio\": 18,");
  file.println("  \"sd_miso_gpio\": 19,");
  file.println("  \"sd_mosi_gpio\": 23,");
  file.println("  \"sd_cs_gpio\": 5,");
  file.printf("  \"sd_max_open_files\": %u,\n", SD_MAX_OPEN_FILES);
  file.println("  \"touch_cs_gpio\": 33,");
  file.println("  \"touch_calibration\": [295,3524,310,3487,7],");
  file.println("  \"transceiver\": \"SN65HVD230_VP230\",");
  file.println("  \"obd_can_h_pin\": 6,");
  file.println("  \"obd_can_l_pin\": 14,");
  file.println("  \"termination_120_ohm_installed\": false,");
  file.printf("  \"diagnostic_reading_enabled_at_close\": %s,\n", diagnosticEnabled ? "true" : "false");
  file.println("  \"control_commands_enabled\": false,");
  file.println("  \"camry_diagnostic_requests_enabled\": false,");
  file.println("  \"isotp_flow_control_path\": \"high_priority_CAN_RX_task\",");
  file.printf("  \"raw_file_count\": %u,\n", rawFileIndex + 1);
  file.printf("  \"frames_processed_by_logger\": %llu,\n", (unsigned long long)rawSequence);
  file.printf("  \"session_received_frames\": %lu,\n",
              (unsigned long)(receivedFrameCount - sessionStartReceivedFrames));
  file.printf("  \"session_transmitted_frames\": %lu,\n",
              (unsigned long)(transmittedFrameCount - sessionStartTransmittedFrames));
  file.printf("  \"received_frames\": %lu,\n", (unsigned long)receivedFrameCount);
  file.printf("  \"transmitted_frames\": %lu,\n", (unsigned long)transmittedFrameCount);
  file.printf("  \"can_queue_drops\": %lu,\n", (unsigned long)canQueueDrops);
  file.printf("  \"diagnostic_queue_drops\": %lu,\n", (unsigned long)diagnosticQueueDrops);
  file.printf("  \"sd_log_drops\": %lu,\n", (unsigned long)sdLogDrops);
  file.printf("  \"sd_log_dropped_frames_estimate\": %lu,\n", (unsigned long)sdLogDroppedFrames);
  file.printf("  \"isotp_flow_control_frames\": %lu,\n", (unsigned long)isotpFlowControlCount);
  file.printf("  \"isotp_flow_control_failures\": %lu,\n", (unsigned long)isotpFlowControlFailures);
  file.printf("  \"isotp_flow_control_max_us\": %lu,\n", (unsigned long)isotpFlowControlMaxUs);
  double flowAverageUs = isotpFlowControlCount ? (double)isotpFlowControlTotalUs / isotpFlowControlCount : 0.0;
  file.printf("  \"isotp_flow_control_average_us\": %.1f,\n", flowAverageUs);
  file.printf("  \"twai_rx_missed_count\": %lu,\n", (unsigned long)twaiRxMissedCount);
  file.printf("  \"twai_rx_overrun_count\": %lu,\n", (unsigned long)twaiRxOverrunCount);
  file.printf("  \"twai_tx_failed_count\": %lu,\n", (unsigned long)twaiTxFailedCount);
  file.printf("  \"twai_arbitration_lost_count\": %lu,\n", (unsigned long)twaiArbLostCount);
  file.printf("  \"twai_bus_error_count\": %lu,\n", (unsigned long)twaiBusErrorCount);
  file.printf("  \"twai_bus_off_events\": %lu,\n", (unsigned long)twaiBusOffEvents);
  file.printf("  \"diagnostic_timeouts\": %lu,\n", (unsigned long)diagnosticTimeouts);
  file.printf("  \"diagnostic_negative_responses\": %lu,\n", (unsigned long)diagnosticNegativeResponses);
  file.printf("  \"external_diagnostic_frames\": %lu,\n", (unsigned long)externalDiagnosticFrames);
  file.printf("  \"external_tester_events\": %lu,\n", (unsigned long)externalTesterEvents);
  file.printf("  \"ble_connected_at_close\": %s,\n", bleConnected ? "true" : "false");
  file.printf("  \"ble_sync_samples\": %lu,\n", (unsigned long)bleSyncSamples);
  file.printf("  \"ble_commands_received\": %lu,\n", (unsigned long)bleCommandCount);
  file.printf("  \"closed_cleanly\": %s\n", closedCleanly ? "true" : "false");
  file.println("}");
  file.close();
}

void writeCheckpoint(bool closedCleanly) {
  if (!sdReady || sessionDir[0] == 0) return;
  char temporaryPath[64];
  char checkpointPath[64];
  char previousPath[64];
  snprintf(temporaryPath, sizeof(temporaryPath), "%s/CHECKPOINT.TMP", sessionDir);
  snprintf(checkpointPath, sizeof(checkpointPath), "%s/CHECKPOINT.JSON", sessionDir);
  snprintf(previousPath, sizeof(previousPath), "%s/CHECKPOINT.OLD", sessionDir);
  if (SD.exists(temporaryPath)) SD.remove(temporaryPath);
  File file = SD.open(temporaryPath, FILE_WRITE);
  if (!file) return;

  uint64_t cardBytes = SD.cardSize();
  uint64_t usedBytes = SD.usedBytes();
  uint64_t freeBytes = cardBytes > usedBytes ? cardBytes - usedBytes : 0;
  file.println("{");
  file.println("  \"format\": \"ToyotaHybridCAN-Checkpoint\",");
  file.println("  \"firmware_version\": \"2.4.2\",");
  file.printf("  \"time_ms\": %lu,\n", (unsigned long)millis());
  file.printf("  \"vehicle_profile\": \"%s\",\n", profileLabel(vehicleProfile));
  file.printf("  \"profile_confidence_pct\": %u,\n", profileConfidence);
  file.printf("  \"raw_file_index\": %u,\n", rawFileIndex);
  file.printf("  \"frames_processed_by_logger\": %llu,\n", (unsigned long long)rawSequence);
  file.printf("  \"session_state\": \"%s\",\n",
              closedCleanly ? "CLOSED" : (sessionHasCanTraffic ? "LOGGING" : "ARMED_WAIT_CAN"));
  file.printf("  \"session_had_can_traffic\": %s,\n", sessionHasCanTraffic ? "true" : "false");
  file.printf("  \"session_start_us\": %llu,\n", (unsigned long long)sessionStartUs);
  file.printf("  \"session_first_can_us\": %llu,\n", (unsigned long long)sessionFirstCanUs);
  file.printf("  \"session_last_can_us\": %llu,\n", (unsigned long long)sessionLastCanUs);
  file.printf("  \"session_received_frames\": %lu,\n",
              (unsigned long)(receivedFrameCount - sessionStartReceivedFrames));
  file.printf("  \"received_frames\": %lu,\n", (unsigned long)receivedFrameCount);
  file.printf("  \"transmitted_frames\": %lu,\n", (unsigned long)transmittedFrameCount);
  file.printf("  \"can_queue_drops\": %lu,\n", (unsigned long)canQueueDrops);
  file.printf("  \"diagnostic_queue_drops\": %lu,\n", (unsigned long)diagnosticQueueDrops);
  file.printf("  \"sd_log_drops\": %lu,\n", (unsigned long)sdLogDrops);
  file.printf("  \"sd_log_dropped_frames_estimate\": %lu,\n", (unsigned long)sdLogDroppedFrames);
  file.printf("  \"diagnostic_timeouts\": %lu,\n", (unsigned long)diagnosticTimeouts);
  file.printf("  \"external_diagnostic_frames\": %lu,\n", (unsigned long)externalDiagnosticFrames);
  file.printf("  \"ble_sync_samples\": %lu,\n", (unsigned long)bleSyncSamples);
  file.printf("  \"isotp_flow_control_frames\": %lu,\n", (unsigned long)isotpFlowControlCount);
  file.printf("  \"isotp_flow_control_failures\": %lu,\n", (unsigned long)isotpFlowControlFailures);
  file.printf("  \"twai_rx_missed_count\": %lu,\n", (unsigned long)twaiRxMissedCount);
  file.printf("  \"twai_rx_overrun_count\": %lu,\n", (unsigned long)twaiRxOverrunCount);
  file.printf("  \"twai_bus_error_count\": %lu,\n", (unsigned long)twaiBusErrorCount);
  file.printf("  \"sd_free_bytes\": %llu,\n", (unsigned long long)freeBytes);
  file.printf("  \"sd_space_low\": %s,\n", freeBytes < MIN_SD_FREE_BYTES ? "true" : "false");
  file.printf("  \"closed_cleanly\": %s\n", closedCleanly ? "true" : "false");
  file.println("}");
  file.flush();
  file.close();

  if (SD.exists(previousPath)) SD.remove(previousPath);
  bool hadCheckpoint = SD.exists(checkpointPath);
  if (hadCheckpoint && !SD.rename(checkpointPath, previousPath)) {
    ++sdLogDrops;
    return;
  }
  if (SD.rename(temporaryPath, checkpointPath)) {
    if (SD.exists(previousPath)) SD.remove(previousPath);
  } else {
    ++sdLogDrops;
    if (hadCheckpoint && SD.exists(previousPath)) SD.rename(previousPath, checkpointPath);
  }
}

void serviceTwaiHealth() {
  uint32_t alerts = 0;
  if (twai_read_alerts(&alerts, 0) == ESP_OK && alerts) {
    if (alerts & TWAI_ALERT_BUS_OFF) {
      ++twaiBusOffEvents;
      diagnosticEnabled = false;
      if (diag.active) completeDiagnostic("BUS_OFF");
      writeEvent("ERROR", "TWAI_BUS_OFF", "Diagnostics disabled; automatic recovery requested");
      if (!twaiRecovering && twai_initiate_recovery() == ESP_OK) twaiRecovering = true;
    }
    if (alerts & TWAI_ALERT_BUS_RECOVERED) {
      bool restored = twaiNormalMode ? configureTwai(TWAI_MODE_LISTEN_ONLY) : (twai_start() == ESP_OK);
      twaiRecovering = false;
      writeEvent(restored ? "INFO" : "ERROR", "TWAI_BUS_RECOVERED",
                 restored ? "Controller restarted in passive mode; diagnostics remain off" : "Controller restart failed");
    }
  }

  uint32_t nowMs = millis();
  if (nowMs - lastTwaiStatusMs < TWAI_STATUS_PERIOD_MS) return;
  lastTwaiStatusMs = nowMs;
  twai_status_info_t status = {};
  if (twai_get_status_info(&status) == ESP_OK) {
    twaiRxMissedCount = status.rx_missed_count;
    twaiRxOverrunCount = status.rx_overrun_count;
    twaiTxFailedCount = status.tx_failed_count;
    twaiArbLostCount = status.arb_lost_count;
    twaiBusErrorCount = status.bus_error_count;
    twaiRxQueued = status.msgs_to_rx;
    twaiTxQueued = status.msgs_to_tx;
  }
}

void flushLogFiles() {
  if (!loggingActive) return;
  if (rawFile) rawFile.flush();
  if (decodedFile) decodedFile.flush();
  if (diagnosticFile) diagnosticFile.flush();
  if (eventFile) eventFile.flush();
  if (syncFile) syncFile.flush();
  if (externalDiagnosticFile) externalDiagnosticFile.flush();
}

// ---------------------------- BLE clock/session sync -------------------------
const char *bleStateLabel() {
  switch (bleLinkState) {
    case BLE_LINK_ADVERTISING: return "ADV";
    case BLE_LINK_CONNECTED: return "CON";
    case BLE_LINK_ERROR: return "ERR";
    default: return "INIT";
  }
}

void printHeapStage(const char *stage) {
  Serial.printf("# HEAP,%s,free=%u,largest=%u,min=%u\n",
                stage,
                (unsigned)ESP.getFreeHeap(),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
                (unsigned)ESP.getMinFreeHeap());
}

void disableBleSync(const char *stage) {
  bleConnected = false;
  bleServiceReady = false;
  bleLinkState = BLE_LINK_ERROR;
  bleServer = nullptr;
  bleResponseCharacteristic = nullptr;
  Serial.printf("# BLE ERROR,%s; BLE disabled; CAN logger continues\n", stage);
  if (bleStackInitialized) {
    BLEDevice::deinit(true);
    bleStackInitialized = false;
  }
  if (bleSyncQueue != nullptr) {
    vQueueDelete(bleSyncQueue);
    bleSyncQueue = nullptr;
  }
  if (bleCommandQueue != nullptr) {
    vQueueDelete(bleCommandQueue);
    bleCommandQueue = nullptr;
  }
  printHeapStage("BLE_DISABLED");
}

bool initializeBleSync() {
  bleLinkState = BLE_LINK_STARTING;
  uint32_t suffix = (uint32_t)(ESP.getEfuseMac() & 0xFFFF);
  snprintf(bleDeviceName, sizeof(bleDeviceName), "ToyotaCYD-%04X", suffix);
  BLEDevice::init(bleDeviceName);
  bleStackInitialized = true;
  bleServer = BLEDevice::createServer();
  if (bleServer == nullptr) {
    disableBleSync("CREATE_SERVER");
    return false;
  }
  bleServer->setCallbacks(new LoggerBleServerCallbacks());
  BLEService *service = bleServer->createService(BLE_SERVICE_UUID);
  if (service == nullptr) {
    disableBleSync("CREATE_SERVICE");
    return false;
  }
  BLECharacteristic *command = service->createCharacteristic(
      BLE_COMMAND_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  if (command == nullptr) {
    disableBleSync("CREATE_COMMAND_CHARACTERISTIC");
    return false;
  }
  command->setCallbacks(new LoggerBleCommandCallbacks());
  bleResponseCharacteristic = service->createCharacteristic(
      BLE_RESPONSE_UUID, BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
  if (bleResponseCharacteristic == nullptr) {
    disableBleSync("CREATE_RESPONSE_CHARACTERISTIC");
    return false;
  }
  bleResponseCharacteristic->addDescriptor(new BLE2902());
  uint8_t initial[20] = {0x80, BLE_PROTOCOL_VERSION};
  bleResponseCharacteristic->setValue(initial, sizeof(initial));
  service->start();
  bleServiceReady = true;
  Serial.printf("# BLE SERVICE READY,%s,advertising=deferred\n", bleDeviceName);
  return true;
}

bool startBleAdvertising() {
  if (!bleServiceReady || !bleStackInitialized) return false;
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  if (advertising == nullptr) {
    disableBleSync("CREATE_ADVERTISING");
    return false;
  }
  advertising->addServiceUUID(BLE_SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  bleLinkState = BLE_LINK_ADVERTISING;
  Serial.printf("# BLE READY,%s,%s\n", bleDeviceName, BLE_SERVICE_UUID);
  return true;
}

void writeSyncRecord(const BleSyncRecord &record, const char *source) {
  if (!loggingActive || !syncFile) return;
  syncFile.print(record.sequence); syncFile.print(',');
  syncFile.printf("%llu", (unsigned long long)record.receiveUs); syncFile.print(',');
  syncFile.printf("%llu", (unsigned long long)record.sendUs); syncFile.print(',');
  syncFile.println(source);
}

void sendBleControlResponse(const BleCommand &command, uint8_t status, uint64_t eventUs) {
  if (bleResponseCharacteristic == nullptr) return;
  uint8_t response[20] = {};
  response[0] = 0x82;
  response[1] = BLE_PROTOCOL_VERSION;
  writeLe16(&response[2], command.sequence);
  response[4] = status;
  response[5] = loggingActive ? 1 : 0;
  uint32_t sessionNumber = sessionDir[0] ? (uint32_t)atoi(&sessionDir[9]) : 0;
  writeLe32(&response[6], sessionNumber);
  writeLe64(&response[10], eventUs);
  response[18] = diagnosticEnabled ? 1 : 0;
  response[19] = twaiNormalMode ? 1 : 0;
  bleResponseCharacteristic->setValue(response, sizeof(response));
  bleResponseCharacteristic->notify();
}

void processBleCommand(const BleCommand &command) {
  ++bleCommandCount;
  if (command.opcode == 1) {
    // A synchronized phone capture always owns a passive session. It can never
    // turn on diagnostics or request an arbitrary CAN transmission.
    if (diagnosticEnabled || twaiNormalMode)
      setDiagnosticCapture(false, "BLE synchronized capture requested");
    if (!loggingActive && sdReady) startLogging();
    uint64_t eventUs = nowMicros64();
    if (loggingActive) {
      writeEvent("INFO", "BLE_CAPTURE_START", "sequence=" + String(command.sequence));
      sendBleControlResponse(command, 0, eventUs);
    } else {
      sendBleControlResponse(command, sdReady ? 3 : 2, eventUs);
    }
    return;
  }

  if (command.opcode == 2) {
    uint64_t eventUs = nowMicros64();
    if (loggingActive) {
      writeEvent("INFO", "BLE_CAPTURE_STOP", "sequence=" + String(command.sequence));
      stopLogging(true);
      sendBleControlResponse(command, 0, eventUs);
    } else {
      sendBleControlResponse(command, 3, eventUs);
    }
    return;
  }

  if (command.opcode == 3) {
    uint64_t eventUs = nowMicros64();
    if (loggingActive) {
      writeEvent("INFO", "BLE_MARKER", "marker=" + String(command.marker) + ";sequence=" + String(command.sequence));
      sendBleControlResponse(command, 0, eventUs);
    } else {
      sendBleControlResponse(command, 3, eventUs);
    }
    return;
  }

  sendBleControlResponse(command, 1, nowMicros64());
}

void serviceBleSync() {
  BleSyncRecord sync;
  while (bleSyncQueue != nullptr && xQueueReceive(bleSyncQueue, &sync, 0) == pdTRUE) {
    ++bleSyncSamples;
    if (loggingActive) {
      writeSyncRecord(sync, "BLE");
    } else if (pendingSyncCount < sizeof(pendingSync) / sizeof(pendingSync[0])) {
      pendingSync[pendingSyncCount++] = sync;
    } else {
      memmove(&pendingSync[0], &pendingSync[1], (pendingSyncCount - 1) * sizeof(BleSyncRecord));
      pendingSync[pendingSyncCount - 1] = sync;
    }
  }

  BleCommand command;
  while (bleCommandQueue != nullptr && xQueueReceive(bleCommandQueue, &command, 0) == pdTRUE)
    processBleCommand(command);
}

// -------------------------------- Display/UI ----------------------------------
void drawStaticUI() {
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawRect(0, 0, 480, 245, TFT_DARKGREY);
  drawButtons();
}

void drawButtons() {
  uint16_t logColor = !loggingActive ? TFT_DARKGREY :
                      (sessionTrafficRecent() ? TFT_GREEN : TFT_ORANGE);
  bool externalRecent = externalTesterLastUs != 0 &&
                        (nowMicros64() - externalTesterLastUs) / 1000ULL < EXTERNAL_TESTER_HOLD_MS;
  bool diagnosticAvailable = loggingActive && vehicleProfile == PROFILE_PRIUS_GEN2 &&
                             profileConfidence >= 80 && !externalRecent;
  uint16_t diagColor = diagnosticEnabled ? TFT_RED : (diagnosticAvailable ? TFT_BLUE : TFT_DARKGREY);
  tft.fillRoundRect(CYD_PAGE_BTN_X, CYD_PAGE_BTN_Y, CYD_PAGE_BTN_W, CYD_PAGE_BTN_H, 6, TFT_DARKCYAN);
  tft.drawRoundRect(CYD_PAGE_BTN_X, CYD_PAGE_BTN_Y, CYD_PAGE_BTN_W, CYD_PAGE_BTN_H, 6, TFT_WHITE);
  tft.fillRoundRect(CYD_LOG_BTN_X, CYD_LOG_BTN_Y, CYD_LOG_BTN_W, CYD_LOG_BTN_H, 6, logColor);
  tft.drawRoundRect(CYD_LOG_BTN_X, CYD_LOG_BTN_Y, CYD_LOG_BTN_W, CYD_LOG_BTN_H, 6, TFT_WHITE);
  tft.fillRoundRect(CYD_DIAG_BTN_X, CYD_DIAG_BTN_Y, CYD_DIAG_BTN_W, CYD_DIAG_BTN_H, 6, diagColor);
  tft.drawRoundRect(CYD_DIAG_BTN_X, CYD_DIAG_BTN_Y, CYD_DIAG_BTN_W, CYD_DIAG_BTN_H, 6, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE);
  tft.drawString(displayPage ? "STATUS PAGE" : "TEMP PAGE", 62, 283, 2);
  tft.drawString(loggingActive ? "STOP LOG" : "START LOG", 297, 283, 2);
  tft.drawString(diagnosticEnabled ? "DIAG ON" : (diagnosticAvailable ? "DIAG OFF" : "DIAG N/A"), 417, 283, 2);
  tft.setTextDatum(TL_DATUM);
}

void updateDisplay() {
  uint32_t nowMs = millis();
  bool electrical = (live.ceValid && nowMs - live.ceMs < 2000) ||
                    (live.c3Valid && nowMs - live.c3Ms < 2000) ||
                    (live.passiveElectricalValid && nowMs - live.passiveElectricalMs < 2000);
  bool soc = (live.ceValid && nowMs - live.ceMs < 2000) ||
             (live.c3Valid && nowMs - live.c3Ms < 2000) ||
             (live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000);
  bool c3 = live.c3Valid && nowMs - live.c3Ms < 2000;
  bool camryEngine = live.camryEngineValid && nowMs - live.camryEngineMs < 2000;
  bool engine = (live.engineRPMValid && nowMs - live.engineRPMMs < 5000) || camryEngine;
  bool camryGear = live.camryGearValid && nowMs - live.camryGearMs < 2000;
  bool camryCoolant = live.camryCoolantValid && nowMs - live.camryCoolantMs < 2000;
  bool temps = (live.cfValid && nowMs - live.cfMs < 2000) ||
               (live.passiveSocTempValid && nowMs - live.passiveSocTempMs < 2000);
  tft.fillRect(2, 2, 476, 241, TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  if (displayPage == 0) {
    tft.drawString("TOYOTA HYBRID CAN LOGGER v2.4.2", 10, 8, 2);
    tft.drawString("Vehicle:", 10, 35, 2);
    tft.drawString("Evidence:", 10, 58, 2);
    tft.drawString("TWAI:", 10, 81, 2);
    tft.drawString("SD:", 10, 104, 2);
    tft.drawString("RX/TX/Qdrop/Ddrop:", 10, 127, 2);
    tft.drawString("SOC / V / A:", 10, 150, 2);
    tft.drawString(vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1 ? "Gear / ICE candidate:" : "MG1 / MG2 / ICE:", 10, 173, 2);
    tft.drawString("HV T1 / T2 / T3:", 10, 196, 2);
    tft.drawString("Quality:", 10, 219, 2);
    bool recognizedProfile = vehicleProfile == PROFILE_PRIUS_GEN2 ||
                             vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1;
    tft.setTextColor(recognizedProfile ? TFT_GREEN : TFT_YELLOW, TFT_BLACK);
    tft.drawString(String(profileLabel(vehicleProfile)) + " " + String(profileConfidence) + "%", 175, 35, 2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("P:" + String(priusScore) + " C:" + String(camryScore), 175, 58, 2);
    String twaiText = twaiNormalMode ? "NORMAL DIAG" : "LISTEN 500k";
    twaiText += " / BLE ";
    twaiText += bleStateLabel();
    tft.drawString(twaiText, 175, 81, 2);
    String sdText;
    if (!sdReady) {
      sdText = loggerStatus;
    } else if (loggingActive) {
      sdText = sessionName();
      if (!sessionHasCanTraffic) sdText += " ARMED / WAIT CAN";
      else if (sessionTrafficRecent()) sdText += " LOGGING";
      else sdText += " LOG / NO CAN";
    } else {
      sdText = loggerStatus;
    }
    tft.drawString(sdText, 175, 104, 2);
    tft.drawString(String(receivedFrameCount) + "/" + transmittedFrameCount + "/" + canQueueDrops + "/" + diagnosticQueueDrops, 175, 127, 2);
    tft.drawString(soc ? String(live.socPct, 1) + "%" : "---", 175, 150, 2);
    tft.drawString(electrical ? String(live.packVolts, 1) + "V " + String(live.packAmps, 1) + "A" : "---", 230, 150, 2);
    if (vehicleProfile == PROFILE_CAMRY_HYBRID_GEN1) {
      String camryText = camryGear ? String(gearLabel(live.gearCode)) : "?";
      camryText += " / ";
      camryText += camryEngine ? String(live.engineRPM) : "---";
      tft.drawString(camryText, 230, 173, 2);
    } else {
      if (c3)
        tft.drawString(String(live.mg1RPM) + " / " + live.mg2RPM + " / " + live.engineRPM, 175, 173, 2);
      else
        tft.drawString(engine ? String("--- / --- / ") + live.engineRPM : "---", 175, 173, 2);
    }
    tft.drawString(temps ? String(live.hvTemp1F, 1) + " / " + live.hvTemp2F + " / " + live.hvTemp3F : "---", 175, 196, 2);
    tft.setTextColor(TFT_CYAN, TFT_BLACK); tft.drawString(dataQualityLabel(), 175, 219, 2);
  } else {
    tft.drawString("TEMPERATURES (F)", 10, 8, 2);
    const char *labels[] = {"Engine coolant:","Engine intake air:","Catalyst B1S1:","Converter:","MG1 / MG2 inverter:","MG1 / MG2 motor:","Battery T1/T2/T3:","Battery intake / avg:"};
    for (uint8_t i=0;i<8;++i) tft.drawString(labels[i],10,35+i*25,2);
    bool coolant = (live.coolantValid && nowMs-live.coolantMs<5000) || camryCoolant;
    bool air = live.engineIntakeValid && nowMs-live.engineIntakeMs<5000;
    bool cat = live.catalystValid && nowMs-live.catalystMs<5000;
    bool c4 = live.c4Valid && nowMs-live.c4Ms<5000;
    tft.setTextColor(TFT_YELLOW,TFT_BLACK);
    tft.drawString(coolant?String(live.engineCoolantF,1):"---",230,35,2);
    tft.drawString(air?String(live.engineIntakeAirF,1):"---",230,60,2);
    tft.drawString(cat?String(live.catalystB1S1F,1):"---",230,85,2);
    tft.drawString(c4?String(live.converterTempF,1):"---",230,110,2);
    tft.drawString(c3?String(live.mg1InvF,1)+" / "+String(live.mg2InvF,1):"---",230,135,2);
    tft.drawString(c3?String(live.mg1StatorF,1)+" / "+String(live.mg2StatorF,1):"---",230,160,2);
    tft.drawString(temps?String(live.hvTemp1F,1)+" / "+String(live.hvTemp2F,1)+" / "+String(live.hvTemp3F,1):"---",230,185,2);
    tft.drawString(temps?String(live.intakeTempF,1)+" / "+String(live.hvAvgF,1):"---",230,210,2);
  }
  drawButtons();
}

void handleTouch() {
  uint32_t nowMs = millis();
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

  bool logButton = touchDownX >= CYD_LOG_BTN_X &&
                   touchDownX < CYD_LOG_BTN_X + CYD_LOG_BTN_W &&
                   touchDownY >= CYD_LOG_BTN_Y &&
                   touchDownY < CYD_LOG_BTN_Y + CYD_LOG_BTN_H;
  bool diagButton = touchDownX >= CYD_DIAG_BTN_X &&
                    touchDownX < CYD_DIAG_BTN_X + CYD_DIAG_BTN_W &&
                    touchDownY >= CYD_DIAG_BTN_Y &&
                    touchDownY < CYD_DIAG_BTN_Y + CYD_DIAG_BTN_H;
  bool pageButton = touchDownX >= CYD_PAGE_BTN_X &&
                    touchDownX < CYD_PAGE_BTN_X + CYD_PAGE_BTN_W &&
                    touchDownY >= CYD_PAGE_BTN_Y &&
                    touchDownY < CYD_PAGE_BTN_Y + CYD_PAGE_BTN_H;

  if (pageButton) {
    displayPage ^= 1;
    updateDisplay();
  } else if (logButton) {
    if (loggingActive) stopLogging(true);
    else startLogging();
  } else if (diagButton) {
    if (vehicleProfile == PROFILE_PRIUS_GEN2 && profileConfidence >= 80) {
      setDiagnosticCapture(!diagnosticEnabled, "Touchscreen user action");
    } else {
      if (nowMs - lastDiagRejectMs >= 2000) {
        writeEvent("WARNING", "DIAGNOSTIC_ENABLE_REJECTED", "Strong Prius Gen 2 profile required; Camry remains passive-only");
        lastDiagRejectMs = nowMs;
      }
    }
  }
  drawButtons();
}
