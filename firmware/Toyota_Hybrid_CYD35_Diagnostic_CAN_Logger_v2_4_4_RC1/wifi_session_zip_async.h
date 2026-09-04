#pragma once

#include <Arduino.h>
#include <SD.h>

// Cooperative single-pass STORE ZIP writer for Wi-Fi maintenance mode.
// One bounded SD chunk is processed per service call so the main Wi-Fi loop can
// continue servicing TCP/IP, HTTP, station events, and UI updates.
// ZIP general-purpose bit 3 + data descriptors allow CRC32 and sizes to be
// calculated while each file is copied, avoiding the previous full CRC pre-pass.

struct WifiAsyncZipEntry {
  char name[64];
  uint32_t size;
  uint32_t crc32;
  uint32_t localOffset;
};

enum WifiAsyncZipState : uint8_t {
  WIFI_ZIP_IDLE = 0,
  WIFI_ZIP_WRITING,
  WIFI_ZIP_FINALIZING,
  WIFI_ZIP_DONE,
  WIFI_ZIP_ERROR
};

struct WifiAsyncZipJob {
  WifiAsyncZipState state = WIFI_ZIP_IDLE;
  String session;
  String sourcePath;
  String zipPath;
  String error;
  WifiAsyncZipEntry *entries = nullptr;
  uint8_t *buffer = nullptr;
  size_t entryCount = 0;
  size_t currentIndex = 0;
  uint64_t sourceBytes = 0;
  uint64_t processedBytes = 0;
  uint64_t zipBytes = 0;
  uint32_t currentCrc = 0xFFFFFFFFUL;
  uint32_t currentBytes = 0;
  File input;
  File output;
};

static WifiAsyncZipJob wifiAsyncZip;
static constexpr size_t WIFI_ASYNC_ZIP_MAX_FILES = 64;
static constexpr size_t WIFI_ASYNC_ZIP_IO_BYTES = 4096;

static bool wifiAsyncZipWrite16(File &out, uint16_t value) {
  uint8_t b[2] = { (uint8_t)(value & 0xFF), (uint8_t)((value >> 8) & 0xFF) };
  return out.write(b, sizeof(b)) == sizeof(b);
}

static bool wifiAsyncZipWrite32(File &out, uint32_t value) {
  uint8_t b[4] = {
    (uint8_t)(value & 0xFF),
    (uint8_t)((value >> 8) & 0xFF),
    (uint8_t)((value >> 16) & 0xFF),
    (uint8_t)((value >> 24) & 0xFF)
  };
  return out.write(b, sizeof(b)) == sizeof(b);
}

static uint32_t wifiAsyncZipCrcUpdate(uint32_t crc, const uint8_t *data, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc >> 1) ^ (0xEDB88320UL & (uint32_t)-(int32_t)(crc & 1));
    }
  }
  return crc;
}

static void wifiAsyncZipReleaseWorkspace() {
  if (wifiAsyncZip.input) wifiAsyncZip.input.close();
  if (wifiAsyncZip.output) wifiAsyncZip.output.close();
  if (wifiAsyncZip.buffer) { free(wifiAsyncZip.buffer); wifiAsyncZip.buffer = nullptr; }
  if (wifiAsyncZip.entries) { free(wifiAsyncZip.entries); wifiAsyncZip.entries = nullptr; }
}

static void wifiAsyncZipFail(const String &message) {
  if (wifiAsyncZip.input) wifiAsyncZip.input.close();
  if (wifiAsyncZip.output) {
    wifiAsyncZip.output.flush();
    wifiAsyncZip.output.close();
  }
  if (wifiAsyncZip.zipPath.length()) SD.remove(wifiAsyncZip.zipPath.c_str());
  if (wifiAsyncZip.buffer) { free(wifiAsyncZip.buffer); wifiAsyncZip.buffer = nullptr; }
  if (wifiAsyncZip.entries) { free(wifiAsyncZip.entries); wifiAsyncZip.entries = nullptr; }
  wifiAsyncZip.error = message;
  wifiAsyncZip.zipBytes = 0;
  wifiAsyncZip.state = WIFI_ZIP_ERROR;
}

static bool wifiAsyncZipOpenCurrentFile() {
  if (wifiAsyncZip.currentIndex >= wifiAsyncZip.entryCount) {
    wifiAsyncZip.state = WIFI_ZIP_FINALIZING;
    return true;
  }

  WifiAsyncZipEntry &entry = wifiAsyncZip.entries[wifiAsyncZip.currentIndex];
  String zipName = wifiAsyncZip.session + "/" + String(entry.name);
  if (wifiAsyncZip.output.position() > 0xFFFFFFFFULL) return false;
  entry.localOffset = (uint32_t)wifiAsyncZip.output.position();

  // General-purpose bit 3 means CRC and sizes follow in a data descriptor.
  bool ok = wifiAsyncZipWrite32(wifiAsyncZip.output, 0x04034B50UL) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 20) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 0x0008) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite32(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite32(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite32(wifiAsyncZip.output, 0) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, (uint16_t)zipName.length()) &&
            wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
            wifiAsyncZip.output.write((const uint8_t *)zipName.c_str(), zipName.length()) == zipName.length();
  if (!ok) return false;

  String inputPath = wifiAsyncZip.sourcePath + "/" + String(entry.name);
  wifiAsyncZip.input = SD.open(inputPath.c_str(), FILE_READ);
  if (!wifiAsyncZip.input || wifiAsyncZip.input.isDirectory()) {
    if (wifiAsyncZip.input) wifiAsyncZip.input.close();
    return false;
  }
  wifiAsyncZip.currentCrc = 0xFFFFFFFFUL;
  wifiAsyncZip.currentBytes = 0;
  return true;
}

static bool startStoredSessionZipAsync(const String &session, const String &sourcePath,
                                       const String &zipPath, uint64_t sourceBytes,
                                       String &error) {
  error = "";
  if (wifiAsyncZip.state == WIFI_ZIP_WRITING || wifiAsyncZip.state == WIFI_ZIP_FINALIZING) {
    error = "Another ZIP is already being prepared.";
    return false;
  }

  wifiAsyncZipReleaseWorkspace();
  wifiAsyncZip = WifiAsyncZipJob();
  wifiAsyncZip.session = session;
  wifiAsyncZip.sourcePath = sourcePath;
  wifiAsyncZip.zipPath = zipPath;
  wifiAsyncZip.sourceBytes = sourceBytes;

  uint64_t total = SD.totalBytes();
  uint64_t used = SD.usedBytes();
  uint64_t freeBytes = total > used ? total - used : 0;
  uint64_t required = sourceBytes + 65536ULL;
  if (freeBytes < required) {
    error = "Not enough free SD space for temporary ZIP (needs source size plus 64 KB safety margin).";
    wifiAsyncZip.error = error;
    wifiAsyncZip.state = WIFI_ZIP_ERROR;
    return false;
  }

  wifiAsyncZip.entries = (WifiAsyncZipEntry *)malloc(sizeof(WifiAsyncZipEntry) * WIFI_ASYNC_ZIP_MAX_FILES);
  wifiAsyncZip.buffer = (uint8_t *)malloc(WIFI_ASYNC_ZIP_IO_BYTES);
  if (!wifiAsyncZip.entries || !wifiAsyncZip.buffer) {
    wifiAsyncZipReleaseWorkspace();
    error = "Not enough ESP32 heap for ZIP workspace.";
    wifiAsyncZip.error = error;
    wifiAsyncZip.state = WIFI_ZIP_ERROR;
    return false;
  }
  memset(wifiAsyncZip.entries, 0, sizeof(WifiAsyncZipEntry) * WIFI_ASYNC_ZIP_MAX_FILES);

  File dir = SD.open(sourcePath.c_str());
  if (!dir || !dir.isDirectory()) {
    if (dir) dir.close();
    wifiAsyncZipReleaseWorkspace();
    error = "Session directory not found.";
    wifiAsyncZip.error = error;
    wifiAsyncZip.state = WIFI_ZIP_ERROR;
    return false;
  }

  File item = dir.openNextFile();
  while (item) {
    if (item.isDirectory()) {
      item.close(); dir.close(); wifiAsyncZipReleaseWorkspace();
      error = "Nested directories are not supported in RC1 session ZIPs.";
      wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
    }
    if (wifiAsyncZip.entryCount >= WIFI_ASYNC_ZIP_MAX_FILES) {
      item.close(); dir.close(); wifiAsyncZipReleaseWorkspace();
      error = "Session has more than 64 files; ZIP not created.";
      wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
    }
    String fullName = String(item.name());
    int slash = fullName.lastIndexOf('/');
    String baseName = slash >= 0 ? fullName.substring(slash + 1) : fullName;
    if (baseName.length() == 0 || baseName.length() >= sizeof(wifiAsyncZip.entries[wifiAsyncZip.entryCount].name)) {
      item.close(); dir.close(); wifiAsyncZipReleaseWorkspace();
      error = "A session filename is too long for the RC1 ZIP writer.";
      wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
    }
    if (item.size() > 0xFFFFFFFFULL) {
      item.close(); dir.close(); wifiAsyncZipReleaseWorkspace();
      error = "A session file exceeds classic ZIP 4 GB limits.";
      wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
    }
    strncpy(wifiAsyncZip.entries[wifiAsyncZip.entryCount].name, baseName.c_str(),
            sizeof(wifiAsyncZip.entries[wifiAsyncZip.entryCount].name) - 1);
    wifiAsyncZip.entries[wifiAsyncZip.entryCount].size = (uint32_t)item.size();
    ++wifiAsyncZip.entryCount;
    item.close();
    item = dir.openNextFile();
  }
  dir.close();

  if (wifiAsyncZip.entryCount == 0) {
    wifiAsyncZipReleaseWorkspace();
    error = "Session is empty; no ZIP created.";
    wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
  }

  if (SD.exists(zipPath.c_str()) && !SD.remove(zipPath.c_str())) {
    wifiAsyncZipReleaseWorkspace();
    error = "Could not replace existing temporary ZIP.";
    wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
  }

  wifiAsyncZip.output = SD.open(zipPath.c_str(), FILE_WRITE);
  if (!wifiAsyncZip.output) {
    wifiAsyncZipReleaseWorkspace();
    error = "Could not create temporary ZIP on SD.";
    wifiAsyncZip.error = error; wifiAsyncZip.state = WIFI_ZIP_ERROR; return false;
  }

  wifiAsyncZip.currentIndex = 0;
  wifiAsyncZip.processedBytes = 0;
  wifiAsyncZip.state = WIFI_ZIP_WRITING;
  if (!wifiAsyncZipOpenCurrentFile()) {
    wifiAsyncZipFail("Could not open first ZIP source file or write its header.");
    error = wifiAsyncZip.error;
    return false;
  }
  return true;
}

static void serviceStoredSessionZipAsync() {
  if (wifiAsyncZip.state == WIFI_ZIP_WRITING) {
    if (wifiAsyncZip.currentIndex >= wifiAsyncZip.entryCount) {
      wifiAsyncZip.state = WIFI_ZIP_FINALIZING;
      return;
    }

    if (wifiAsyncZip.input && wifiAsyncZip.input.available()) {
      size_t count = wifiAsyncZip.input.read(wifiAsyncZip.buffer, WIFI_ASYNC_ZIP_IO_BYTES);
      if (count == 0) { wifiAsyncZipFail("ZIP source read failed."); return; }
      if (wifiAsyncZip.output.write(wifiAsyncZip.buffer, count) != count) {
        wifiAsyncZipFail("ZIP SD write failed."); return;
      }
      wifiAsyncZip.currentCrc = wifiAsyncZipCrcUpdate(wifiAsyncZip.currentCrc, wifiAsyncZip.buffer, count);
      wifiAsyncZip.currentBytes += (uint32_t)count;
      wifiAsyncZip.processedBytes += count;
      return;
    }

    if (wifiAsyncZip.input) wifiAsyncZip.input.close();
    WifiAsyncZipEntry &entry = wifiAsyncZip.entries[wifiAsyncZip.currentIndex];
    entry.crc32 = wifiAsyncZip.currentCrc ^ 0xFFFFFFFFUL;
    if (wifiAsyncZip.currentBytes != entry.size) {
      wifiAsyncZipFail("ZIP source size changed or read ended early."); return;
    }

    bool ok = wifiAsyncZipWrite32(wifiAsyncZip.output, 0x08074B50UL) &&
              wifiAsyncZipWrite32(wifiAsyncZip.output, entry.crc32) &&
              wifiAsyncZipWrite32(wifiAsyncZip.output, entry.size) &&
              wifiAsyncZipWrite32(wifiAsyncZip.output, entry.size);
    if (!ok) { wifiAsyncZipFail("ZIP data descriptor write failed."); return; }

    ++wifiAsyncZip.currentIndex;
    if (!wifiAsyncZipOpenCurrentFile()) {
      wifiAsyncZipFail("Could not open next ZIP source file or write its header.");
    }
    return;
  }

  if (wifiAsyncZip.state == WIFI_ZIP_FINALIZING) {
    if (!wifiAsyncZip.output) { wifiAsyncZipFail("ZIP output file is not open."); return; }
    if (wifiAsyncZip.output.position() > 0xFFFFFFFFULL) { wifiAsyncZipFail("ZIP exceeds classic 4 GB offset limits."); return; }
    uint32_t centralOffset = (uint32_t)wifiAsyncZip.output.position();
    bool ok = true;

    for (size_t i = 0; i < wifiAsyncZip.entryCount && ok; ++i) {
      WifiAsyncZipEntry &entry = wifiAsyncZip.entries[i];
      String zipName = wifiAsyncZip.session + "/" + String(entry.name);
      ok = wifiAsyncZipWrite32(wifiAsyncZip.output, 0x02014B50UL) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, 20) && wifiAsyncZipWrite16(wifiAsyncZip.output, 20) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, 0x0008) && wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, 0) && wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
           wifiAsyncZipWrite32(wifiAsyncZip.output, entry.crc32) &&
           wifiAsyncZipWrite32(wifiAsyncZip.output, entry.size) && wifiAsyncZipWrite32(wifiAsyncZip.output, entry.size) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, (uint16_t)zipName.length()) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, 0) && wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
           wifiAsyncZipWrite16(wifiAsyncZip.output, 0) && wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
           wifiAsyncZipWrite32(wifiAsyncZip.output, 0) && wifiAsyncZipWrite32(wifiAsyncZip.output, entry.localOffset) &&
           wifiAsyncZip.output.write((const uint8_t *)zipName.c_str(), zipName.length()) == zipName.length();
    }
    if (!ok) { wifiAsyncZipFail("ZIP central-directory write failed."); return; }

    uint64_t pos = wifiAsyncZip.output.position();
    if (pos > 0xFFFFFFFFULL || pos < centralOffset) { wifiAsyncZipFail("ZIP central-directory size overflow."); return; }
    uint32_t centralSize = (uint32_t)(pos - centralOffset);
    ok = wifiAsyncZipWrite32(wifiAsyncZip.output, 0x06054B50UL) &&
         wifiAsyncZipWrite16(wifiAsyncZip.output, 0) && wifiAsyncZipWrite16(wifiAsyncZip.output, 0) &&
         wifiAsyncZipWrite16(wifiAsyncZip.output, (uint16_t)wifiAsyncZip.entryCount) &&
         wifiAsyncZipWrite16(wifiAsyncZip.output, (uint16_t)wifiAsyncZip.entryCount) &&
         wifiAsyncZipWrite32(wifiAsyncZip.output, centralSize) && wifiAsyncZipWrite32(wifiAsyncZip.output, centralOffset) &&
         wifiAsyncZipWrite16(wifiAsyncZip.output, 0);
    if (!ok) { wifiAsyncZipFail("ZIP end-of-central-directory write failed."); return; }

    wifiAsyncZip.output.flush();
    wifiAsyncZip.zipBytes = wifiAsyncZip.output.size();
    wifiAsyncZip.output.close();
    if (wifiAsyncZip.buffer) { free(wifiAsyncZip.buffer); wifiAsyncZip.buffer = nullptr; }
    if (wifiAsyncZip.entries) { free(wifiAsyncZip.entries); wifiAsyncZip.entries = nullptr; }
    wifiAsyncZip.state = WIFI_ZIP_DONE;
  }
}

static void cancelStoredSessionZipAsync() {
  if (wifiAsyncZip.state != WIFI_ZIP_WRITING && wifiAsyncZip.state != WIFI_ZIP_FINALIZING) return;
  String partial = wifiAsyncZip.zipPath;
  if (wifiAsyncZip.input) wifiAsyncZip.input.close();
  if (wifiAsyncZip.output) wifiAsyncZip.output.close();
  if (wifiAsyncZip.buffer) { free(wifiAsyncZip.buffer); wifiAsyncZip.buffer = nullptr; }
  if (wifiAsyncZip.entries) { free(wifiAsyncZip.entries); wifiAsyncZip.entries = nullptr; }
  if (partial.length()) SD.remove(partial.c_str());
  wifiAsyncZip.error = "ZIP preparation cancelled.";
  wifiAsyncZip.zipBytes = 0;
  wifiAsyncZip.state = WIFI_ZIP_ERROR;
}

static bool storedSessionZipAsyncBusy() {
  return wifiAsyncZip.state == WIFI_ZIP_WRITING || wifiAsyncZip.state == WIFI_ZIP_FINALIZING;
}

static bool storedSessionZipAsyncDone() { return wifiAsyncZip.state == WIFI_ZIP_DONE; }
static bool storedSessionZipAsyncFailed() { return wifiAsyncZip.state == WIFI_ZIP_ERROR; }
static const String &storedSessionZipAsyncSession() { return wifiAsyncZip.session; }
static const String &storedSessionZipAsyncError() { return wifiAsyncZip.error; }
static uint64_t storedSessionZipAsyncBytes() { return wifiAsyncZip.zipBytes; }
static uint8_t storedSessionZipAsyncProgress() {
  if (wifiAsyncZip.sourceBytes == 0) return storedSessionZipAsyncDone() ? 100 : 0;
  uint64_t pct = (wifiAsyncZip.processedBytes * 100ULL) / wifiAsyncZip.sourceBytes;
  if (pct > 100ULL) pct = 100ULL;
  return (uint8_t)pct;
}
