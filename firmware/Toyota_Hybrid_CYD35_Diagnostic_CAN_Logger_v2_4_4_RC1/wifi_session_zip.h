#pragma once

#include <Arduino.h>
#include <SD.h>

// Minimal ZIP writer for Wi-Fi maintenance mode.
// Uses ZIP method 0 (STORE / no compression) deliberately: no extra ZIP library,
// deterministic RAM use, and no impact on the logger runtime. The temporary ZIP
// therefore needs approximately the same free SD space as the selected session.

struct WifiZipEntry {
  char name[64];
  uint32_t size;
  uint32_t crc32;
  uint32_t localOffset;
};

static bool zipWrite16(File &out, uint16_t value) {
  uint8_t b[2] = { (uint8_t)(value & 0xFF), (uint8_t)((value >> 8) & 0xFF) };
  return out.write(b, sizeof(b)) == sizeof(b);
}

static bool zipWrite32(File &out, uint32_t value) {
  uint8_t b[4] = {
    (uint8_t)(value & 0xFF),
    (uint8_t)((value >> 8) & 0xFF),
    (uint8_t)((value >> 16) & 0xFF),
    (uint8_t)((value >> 24) & 0xFF)
  };
  return out.write(b, sizeof(b)) == sizeof(b);
}

static uint32_t zipCrc32File(File &file, bool &ok) {
  uint32_t crc = 0xFFFFFFFFUL;
  uint8_t buffer[1024];
  ok = true;
  while (file.available()) {
    size_t count = file.read(buffer, sizeof(buffer));
    if (count == 0) { ok = false; break; }
    for (size_t i = 0; i < count; ++i) {
      crc ^= buffer[i];
      for (uint8_t bit = 0; bit < 8; ++bit) {
        crc = (crc >> 1) ^ (0xEDB88320UL & (uint32_t)-(int32_t)(crc & 1));
      }
    }
  }
  return crc ^ 0xFFFFFFFFUL;
}

static bool zipCopyFile(File &input, File &output) {
  uint8_t buffer[2048];
  while (input.available()) {
    size_t count = input.read(buffer, sizeof(buffer));
    if (count == 0) return false;
    if (output.write(buffer, count) != count) return false;
    delay(0);
  }
  return true;
}

static bool buildStoredSessionZip(const String &session, const String &sourcePath,
                                  const String &zipPath, uint64_t sourceBytes,
                                  uint64_t &zipBytes, String &error) {
  constexpr size_t MAX_ZIP_FILES = 64;
  WifiZipEntry entries[MAX_ZIP_FILES];
  size_t entryCount = 0;
  zipBytes = 0;
  error = "";

  // STORE ZIP needs roughly source size plus headers. Keep a safety margin so
  // the archive never intentionally fills the card to the last sector.
  uint64_t total = SD.totalBytes();
  uint64_t used = SD.usedBytes();
  uint64_t freeBytes = total > used ? total - used : 0;
  uint64_t required = sourceBytes + 65536ULL;
  if (freeBytes < required) {
    error = "Not enough free SD space for temporary ZIP (needs source size plus 64 KB safety margin).";
    return false;
  }

  File dir = SD.open(sourcePath.c_str());
  if (!dir || !dir.isDirectory()) {
    if (dir) dir.close();
    error = "Session directory not found.";
    return false;
  }

  File item = dir.openNextFile();
  while (item) {
    if (item.isDirectory()) {
      item.close();
      dir.close();
      error = "Nested directories are not supported in RC1 session ZIPs.";
      return false;
    }
    if (entryCount >= MAX_ZIP_FILES) {
      item.close();
      dir.close();
      error = "Session has more than 64 files; ZIP not created.";
      return false;
    }

    String fullName = String(item.name());
    int slash = fullName.lastIndexOf('/');
    String baseName = slash >= 0 ? fullName.substring(slash + 1) : fullName;
    if (baseName.length() == 0 || baseName.length() >= sizeof(entries[entryCount].name)) {
      item.close();
      dir.close();
      error = "A session filename is too long for the RC1 ZIP writer.";
      return false;
    }
    if (item.size() > 0xFFFFFFFFULL) {
      item.close();
      dir.close();
      error = "A session file exceeds classic ZIP 4 GB limits.";
      return false;
    }

    bool crcOk = false;
    uint32_t crc = zipCrc32File(item, crcOk);
    uint32_t size = (uint32_t)item.size();
    item.close();
    if (!crcOk) {
      dir.close();
      error = "Failed while calculating file CRC.";
      return false;
    }

    memset(&entries[entryCount], 0, sizeof(entries[entryCount]));
    strncpy(entries[entryCount].name, baseName.c_str(), sizeof(entries[entryCount].name) - 1);
    entries[entryCount].size = size;
    entries[entryCount].crc32 = crc;
    ++entryCount;
    item = dir.openNextFile();
  }
  dir.close();

  if (entryCount == 0) {
    error = "Session is empty; no ZIP created.";
    return false;
  }

  if (SD.exists(zipPath.c_str()) && !SD.remove(zipPath.c_str())) {
    error = "Could not replace existing temporary ZIP.";
    return false;
  }

  File out = SD.open(zipPath.c_str(), FILE_WRITE);
  if (!out) {
    error = "Could not create temporary ZIP on SD.";
    return false;
  }

  bool ok = true;
  for (size_t i = 0; i < entryCount && ok; ++i) {
    String zipName = session + "/" + String(entries[i].name);
    if (zipName.length() > 0xFFFF) { ok = false; break; }
    if (out.position() > 0xFFFFFFFFULL) { ok = false; break; }
    entries[i].localOffset = (uint32_t)out.position();

    ok = zipWrite32(out, 0x04034B50UL) && // local file header
         zipWrite16(out, 20) &&           // version needed
         zipWrite16(out, 0) &&            // flags
         zipWrite16(out, 0) &&            // method: STORE
         zipWrite16(out, 0) && zipWrite16(out, 0) && // DOS time/date
         zipWrite32(out, entries[i].crc32) &&
         zipWrite32(out, entries[i].size) &&
         zipWrite32(out, entries[i].size) &&
         zipWrite16(out, (uint16_t)zipName.length()) &&
         zipWrite16(out, 0) &&
         out.write((const uint8_t *)zipName.c_str(), zipName.length()) == zipName.length();
    if (!ok) break;

    String inputPath = sourcePath + "/" + String(entries[i].name);
    File input = SD.open(inputPath.c_str(), FILE_READ);
    if (!input || input.isDirectory()) {
      if (input) input.close();
      ok = false;
      break;
    }
    ok = zipCopyFile(input, out);
    input.close();
  }

  uint32_t centralOffset = 0;
  uint32_t centralSize = 0;
  if (ok) {
    if (out.position() > 0xFFFFFFFFULL) ok = false;
    else centralOffset = (uint32_t)out.position();
  }

  for (size_t i = 0; i < entryCount && ok; ++i) {
    String zipName = session + "/" + String(entries[i].name);
    ok = zipWrite32(out, 0x02014B50UL) && // central directory header
         zipWrite16(out, 20) && zipWrite16(out, 20) &&
         zipWrite16(out, 0) && zipWrite16(out, 0) &&
         zipWrite16(out, 0) && zipWrite16(out, 0) &&
         zipWrite32(out, entries[i].crc32) &&
         zipWrite32(out, entries[i].size) &&
         zipWrite32(out, entries[i].size) &&
         zipWrite16(out, (uint16_t)zipName.length()) &&
         zipWrite16(out, 0) && zipWrite16(out, 0) &&
         zipWrite16(out, 0) && zipWrite16(out, 0) &&
         zipWrite32(out, 0) &&
         zipWrite32(out, entries[i].localOffset) &&
         out.write((const uint8_t *)zipName.c_str(), zipName.length()) == zipName.length();
  }

  if (ok) {
    uint64_t pos = out.position();
    if (pos > 0xFFFFFFFFULL || pos < centralOffset) ok = false;
    else centralSize = (uint32_t)(pos - centralOffset);
  }

  if (ok) {
    ok = zipWrite32(out, 0x06054B50UL) && // end of central directory
         zipWrite16(out, 0) && zipWrite16(out, 0) &&
         zipWrite16(out, (uint16_t)entryCount) &&
         zipWrite16(out, (uint16_t)entryCount) &&
         zipWrite32(out, centralSize) &&
         zipWrite32(out, centralOffset) &&
         zipWrite16(out, 0);
  }

  out.flush();
  zipBytes = out.size();
  out.close();

  if (!ok) {
    SD.remove(zipPath.c_str());
    error = "ZIP write failed; incomplete temporary ZIP removed.";
    zipBytes = 0;
    return false;
  }
  return true;
}
