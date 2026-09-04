#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <SD.h>

// Cooperative single-client ZIP download server on TCP port 81.
// Port 80 remains available for the maintenance/status UI while a large ZIP
// is transferred. One bounded chunk is sent per service call. Only one ZIP
// download is active at a time; concurrent attempts are rejected with 503.

static constexpr uint16_t WIFI_ZIP_DOWNLOAD_PORT = 81;
static constexpr size_t WIFI_ZIP_DOWNLOAD_BUFFER_BYTES = 4096;
static constexpr size_t WIFI_ZIP_DOWNLOAD_REQUEST_MAX = 192;
static constexpr uint32_t WIFI_ZIP_DOWNLOAD_STALL_MS = 15000;

enum WifiZipDownloadState : uint8_t {
  WIFI_DL_IDLE = 0,
  WIFI_DL_READING_REQUEST,
  WIFI_DL_STREAMING,
  WIFI_DL_DONE,
  WIFI_DL_ABORTED,
  WIFI_DL_ERROR
};

struct WifiZipDownloadJob {
  WifiZipDownloadState state = WIFI_DL_IDLE;
  WiFiClient client;
  String requestLine;
  String session;
  String path;
  String error;
  File file;
  uint8_t *buffer = nullptr;
  uint64_t totalBytes = 0;
  uint64_t sentBytes = 0;
  bool firstLineDone = false;
  uint8_t blankLineCount = 0;
  uint32_t lastActivityMs = 0;
};

static WiFiServer wifiZipDownloadServer(WIFI_ZIP_DOWNLOAD_PORT);
static WifiZipDownloadJob wifiZipDownload;

static bool wifiZipDownloadValidSession(const String &s) {
  if (s.length() != 5 || s[0] != 'S') return false;
  for (uint8_t i = 1; i < 5; ++i) if (!isDigit(s[i])) return false;
  return true;
}

static void wifiZipDownloadCloseHandles() {
  if (wifiZipDownload.file) wifiZipDownload.file.close();
  if (wifiZipDownload.client) wifiZipDownload.client.stop();
  if (wifiZipDownload.buffer) {
    free(wifiZipDownload.buffer);
    wifiZipDownload.buffer = nullptr;
  }
}

static void wifiZipDownloadFinish(WifiZipDownloadState state, const String &message = "") {
  wifiZipDownloadCloseHandles();
  wifiZipDownload.error = message;
  wifiZipDownload.state = state;
}

static void wifiZipDownloadPrepareForNewClient(WiFiClient client) {
  wifiZipDownloadCloseHandles();
  wifiZipDownload = WifiZipDownloadJob();
  wifiZipDownload.client = client;
  wifiZipDownload.state = WIFI_DL_READING_REQUEST;
  wifiZipDownload.lastActivityMs = millis();
}

static void beginWifiZipDownloadServer() {
  wifiZipDownloadServer.begin();
  wifiZipDownloadServer.setNoDelay(true);
}

static bool wifiZipDownloadBusy() {
  return wifiZipDownload.state == WIFI_DL_READING_REQUEST || wifiZipDownload.state == WIFI_DL_STREAMING;
}

static bool wifiZipDownloadStreaming() { return wifiZipDownload.state == WIFI_DL_STREAMING; }
static bool wifiZipDownloadDone() { return wifiZipDownload.state == WIFI_DL_DONE; }
static bool wifiZipDownloadAborted() { return wifiZipDownload.state == WIFI_DL_ABORTED; }
static bool wifiZipDownloadFailed() { return wifiZipDownload.state == WIFI_DL_ERROR; }
static String wifiZipDownloadSession() { return wifiZipDownload.session; }
static uint64_t wifiZipDownloadTotalBytes() { return wifiZipDownload.totalBytes; }
static uint64_t wifiZipDownloadSentBytes() { return wifiZipDownload.sentBytes; }
static String wifiZipDownloadError() { return wifiZipDownload.error; }

static uint8_t wifiZipDownloadProgress() {
  if (wifiZipDownload.totalBytes == 0) return 0;
  uint64_t value = (wifiZipDownload.sentBytes * 100ULL) / wifiZipDownload.totalBytes;
  if (value > 100ULL) value = 100ULL;
  return (uint8_t)value;
}

static void wifiZipDownloadSendSimple(WiFiClient &client, int code, const char *status, const char *body) {
  client.printf("HTTP/1.1 %d %s\r\n", code, status);
  client.println("Content-Type: text/plain");
  client.println("Connection: close");
  client.printf("Content-Length: %u\r\n\r\n", (unsigned)strlen(body));
  client.print(body);
  delay(0);
  client.stop();
}

static void cancelWifiZipDownload() {
  if (!wifiZipDownloadBusy()) return;
  String session = wifiZipDownload.session;
  uint64_t sent = wifiZipDownload.sentBytes;
  wifiZipDownloadFinish(WIFI_DL_ABORTED, "Cancelled from maintenance UI.");
  Serial.printf("# WIFI DOWNLOAD CANCELLED,%s,%llu bytes\n",
                session.c_str(), (unsigned long long)sent);
}

static bool wifiZipDownloadStartStream() {
  // Expected request: GET /S0001.zip HTTP/1.1
  if (!wifiZipDownload.requestLine.startsWith("GET /")) return false;
  int pathStart = 5;
  int pathEnd = wifiZipDownload.requestLine.indexOf(' ', pathStart);
  if (pathEnd < 0) return false;
  String requestPath = wifiZipDownload.requestLine.substring(pathStart, pathEnd);
  if (!requestPath.endsWith(".zip")) return false;
  String session = requestPath.substring(0, requestPath.length() - 4);
  if (!wifiZipDownloadValidSession(session)) return false;

  String path = String("/CANLOG/_ZIP/") + session + ".zip";
  File file = SD.open(path.c_str(), FILE_READ);
  if (!file || file.isDirectory()) {
    if (file) file.close();
    wifiZipDownloadSendSimple(wifiZipDownload.client, 404, "Not Found", "ZIP not prepared");
    wifiZipDownload.state = WIFI_DL_ERROR;
    wifiZipDownload.error = "ZIP not prepared.";
    return true;
  }

  uint64_t total = file.size();
  if (total == 0) {
    file.close();
    wifiZipDownloadSendSimple(wifiZipDownload.client, 404, "Not Found", "ZIP is empty");
    wifiZipDownload.state = WIFI_DL_ERROR;
    wifiZipDownload.error = "ZIP is empty.";
    return true;
  }

  uint8_t *buffer = (uint8_t *)malloc(WIFI_ZIP_DOWNLOAD_BUFFER_BYTES);
  if (!buffer) {
    file.close();
    wifiZipDownloadSendSimple(wifiZipDownload.client, 503, "Service Unavailable", "Not enough ESP32 heap for download buffer");
    wifiZipDownload.state = WIFI_DL_ERROR;
    wifiZipDownload.error = "Not enough ESP32 heap for download buffer.";
    return true;
  }

  wifiZipDownload.session = session;
  wifiZipDownload.path = path;
  wifiZipDownload.file = file;
  wifiZipDownload.buffer = buffer;
  wifiZipDownload.totalBytes = total;
  wifiZipDownload.sentBytes = 0;
  wifiZipDownload.lastActivityMs = millis();

  wifiZipDownload.client.println("HTTP/1.1 200 OK");
  wifiZipDownload.client.println("Content-Type: application/zip");
  wifiZipDownload.client.printf("Content-Disposition: attachment; filename=\"%s.zip\"\r\n", session.c_str());
  wifiZipDownload.client.printf("Content-Length: %llu\r\n", (unsigned long long)total);
  wifiZipDownload.client.println("Cache-Control: no-store");
  wifiZipDownload.client.println("Connection: close");
  wifiZipDownload.client.println();
  wifiZipDownload.state = WIFI_DL_STREAMING;

  Serial.printf("# WIFI DOWNLOAD START,%s,%llu bytes\n",
                session.c_str(), (unsigned long long)total);
  return true;
}

static void serviceWifiZipDownload() {
  // Reject a second download connection while one is active. Multiple clients
  // may still use the normal status UI on port 80.
  WiFiClient incoming = wifiZipDownloadServer.available();
  if (incoming) {
    incoming.setNoDelay(true);
    if (wifiZipDownloadBusy()) {
      wifiZipDownloadSendSimple(incoming, 503, "Service Unavailable", "Another ZIP download is active. Retry after it completes.");
    } else {
      wifiZipDownloadPrepareForNewClient(incoming);
    }
  }

  if (wifiZipDownload.state == WIFI_DL_READING_REQUEST) {
    if (!wifiZipDownload.client || !wifiZipDownload.client.connected()) {
      wifiZipDownloadFinish(WIFI_DL_ABORTED, "Client disconnected before request completed.");
      return;
    }

    size_t budget = 256;
    while (budget-- && wifiZipDownload.client.available()) {
      char c = (char)wifiZipDownload.client.read();
      wifiZipDownload.lastActivityMs = millis();
      if (!wifiZipDownload.firstLineDone) {
        if (c == '\n') {
          wifiZipDownload.requestLine.trim();
          wifiZipDownload.firstLineDone = true;
        } else if (c != '\r') {
          if (wifiZipDownload.requestLine.length() >= WIFI_ZIP_DOWNLOAD_REQUEST_MAX) {
            wifiZipDownloadSendSimple(wifiZipDownload.client, 414, "URI Too Long", "Request too long");
            wifiZipDownload.state = WIFI_DL_ERROR;
            wifiZipDownload.error = "Download request too long.";
            return;
          }
          wifiZipDownload.requestLine += c;
        }
      } else {
        if (c == '\n') ++wifiZipDownload.blankLineCount;
        else if (c != '\r') wifiZipDownload.blankLineCount = 0;
        if (wifiZipDownload.blankLineCount >= 2) break;
      }
    }

    if (wifiZipDownload.firstLineDone && wifiZipDownload.blankLineCount >= 2) {
      if (!wifiZipDownloadStartStream()) {
        wifiZipDownloadSendSimple(wifiZipDownload.client, 400, "Bad Request", "Expected /Sxxxx.zip");
        wifiZipDownload.state = WIFI_DL_ERROR;
        wifiZipDownload.error = "Invalid ZIP download request.";
      }
      return;
    }

    if (millis() - wifiZipDownload.lastActivityMs > WIFI_ZIP_DOWNLOAD_STALL_MS) {
      wifiZipDownloadFinish(WIFI_DL_ABORTED, "Download request timed out.");
    }
    return;
  }

  if (wifiZipDownload.state != WIFI_DL_STREAMING) return;

  if (!wifiZipDownload.client || !wifiZipDownload.client.connected()) {
    String session = wifiZipDownload.session;
    uint64_t sent = wifiZipDownload.sentBytes;
    wifiZipDownloadFinish(WIFI_DL_ABORTED, "Client disconnected during download.");
    Serial.printf("# WIFI DOWNLOAD ABORTED,%s,%llu bytes\n",
                  session.c_str(), (unsigned long long)sent);
    return;
  }

  if (wifiZipDownload.sentBytes >= wifiZipDownload.totalBytes) {
    String session = wifiZipDownload.session;
    uint64_t total = wifiZipDownload.totalBytes;
    wifiZipDownloadFinish(WIFI_DL_DONE);
    Serial.printf("# WIFI DOWNLOAD COMPLETE,%s,%llu bytes\n",
                  session.c_str(), (unsigned long long)total);
    return;
  }

  if (!wifiZipDownload.file || !wifiZipDownload.file.available()) {
    String session = wifiZipDownload.session;
    uint64_t sent = wifiZipDownload.sentBytes;
    wifiZipDownloadFinish(WIFI_DL_ERROR, "ZIP file ended before expected Content-Length.");
    Serial.printf("# WIFI DOWNLOAD ERROR,%s,%llu bytes,file ended early\n",
                  session.c_str(), (unsigned long long)sent);
    return;
  }

  size_t remaining = (size_t)min((uint64_t)WIFI_ZIP_DOWNLOAD_BUFFER_BYTES,
                                wifiZipDownload.totalBytes - wifiZipDownload.sentBytes);
  size_t count = wifiZipDownload.file.read(wifiZipDownload.buffer, remaining);
  if (count == 0) {
    wifiZipDownloadFinish(WIFI_DL_ERROR, "ZIP SD read failed.");
    return;
  }

  size_t written = wifiZipDownload.client.write(wifiZipDownload.buffer, count);
  if (written == 0) {
    // Seek back because no bytes from this chunk were accepted by TCP.
    wifiZipDownload.file.seek(wifiZipDownload.file.position() - count);
    if (millis() - wifiZipDownload.lastActivityMs > WIFI_ZIP_DOWNLOAD_STALL_MS) {
      String session = wifiZipDownload.session;
      uint64_t sent = wifiZipDownload.sentBytes;
      wifiZipDownloadFinish(WIFI_DL_ABORTED, "Client stalled during download.");
      Serial.printf("# WIFI DOWNLOAD ABORTED,%s,%llu bytes,stall\n",
                    session.c_str(), (unsigned long long)sent);
    }
    return;
  }

  if (written < count) {
    // Preserve any unwritten tail for the next service call.
    wifiZipDownload.file.seek(wifiZipDownload.file.position() - (count - written));
  }
  wifiZipDownload.sentBytes += written;
  wifiZipDownload.lastActivityMs = millis();
  delay(0);
}
