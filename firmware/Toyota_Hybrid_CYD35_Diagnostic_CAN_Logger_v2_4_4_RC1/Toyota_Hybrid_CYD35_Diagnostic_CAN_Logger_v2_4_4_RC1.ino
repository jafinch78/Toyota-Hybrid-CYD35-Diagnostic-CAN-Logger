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
    - Toyota Hybrid CAN Database v0.5.5 read-only decoded-ID/profile metadata is
      compiled in for Gen 2, Gen 3 profile metadata, PHV Gen 1, and Camry Hybrid.
      No new automatic transmit workflow is enabled by the database manifest.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <esp_wifi.h>
#include "database_v0_5_5_decoded_ids.h"
#include "wifi_session_zip.h"
#include "wifi_session_zip_async.h"
#include "wifi_zip_download_async.h"

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
constexpr uint8_t CYD_WIFI_CHANNEL = 6;
constexpr uint8_t CYD_WIFI_MAX_CLIENTS = 4;

WebServer wifiServer(80);
bool wifiMaintenanceMode = false;
bool wifiConfirmPending = false;
bool wifiZipCompletionLogged = false;
String wifiPendingClear;
char wifiApSsid[32] = {0};
char wifiApPassword[20] = {0};
uint32_t lastWifiUiMs = 0;

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

static String sessionPath(const String &session) { return String("/CANLOG/") + session; }
static String zipPath(const String &session) { return String("/CANLOG/_ZIP/") + session + ".zip"; }

static bool ensureZipDirectory() {
  if (SD.exists("/CANLOG/_ZIP")) return true;
  return SD.mkdir("/CANLOG/_ZIP");
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

static uint64_t fileBytes(const String &path) {
  File f = SD.open(path.c_str(), FILE_READ);
  if (!f || f.isDirectory()) { if (f) f.close(); return 0; }
  uint64_t size = f.size();
  f.close();
  return size;
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
    if (!ok) break;
    f = dir.openNextFile();
  }
  dir.close();
  return ok;
}

static void sendPage(const String &body, int code = 200) {
  String html = F("<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
                  "<title>Toyota CYD Wi-Fi Files</title><style>"
                  "*{box-sizing:border-box}body{font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f6f7;color:#171717}"
                  "h1{font-size:1.7rem;margin:.2em 0}.sub{color:#555;margin:.4em 0 1.2em}.session{background:white;border:1px solid #ddd;border-radius:12px;padding:14px;margin:10px 0;box-shadow:0 1px 2px #0001}"
                  ".sessionHead{display:flex;justify-content:space-between;gap:12px;align-items:baseline}.sessionName{font-size:1.2rem;font-weight:700}.size{color:#555;white-space:nowrap}.state{font-size:.85rem;color:#666;margin-top:3px}"
                  ".actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.btn,button{appearance:none;border:1px solid #aaa;border-radius:8px;background:#fff;color:#111;padding:9px 12px;text-decoration:none;font-size:.95rem;line-height:1.15}"
                  ".primary{background:#1769aa;color:white;border-color:#1769aa}.danger{background:#a51d25;color:white;border-color:#a51d25}.secondary{background:#eee}.actions form{margin:0}"
                  ".notice{background:#fff8df;border:1px solid #ead28b;border-radius:10px;padding:10px 12px}.tableWrap{overflow-x:auto;background:white;border-radius:10px}table{border-collapse:collapse;width:100%;min-width:440px}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}"
                  "@media(max-width:520px){body{padding:12px}h1{font-size:1.45rem}.sessionHead{align-items:flex-start}.actions{display:grid;grid-template-columns:1fr 1fr}.btn,button{width:100%;text-align:center}.actions form{width:100%}}"
                  "</style></head><body>");
  html += body;
  html += F("</body></html>");
  wifiServer.send(code, "text/html", html);
}

static void handleWifiRoot() {
  String body = F("<h1>Toyota CYD v2.4.4 RC1 - Wi-Fi Files</h1><p class='sub'>Logger runtime is offline. SD maintenance only.</p>");
  body += "<p class='sub'>Toyota Hybrid CAN DB v" + String(TOYOTA_CAN_DB_VERSION) + " &middot; " + String(DB_DECODED_ID_COUNT) + " read-only definitions compiled &middot; AP channel " + String(CYD_WIFI_CHANNEL) + " &middot; Wi-Fi sleep OFF</p>";

  if (wifiZipDownloadBusy()) {
    body += "<div class='notice'><b>Downloading " + htmlEscape(wifiZipDownloadSession()) + ".zip:</b> " + String(wifiZipDownloadProgress()) + "% &middot; " + humanBytes(wifiZipDownloadSentBytes()) + " / " + humanBytes(wifiZipDownloadTotalBytes()) + ". One ZIP download is allowed at a time; other clients may continue viewing this status page.</div>";
    body += "<div class='actions'><form method='POST' action='/download-cancel'><button class='danger' type='submit'>Cancel Download</button></form><a class='btn secondary' href='/exit'>EXIT / RESTART LOGGER</a></div>";
    body += F("<script>setTimeout(function(){location.reload();},1500);</script>");
    sendPage(body);
    return;
  }

  if (storedSessionZipAsyncBusy()) {
    String s = storedSessionZipAsyncSession();
    body += "<div class='notice'><b>Preparing " + htmlEscape(s) + ".zip:</b> " + String(storedSessionZipAsyncProgress()) + "% complete. The ZIP is being written cooperatively so Wi-Fi/HTTP can continue to run.</div>";
    body += "<div class='actions'><form method='POST' action='/zip-cancel'><button class='danger' type='submit'>Cancel ZIP</button></form><a class='btn secondary' href='/exit'>EXIT / RESTART LOGGER</a></div>";
    body += F("<script>setTimeout(function(){location.reload();},1500);</script>");
    sendPage(body);
    return;
  }

  if (wifiZipDownloadAborted()) body += "<div class='notice'><b>Last download stopped:</b> " + htmlEscape(wifiZipDownloadError()) + "</div>";
  else if (wifiZipDownloadFailed()) body += "<div class='notice'><b>Last download error:</b> " + htmlEscape(wifiZipDownloadError()) + "</div>";
  if (storedSessionZipAsyncFailed()) body += "<div class='notice'><b>Last ZIP error:</b> " + htmlEscape(storedSessionZipAsyncError()) + "</div>";

  body += F("<div class='notice'><b>Preferred transfer:</b> Prepare a session ZIP, download it, then explicitly delete the temporary ZIP from the microSD. ZIPs are STORE archives (no compression) in RC1, so creation requires roughly the session size in free space. Large ZIP downloads use a dedicated cooperative transfer service so the status page stays responsive.</div>");

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
          String zp = zipPath(name);
          uint64_t zbytes = fileBytes(zp);
          bool zipReady = zbytes > 0;
          body += "<div class='session'><div class='sessionHead'><div><div class='sessionName'>" + htmlEscape(name) + "</div>";
          if (bytes == 0) body += "<div class='state'>EMPTY / CLEARED</div>";
          else body += "<div class='state'>Session data ready</div>";
          body += "</div><div class='size'>" + humanBytes(bytes) + "</div></div><div class='actions'>";
          if (bytes > 0 && !zipReady) {
            body += "<form method='POST' action='/zip-create'><input type='hidden' name='s' value='" + name + "'><button class='primary' type='submit'>Prepare ZIP</button></form>";
          }
          if (zipReady) {
            String dl = String("http://") + WiFi.softAPIP().toString() + ":" + WIFI_ZIP_DOWNLOAD_PORT + "/" + name + ".zip";
            body += "<a class='btn primary' href='" + dl + "' target='_blank'>Download ZIP (" + humanBytes(zbytes) + ")</a>";
            body += "<form method='POST' action='/zip-delete'><input type='hidden' name='s' value='" + name + "'><button class='secondary' type='submit'>Delete ZIP</button></form>";
          }
          body += "<a class='btn secondary' href='/session?s=" + name + "'>View files</a>";
          if (bytes > 0) body += "<a class='btn danger' href='/clear?s=" + name + "'>Clear contents</a>";
          body += "</div></div>";
        }
      }
      entry.close();
      entry = root.openNextFile();
    }
  }
  if (root) root.close();
  body += F("<p><a class='btn secondary' href='/exit'>EXIT / RESTART LOGGER</a></p>");
  sendPage(body);
}

static void handleWifiSession() {
  if (storedSessionZipAsyncBusy() || wifiZipDownloadBusy()) { wifiServer.send(409, "text/plain", "SD transfer in progress; retry shortly."); return; }
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h2>Invalid session</h2>"), 400); return; }
  String path = sessionPath(s);
  File dir = SD.open(path.c_str());
  if (!dir || !dir.isDirectory()) { if (dir) dir.close(); sendPage(F("<h2>Session not found</h2>"), 404); return; }
  String body = "<h1>" + htmlEscape(s) + "</h1><div class='tableWrap'><table><tr><th>File</th><th>Size</th><th>Action</th></tr>";
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
  body += F("</table></div><p><a class='btn secondary' href='/'>Back</a></p>");
  sendPage(body);
}

static void handleWifiDownload() {
  if (storedSessionZipAsyncBusy() || wifiZipDownloadBusy()) { wifiServer.send(409, "text/plain", "SD transfer in progress; retry shortly."); return; }
  String s = wifiServer.arg("s"), f = wifiServer.arg("f");
  if (!validSessionName(s) || !validFileName(f)) { wifiServer.send(400, "text/plain", "Invalid path"); return; }
  String path = sessionPath(s) + "/" + f;
  File file = SD.open(path.c_str(), FILE_READ);
  if (!file || file.isDirectory()) { if (file) file.close(); wifiServer.send(404, "text/plain", "Not found"); return; }
  wifiServer.sendHeader("Content-Disposition", "attachment; filename=\"" + f + "\"");
  wifiServer.streamFile(file, "application/octet-stream");
  file.close();
}

static void handleWifiZipCreate() {
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h2>Invalid session</h2>"), 400); return; }
  if (wifiZipDownloadBusy()) { sendPage(F("<h2>A ZIP download is active. Wait or cancel it first.</h2>"), 409); return; }
  if (storedSessionZipAsyncBusy()) { sendPage(F("<h2>A ZIP is already being prepared.</h2>"), 409); return; }
  String source = sessionPath(s);
  uint64_t sourceBytes = directoryBytes(source);
  if (sourceBytes == 0) { sendPage(F("<h2>Session is empty</h2><p>No ZIP was created.</p>"), 400); return; }
  if (!ensureZipDirectory()) { sendPage(F("<h2>ZIP folder error</h2><p>Could not create /CANLOG/_ZIP.</p>"), 500); return; }

  String error;
  String zp = zipPath(s);
  Serial.printf("# WIFI ZIP ASYNC START,%s,%llu bytes\n", s.c_str(), (unsigned long long)sourceBytes);
  if (!startStoredSessionZipAsync(s, source, zp, sourceBytes, error)) {
    Serial.printf("# WIFI ZIP ASYNC FAILED_TO_START,%s,%s\n", s.c_str(), error.c_str());
    sendPage("<h1>ZIP creation failed</h1><p>" + htmlEscape(error) + "</p><p><a class='btn secondary' href='/'>Back</a></p>", 500);
    return;
  }
  wifiZipCompletionLogged = false;
  wifiServer.sendHeader("Location", "/");
  wifiServer.send(303, "text/plain", "ZIP preparation started");
}

static void handleWifiZipDownload() {
  // Compatibility route: redirect legacy port-80 ZIP links to the dedicated
  // cooperative port-81 download service.
  if (storedSessionZipAsyncBusy()) { wifiServer.send(409, "text/plain", "ZIP preparation still in progress."); return; }
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { wifiServer.send(400, "text/plain", "Invalid session"); return; }
  if (fileBytes(zipPath(s)) == 0) { wifiServer.send(404, "text/plain", "ZIP not prepared"); return; }
  String dl = String("http://") + WiFi.softAPIP().toString() + ":" + WIFI_ZIP_DOWNLOAD_PORT + "/" + s + ".zip";
  wifiServer.sendHeader("Location", dl);
  wifiServer.send(303, "text/plain", "Use cooperative ZIP download service");
}

static void handleWifiZipDelete() {
  if (storedSessionZipAsyncBusy() || wifiZipDownloadBusy()) { sendPage(F("<h2>An SD transfer is active. Wait or cancel it before deleting.</h2>"), 409); return; }
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h2>Invalid session</h2>"), 400); return; }
  String zp = zipPath(s);
  uint64_t before = fileBytes(zp);
  if (before == 0) { sendPage("<h1>No temporary ZIP</h1><p>" + htmlEscape(s) + ".zip is not present.</p><p><a class='btn secondary' href='/'>Back</a></p>"); return; }
  if (!SD.remove(zp.c_str())) { sendPage(F("<h1>ZIP delete failed</h1><p>The temporary ZIP remains on the microSD.</p>"), 500); return; }
  Serial.printf("# WIFI ZIP DELETED,%s,%llu bytes\n", s.c_str(), (unsigned long long)before);
  wifiServer.sendHeader("Location", "/");
  wifiServer.send(303, "text/plain", "Temporary ZIP deleted");
}

static void handleWifiZipCancel() {
  if (storedSessionZipAsyncBusy()) {
    String s = storedSessionZipAsyncSession();
    cancelStoredSessionZipAsync();
    Serial.printf("# WIFI ZIP CANCELLED,%s\n", s.c_str());
  }
  wifiServer.sendHeader("Location", "/");
  wifiServer.send(303, "text/plain", "ZIP preparation cancelled");
}

static void handleWifiDownloadCancel() {
  if (wifiZipDownloadBusy()) cancelWifiZipDownload();
  wifiServer.sendHeader("Location", "/");
  wifiServer.send(303, "text/plain", "Download cancelled");
}

static void handleWifiClearRequest() {
  if (storedSessionZipAsyncBusy() || wifiZipDownloadBusy()) { sendPage(F("<h2>An SD transfer is active. Wait or cancel it before clearing.</h2>"), 409); return; }
  String s = wifiServer.arg("s");
  if (!validSessionName(s)) { sendPage(F("<h2>Invalid session</h2>"), 400); return; }
  wifiPendingClear = s;
  wifiConfirmPending = true;
  String body = "<h1>Confirm clear</h1><p>Clear contents of <b>" + htmlEscape(s) + "</b> while keeping the empty <b>" + htmlEscape(s) + "</b> folder for session-number continuity?</p>";
  if (fileBytes(zipPath(s)) > 0) body += F("<div class='notice'>A temporary ZIP for this session also exists. It will be deleted first so cleared data is not left behind in /CANLOG/_ZIP.</div>");
  body += "<div class='actions'><form method='POST' action='/clear-confirm'><input type='hidden' name='s' value='" + s + "'><button class='danger' type='submit'>CLEAR CONTENTS OF " + s + "</button></form><a class='btn secondary' href='/'>Cancel</a></div>";
  sendPage(body);
}

static void handleWifiClearConfirm() {
  if (storedSessionZipAsyncBusy() || wifiZipDownloadBusy()) { sendPage(F("<h2>An SD transfer is active. Clear refused.</h2>"), 409); return; }
  String s = wifiServer.arg("s");
  if (!wifiConfirmPending || s != wifiPendingClear || !validSessionName(s)) { sendPage(F("<h2>Confirmation expired or invalid.</h2>"), 400); return; }
  wifiConfirmPending = false;
  wifiPendingClear = "";
  String path = sessionPath(s);
  uint64_t sourceBefore = directoryBytes(path);
  String zp = zipPath(s);
  uint64_t zipBefore = fileBytes(zp);
  if (zipBefore > 0 && !SD.remove(zp.c_str())) {
    sendPage(F("<h1>Clear stopped</h1><p>Temporary ZIP could not be removed, so session contents were not cleared.</p>"), 500);
    return;
  }
  bool ok = clearDirectoryContents(path);
  if (ok && SD.exists(path.c_str())) {
    uint64_t freed = sourceBefore + zipBefore;
    sendPage("<h1>Cleared " + htmlEscape(s) + "</h1><p>Freed approximately <b>" + humanBytes(freed) + "</b>. The empty session folder was retained for v2.4.2 numbering continuity.</p><p><a class='btn secondary' href='/'>Back</a></p>");
  } else {
    sendPage("<h1>Clear incomplete</h1><p>Stopped on SD error. The session folder was not intentionally removed.</p><p><a class='btn secondary' href='/'>Back</a></p>", 500);
  }
}

static void handleWifiExit() {
  if (storedSessionZipAsyncBusy()) cancelStoredSessionZipAsync();
  if (wifiZipDownloadBusy()) cancelWifiZipDownload();
  wifiServer.send(200, "text/plain", "Restarting logger...");
  delay(250);
  ESP.restart();
}

static void wifiEventHandler(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_AP_STACONNECTED) {
    const wifi_event_ap_staconnected_t &e = info.wifi_ap_staconnected;
    Serial.printf("# WIFI STA CONNECTED,%02X:%02X:%02X:%02X:%02X:%02X,AID=%u\n",
                  e.mac[0], e.mac[1], e.mac[2], e.mac[3], e.mac[4], e.mac[5], (unsigned)e.aid);
  } else if (event == ARDUINO_EVENT_WIFI_AP_STADISCONNECTED) {
    const wifi_event_ap_stadisconnected_t &e = info.wifi_ap_stadisconnected;
    Serial.printf("# WIFI STA DISCONNECTED,%02X:%02X:%02X:%02X:%02X:%02X,AID=%u,REASON=%u\n",
                  e.mac[0], e.mac[1], e.mac[2], e.mac[3], e.mac[4], e.mac[5],
                  (unsigned)e.aid, (unsigned)e.reason);
  }
}

static void serviceWifiMaintenanceUi() {
  uint32_t nowMs = millis();
  if (nowMs - lastWifiUiMs < 500) return;
  lastWifiUiMs = nowMs;
  uint8_t clients = (uint8_t)WiFi.softAPgetStationNum();

  tft.fillRect(15, 225, 455, 55, TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString(String("Clients: ") + clients + "   CH: " + CYD_WIFI_CHANNEL + "   Sleep: OFF", 20, 228, 2);
  if (wifiZipDownloadBusy()) {
    tft.drawString(String("DL ") + wifiZipDownloadSession() + ": " + wifiZipDownloadProgress() + "%", 20, 252, 2);
  } else if (storedSessionZipAsyncBusy()) {
    tft.drawString(String("ZIP ") + storedSessionZipAsyncSession() + ": " + storedSessionZipAsyncProgress() + "%", 20, 252, 2);
  } else if (storedSessionZipAsyncDone()) {
    tft.drawString(String("ZIP ready: ") + storedSessionZipAsyncSession(), 20, 252, 2);
  } else if (storedSessionZipAsyncFailed()) {
    tft.drawString("ZIP last result: stopped/error", 20, 252, 2);
  }
}

static void shutdownLoggerServicesForWifi() {
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

  WiFi.onEvent(wifiEventHandler);
  WiFi.mode(WIFI_AP);
  esp_err_t psResult = esp_wifi_set_ps(WIFI_PS_NONE);
  Serial.printf("# WIFI AP CONFIG,channel=%u,max_clients=%u,power_save=OFF,ps_result=%d\n",
                (unsigned)CYD_WIFI_CHANNEL, (unsigned)CYD_WIFI_MAX_CLIENTS, (int)psResult);

  if (!WiFi.softAP(wifiApSsid, wifiApPassword, CYD_WIFI_CHANNEL, false, CYD_WIFI_MAX_CLIENTS)) {
    tft.fillScreen(TFT_RED);
    tft.setTextColor(TFT_WHITE, TFT_RED);
    tft.drawString("WIFI AP FAILED", 40, 110, 4);
    tft.drawString("RESTART REQUIRED", 40, 160, 3);
    return;
  }

  wifiServer.on("/", HTTP_GET, handleWifiRoot);
  wifiServer.on("/session", HTTP_GET, handleWifiSession);
  wifiServer.on("/download", HTTP_GET, handleWifiDownload);
  wifiServer.on("/zip-create", HTTP_POST, handleWifiZipCreate);
  wifiServer.on("/zip-download", HTTP_GET, handleWifiZipDownload);
  wifiServer.on("/zip-delete", HTTP_POST, handleWifiZipDelete);
  wifiServer.on("/zip-cancel", HTTP_POST, handleWifiZipCancel);
  wifiServer.on("/download-cancel", HTTP_POST, handleWifiDownloadCancel);
  wifiServer.on("/clear", HTTP_GET, handleWifiClearRequest);
  wifiServer.on("/clear-confirm", HTTP_POST, handleWifiClearConfirm);
  wifiServer.on("/exit", HTTP_GET, handleWifiExit);
  wifiServer.onNotFound([](){ wifiServer.send(404, "text/plain", "Not found"); });
  wifiServer.begin();
  beginWifiZipDownloadServer();

  Serial.printf("# WIFI AP READY,%s,http://%s,channel=%u,zip_download_port=%u\n",
                wifiApSsid, WiFi.softAPIP().toString().c_str(), (unsigned)CYD_WIFI_CHANNEL,
                (unsigned)WIFI_ZIP_DOWNLOAD_PORT);
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("WIFI FILE MAINTENANCE", 20, 20, 4);
  tft.drawString(String("SSID: ") + wifiApSsid, 20, 80, 2);
  tft.drawString(String("PASS: ") + wifiApPassword, 20, 110, 2);
  tft.drawString(String("OPEN: http://") + WiFi.softAPIP().toString(), 20, 140, 2);
  tft.drawString(String("CAN DB: v") + TOYOTA_CAN_DB_VERSION, 20, 170, 2);
  tft.drawString("EXIT from browser restarts logger", 20, 200, 2);
  lastWifiUiMs = 0;
  serviceWifiMaintenanceUi();
}

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
  logger242_setup();
  Serial.printf("# v2.4.4 RC1 wrapper ready; Wi-Fi OFF; CAN DB v%s; decoded IDs=%u\n",
                TOYOTA_CAN_DB_VERSION, (unsigned)DB_DECODED_ID_COUNT);
  updateDisplay();
}

static void serviceWifiMaintenanceMode() {
  wifiServer.handleClient();
  serviceWifiZipDownload();
  if (!wifiZipDownloadBusy()) serviceStoredSessionZipAsync();
  serviceWifiMaintenanceUi();

  if (!wifiZipCompletionLogged && storedSessionZipAsyncDone()) {
    Serial.printf("# WIFI ZIP ASYNC READY,%s,%llu bytes\n",
                  storedSessionZipAsyncSession().c_str(),
                  (unsigned long long)storedSessionZipAsyncBytes());
    wifiZipCompletionLogged = true;
  } else if (!wifiZipCompletionLogged && storedSessionZipAsyncFailed()) {
    Serial.printf("# WIFI ZIP ASYNC STOPPED,%s,%s\n",
                  storedSessionZipAsyncSession().c_str(),
                  storedSessionZipAsyncError().c_str());
    wifiZipCompletionLogged = true;
  }
}

void loop() {
  if (wifiMaintenanceMode) {
    serviceWifiMaintenanceMode();
    delay(1);
    return;
  }

  handleTouch();
  if (wifiMaintenanceMode) {
    serviceWifiMaintenanceMode();
    delay(1);
    return;
  }

  uint32_t displayStampBefore = lastDisplayMs;
  logger242_loop();
  if (lastDisplayMs != displayStampBefore && !wifiMaintenanceMode) drawButtons();
}
