/*
  Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.4 RC1

  Architecture rule:
    - The acquisition/logger implementation below is the exact v2.4.2 source
      included as logger_v2_4_2_core.inc.
    - Only setup(), loop(), handleTouch(), drawButtons(), and updateDisplay()
      are wrapped so Wi-Fi maintenance can be entered while STOPPED.
    - Wi-Fi is never initialized during the normal logger boot/run path.
    - Entering Wi-Fi permanently tears down BLE/TWAI/CAN runtime services.
      EXIT performs ESP.restart(); logger services are never reconstructed in RAM.
    - No persistent/NVS session allocator is used. v2.4.2 folder allocation is
      preserved. CLEAR removes contents of selected Sxxxx folders but leaves the
      empty session folder, so the original first-unused-folder sequence does not
      reuse cleared session numbers.
*/

#include <WiFi.h>
#include <WebServer.h>

// Rename only the v2.4.2 integration points. All acquisition/storage functions
// retain their exact v2.4.2 bodies in the included source.
#define setup logger242_setup
#define loop logger242_loop
#define handleTouch logger242_handleTouch
#define drawButtons logger242_drawButtons
#define updateDisplay logger242_updateDisplay
#include "logger_v2_4_2_core.inc"
#undef setup
#undef loop
#undef handleTouch
#undef drawButtons
#undef updateDisplay

constexpr int CYD_WIFI_BTN_X = 125;
constexpr int CYD_WIFI_BTN_Y = 258;
constexpr int CYD_WIFI_BTN_W = 105;
constexpr int CYD_WIFI_BTN_H = 50;

WebServer wifiServer(80);
bool wifiMaintenanceMode = false;
bool wifiConfirmPending = false;
String wifiPendingClear;
char wifiApSsid[32] = {0};
char wifiApPassword[20] = {0};

static String htmlEscape(const String &s) {
  String out;
  out.reserve(s.length() + 16);
  for (size_t i = 0; i < s.length(); ++i) {
    char c = s[i];
    if (c == '&') out += F("&amp;");
    else if (c == '<') out += F("&lt;");
    else if (c == '>') out += F("&gt;");
    else if (c == '\"') out += F("&quot;");
    else out += c;
  }
  return out;
}

static bool validSessionName(const String &name) {
  if (name.length() != 5 || name[0] != 'S') return false;
  for (uint8_t i = 1; i < 5; ++i) if (!isDigit(name[i])) return false;
  return true;
}

static bool validFileName(const String &name) {
  if (name.length() == 0 || name.length() > 48) return false;
  if (name.indexOf('/') >= 0 || name.indexOf('\\') >= 0 || name.indexOf("..") >= 0) return false;
  return true;
}

static String sessionPath(const String &session) {
  return String("/CANLOG/") + session;
}

static uint64_t directoryBytes(const String &path) {
  File dir = SD.open(path.c_str());
  if (!dir || !dir.isDirectory()) { if (dir) dir.close(); return 0; }
  uint64_t total = 0;
  File f = dir.openNextFile();
  while (f) {
    if (!f.isDirectory()) total += f.size();
    f.close();
    f = dir.openNextFile();
  }
  dir.close();
  return total;
}

static String humanBytes(uint64_t bytes) {
  if (bytes >= 1024ULL * 1024ULL) return String((double)bytes / (1024.0 * 1024.0), 1) + " MB";
  if (bytes >= 1024ULL) return String((double)bytes / 1024.0, 1) + " KB";
  return String((unsigned long long)bytes) + " B";
}

static bool clearDirectoryContents(const String &path) {
  File dir = SD.open(path.c_str());
  if (!dir || !dir.isDirectory()) { if (dir) dir.close(); return false; }
  bool ok = true;
  File f = dir.openNextFile();
  while (f) {
    String childName = String(f.name());
    bool childDir = f.isDirectory();
    f.close();
    String childPath = childName.startsWith("/") ? childName : path + "/" + childName;
    if (childDir) {
      if (!clearDirectoryContents(childPath)) ok = false;
      if (!SD.rmdir(childPath.c_str())) ok = false;
    } else if (!SD.remove(childPath.c_str())) {
      ok = false;
    }
    if (!ok) break;  // fail closed: do not silently continue a partial bulk clear
    f = dir.openNextFile();
  }
  dir.close();
  return ok;
}

static void sendPage(const String &body, int code = 200) {
  String html = F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                  "<title>Toyota CYD Wi-Fi Files</title><style>body{font-family:sans-serif;max-width:900px;margin:24px auto;padding:0 12px}"
                  "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:8px;text-align:left}"
                  "button,a.btn{padding:8px 12px;margin:3px;text-decoration:none} .danger{background:#b00020;color:white}</style></head><body>");
  html += body;
  html += F("</body></html>");
  wifiServer.send(code, "text/html", html);
}

static void handleWifiRoot() {
  String body = F("<h2>Toyota CYD v2.4.4 RC1 - Wi-Fi Files</h2><p>Logger runtime is offline. SD maintenance only.</p>"
                  "<table><tr><th>Session</th><th>Size</th><th>Actions</th></tr>");
  File root = SD.open("/CANLOG");
  if (root && root.isDirectory()) {
    File entry = root.openNextFile();
    while (entry) {
      if (entry.isDirectory()) {
        String full = String(entry.name());
        int slash = full.lastIndexOf('/');
        String name = slash >= 0 ? full.substring(slash + 1) : full;
        if (validSessionName(name)) {
          uint64_t bytes = directoryBytes(sessionPath(name));
          body += "<tr><td><b>" + htmlEscape(name) + "</b>" + (bytes == 0 ? " (EMPTY / CLEARED)" : "") + "</td><td>" + humanBytes(bytes) + "</td><td>";
          body += "<a class='btn' href='/session?s=" + name + "'>Files</a>";
          body += "<a class='btn danger' href='/clear?s=" + name + "'>Clear contents</a></td></tr>";
        }
      }
      entry.close();
      entry = root.openNextFile();
    }
  }
  if (root) root.close();
  body += F("</table><p><a class='btn' href='/exit'>EXIT / RESTART LOGGER</a></p>");
  sendPage(body);
}

static void handleWifiSession() {
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h3>Invalid session</h3>"), 400); return; }
  String path = sessionPath(s);
  File dir = SD.open(path.c_str());
  if (!dir || !dir.isDirectory()) { if (dir) dir.close(); sendPage(F("<h3>Session not found</h3>"), 404); return; }
  String body = "<h2>" + htmlEscape(s) + "</h2><table><tr><th>File</th><th>Size</th><th>Action</th></tr>";
  File f = dir.openNextFile();
  while (f) {
    if (!f.isDirectory()) {
      String full = String(f.name());
      int slash = full.lastIndexOf('/');
      String name = slash >= 0 ? full.substring(slash + 1) : full;
      if (validFileName(name)) body += "<tr><td>" + htmlEscape(name) + "</td><td>" + humanBytes(f.size()) + "</td><td><a href='/download?s=" + s + "&f=" + name + "'>Download</a></td></tr>";
    }
    f.close();
    f = dir.openNextFile();
  }
  dir.close();
  body += F("</table><p><a href='/'>Back</a></p>");
  sendPage(body);
}

static void handleWifiDownload() {
  String s = wifiServer.arg("s"), f = wifiServer.arg("f");
  if (!validSessionName(s) || !validFileName(f)) { wifiServer.send(400, "text/plain", "Invalid path"); return; }
  String path = sessionPath(s) + "/" + f;
  File file = SD.open(path.c_str(), FILE_READ);
  if (!file || file.isDirectory()) { if (file) file.close(); wifiServer.send(404, "text/plain", "Not found"); return; }
  wifiServer.sendHeader("Content-Disposition", "attachment; filename=\"" + f + "\"");
  wifiServer.streamFile(file, "application/octet-stream");
  file.close();
}

static void handleWifiClearRequest() {
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h3>Invalid session</h3>"), 400); return; }
  wifiPendingClear = s;
  wifiConfirmPending = true;
  String body = "<h2>Confirm clear</h2><p>Delete all contents of <b>" + htmlEscape(s) + "</b> but KEEP the empty session folder?</p>";
  body += "<form method='POST' action='/clear-confirm'><input type='hidden' name='s' value='" + s + "'><button class='danger' type='submit'>CLEAR CONTENTS OF " + s + "</button></form><p><a href='/'>Cancel</a></p>";
  sendPage(body);
}

static void handleWifiClearConfirm() {
  String s = wifiServer.arg("s");
  if (!wifiConfirmPending || s != wifiPendingClear || !validSessionName(s)) { sendPage(F("<h3>Confirmation expired or invalid.</h3>"), 400); return; }
  wifiConfirmPending = false;
  wifiPendingClear = "";
  String path = sessionPath(s);
  bool ok = clearDirectoryContents(path);
  // The selected Sxxxx directory itself is intentionally never removed.
  if (ok && SD.exists(path.c_str())) sendPage("<h2>Cleared " + htmlEscape(s) + "</h2><p>Session folder retained for v2.4.2 numbering continuity.</p><p><a href='/'>Back</a></p>");
  else sendPage("<h2>Clear incomplete</h2><p>Stopped on SD error. The session folder was not intentionally removed.</p><p><a href='/'>Back</a></p>", 500);
}

static void handleWifiExit() {
  wifiServer.send(200, "text/plain", "Restarting logger...");
  delay(250);
  ESP.restart();
}

static void shutdownLoggerServicesForWifi() {
  // Entry is allowed only while logging is stopped. Force diagnostics passive
  // before tearing the CAN runtime down.
  diagnosticEnabled = false;
  fastDiagActive = false;
  if (canReceiveTaskHandle != nullptr) {
    vTaskDelete(canReceiveTaskHandle);
    canReceiveTaskHandle = nullptr;
  }
  twai_stop();
  twai_driver_uninstall();
  twaiNormalMode = false;
  if (bleStackInitialized) {
    BLEDevice::deinit(true);
    bleStackInitialized = false;
    bleServiceReady = false;
    bleConnected = false;
  }
  if (bleSyncQueue != nullptr) { vQueueDelete(bleSyncQueue); bleSyncQueue = nullptr; }
  if (bleCommandQueue != nullptr) { vQueueDelete(bleCommandQueue); bleCommandQueue = nullptr; }
}

static void enterWifiMaintenanceMode() {
  if (wifiMaintenanceMode || loggingActive || !sdReady) return;
  shutdownLoggerServicesForWifi();
  wifiMaintenanceMode = true;
  uint32_t suffix = (uint32_t)(ESP.getEfuseMac() & 0xFFFF);
  snprintf(wifiApSsid, sizeof(wifiApSsid), "ToyotaCYD-Files-%04X", suffix);
  snprintf(wifiApPassword, sizeof(wifiApPassword), "Toyota%04Xfiles", suffix);
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(wifiApSsid, wifiApPassword)) {
    tft.fillScreen(TFT_RED);
    tft.setTextColor(TFT_WHITE, TFT_RED);
    tft.drawString("WIFI AP FAILED", 40, 110, 4);
    tft.drawString("RESTART REQUIRED", 40, 160, 3);
    return;
  }
  wifiServer.on("/", HTTP_GET, handleWifiRoot);
  wifiServer.on("/session", HTTP_GET, handleWifiSession);
  wifiServer.on("/download", HTTP_GET, handleWifiDownload);
  wifiServer.on("/clear", HTTP_GET, handleWifiClearRequest);
  wifiServer.on("/clear-confirm", HTTP_POST, handleWifiClearConfirm);
  wifiServer.on("/exit", HTTP_GET, handleWifiExit);
  wifiServer.onNotFound([](){ wifiServer.send(404, "text/plain", "Not found"); });
  wifiServer.begin();

  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("WIFI FILE MAINTENANCE", 20, 20, 4);
  tft.drawString(String("SSID: ") + wifiApSsid, 20, 80, 2);
  tft.drawString(String("PASS: ") + wifiApPassword, 20, 110, 2);
  tft.drawString(String("OPEN: http://") + WiFi.softAPIP().toString(), 20, 140, 2);
  tft.drawString("EXIT from browser restarts logger", 20, 190, 2);
}

// v2.4.2 UI with one additive maintenance button in the previously unused
// center-bottom area. Logger/diagnostic/page button geometry remains unchanged.
void drawButtons() {
  logger242_drawButtons();
  if (wifiMaintenanceMode) return;
  uint16_t wifiColor = (!loggingActive && sdReady) ? TFT_PURPLE : TFT_DARKGREY;
  tft.fillRoundRect(CYD_WIFI_BTN_X, CYD_WIFI_BTN_Y, CYD_WIFI_BTN_W, CYD_WIFI_BTN_H, 6, wifiColor);
  tft.drawRoundRect(CYD_WIFI_BTN_X, CYD_WIFI_BTN_Y, CYD_WIFI_BTN_W, CYD_WIFI_BTN_H, 6, TFT_WHITE);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE);
  tft.drawString("WIFI FILES", CYD_WIFI_BTN_X + CYD_WIFI_BTN_W / 2, 283, 2);
  tft.setTextDatum(TL_DATUM);
}

void updateDisplay() {
  if (wifiMaintenanceMode) return;
  logger242_updateDisplay();
  // logger242_updateDisplay() calls the renamed v2.4.2 drawButtons(); overlay
  // the additive maintenance control after the exact v2.4.2 display rendering.
  drawButtons();
}

void handleTouch() {
  if (wifiMaintenanceMode) return;
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

  bool wifiButton = touchDownX >= CYD_WIFI_BTN_X && touchDownX < CYD_WIFI_BTN_X + CYD_WIFI_BTN_W &&
                    touchDownY >= CYD_WIFI_BTN_Y && touchDownY < CYD_WIFI_BTN_Y + CYD_WIFI_BTN_H;
  if (wifiButton) {
    if (!loggingActive && sdReady) enterWifiMaintenanceMode();
    return;
  }

  // Preserve the v2.4.2 actions exactly for its three original button regions.
  bool logButton = touchDownX >= CYD_LOG_BTN_X && touchDownX < CYD_LOG_BTN_X + CYD_LOG_BTN_W && touchDownY >= CYD_LOG_BTN_Y && touchDownY < CYD_LOG_BTN_Y + CYD_LOG_BTN_H;
  bool diagButton = touchDownX >= CYD_DIAG_BTN_X && touchDownX < CYD_DIAG_BTN_X + CYD_DIAG_BTN_W && touchDownY >= CYD_DIAG_BTN_Y && touchDownY < CYD_DIAG_BTN_Y + CYD_DIAG_BTN_H;
  bool pageButton = touchDownX >= CYD_PAGE_BTN_X && touchDownX < CYD_PAGE_BTN_X + CYD_PAGE_BTN_W && touchDownY >= CYD_PAGE_BTN_Y && touchDownY < CYD_PAGE_BTN_Y + CYD_PAGE_BTN_H;
  if (pageButton) { displayPage ^= 1; updateDisplay(); }
  else if (logButton) { if (loggingActive) stopLogging(true); else startLogging(); }
  else if (diagButton) {
    if (vehicleProfile == PROFILE_PRIUS_GEN2 && profileConfidence >= 80) setDiagnosticCapture(!diagnosticEnabled, "Touchscreen user action");
    else if (nowMs - lastDiagRejectMs >= 2000) {
      writeEvent("WARNING", "DIAGNOSTIC_ENABLE_REJECTED", "Strong Prius Gen 2 profile required; Camry remains passive-only");
      lastDiagRejectMs = nowMs;
    }
  }
  drawButtons();
}

void setup() {
  // Exact v2.4.2 initialization. Wi-Fi is not touched here.
  logger242_setup();
  Serial.println("# v2.4.4 RC1 wrapper ready; Wi-Fi remains OFF until touchscreen request");
  updateDisplay();
}

void loop() {
  if (wifiMaintenanceMode) {
    wifiServer.handleClient();
    delay(1);
    return;
  }
  // Exact v2.4.2 loop body executes while Wi-Fi maintenance is false. Its calls
  // to handleTouch/updateDisplay resolve to the renamed v2.4.2 implementations,
  // so we additionally poll the RC1 touch wrapper at the same loop cadence.
  logger242_loop();
  handleTouch();
}
