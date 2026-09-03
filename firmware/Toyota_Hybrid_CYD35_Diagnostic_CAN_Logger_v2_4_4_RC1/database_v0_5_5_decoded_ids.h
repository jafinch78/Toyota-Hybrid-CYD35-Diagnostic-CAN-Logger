#pragma once

// Toyota Hybrid CAN Database v0.5.5 firmware manifest.
// Source: database/toyota_hybrid_can_db_v0.5.5.json on
// release/database-v0.5.5-evidence-builder-v1.0.3.
//
// Safety boundary:
//   * This file contains metadata only. It does not transmit CAN requests.
//   * CONTROL_WRITE_QUARANTINED and CANDIDATE definitions are intentionally
//     excluded from the live/confirmed manifest.
//   * Gen 3 pack/profile metadata is included, but no Gen 3 decoder is claimed
//     because v0.5.5 contains no PRIUS_GEN3 definition records.

#include <Arduino.h>

struct DbDecodedId {
  const char *profile;
  uint32_t requestId;
  uint32_t responseId;
  uint8_t service;
  uint8_t pid;
  const char *key;
  const char *grade;
};

constexpr char TOYOTA_CAN_DB_VERSION[] = "0.5.5";
constexpr char TOYOTA_CAN_DB_SOURCE_BRANCH[] = "release/database-v0.5.5-evidence-builder-v1.0.3";

// CONFIRMED/PROBABLE read-only definitions selected for firmware awareness.
// Existing v2.4.2 Gen 2 decoding remains the acquisition-safe implementation;
// PHV/Camry records are initially awareness/passive-correlation definitions and
// must not automatically enable diagnostic transmission.
constexpr DbDecodedId DB_DECODED_IDS[] = {
  // Prius Gen 2 NHW20
  {"PRIUS_GEN2",        0x7E3, 0x7EB, 0x21, 0xCE, "NHW20_BATTERY_ECU_21CE_SOC_CURRENT_BLOCK_VOLTAGES", "CONFIRMED"},
  {"PRIUS_GEN2",        0x7E3, 0x7EB, 0x21, 0xD0, "NHW20_BATTERY_ECU_21D0_BLOCK_HEALTH", "CONFIRMED"},

  // Camry Hybrid Gen 1 AHV40
  {"CAMRY_HYBRID_GEN1", 0x7E2, 0x7EA, 0x21, 0xCE, "AHV40_HYBRID_ECU_21CE_BLOCK_VOLTAGES", "CONFIRMED"},
  {"CAMRY_HYBRID_GEN1", 0x7E2, 0x7EA, 0x13, 0xB0, "AHV40_HYBRID_ECU_13B0_READ_DTC_BY_STATUS", "PROBABLE"},
  {"CAMRY_HYBRID_GEN1", 0x7E2, 0x7EA, 0x13, 0x80, "AHV40_HYBRID_ECU_1380_READ_DTC_BY_STATUS", "PROBABLE"},
  {"CAMRY_HYBRID_GEN1", 0x7E0, 0x7E8, 0x13, 0xB0, "AHV40_ENGINE_ECU_13B0_READ_DTC_BY_STATUS", "PROBABLE"},

  // Prius PHV Gen 1 ZVW35. v0.5.5 promoted these from S0018 AP200 evidence.
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x01, "ZVW35_HYBRID_ECU_2101_ENGINE_AND_SOC", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x61, "ZVW35_HYBRID_ECU_2161_MG1_STATUS", "PROBABLE"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x62, "ZVW35_HYBRID_ECU_2162_MG2_STATUS", "PROBABLE"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x70, "ZVW35_HYBRID_ECU_2170_MG1_INVERTER_TEMPERATURE", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x71, "ZVW35_HYBRID_ECU_2171_MG2_INVERTER_TEMPERATURE", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x75, "ZVW35_HYBRID_ECU_2175_INVERTER_COOLANT_AND_PUMP", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x81, "ZVW35_HYBRID_ECU_2181_EIGHT_BLOCK_VOLTAGES", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x87, "ZVW35_HYBRID_ECU_2187_BATTERY_TEMPERATURES", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x8A, "ZVW35_HYBRID_ECU_218A_POWER_RESOURCE_CURRENTS", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x92, "ZVW35_HYBRID_ECU_2192_BLOCK_EXTREMA", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x95, "ZVW35_HYBRID_ECU_2195_BLOCK_INTERNAL_RESISTANCE", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0x98, "ZVW35_HYBRID_ECU_2198_BATTERY_CURRENT_AND_SOC", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E2, 0x7EA, 0x21, 0xC2, "ZVW35_HYBRID_ECU_21C2_ECU_CODE", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E0, 0x7E8, 0x21, 0xC1, "ZVW35_ENGINE_ECU_21C1_MODEL_SIGNATURE", "CONFIRMED"},
  {"PRIUS_PHV_GEN1",    0x7E0, 0x7E8, 0x09, 0x02, "ZVW35_ENGINE_ECU_0902_VIN", "CONFIRMED"},
};

constexpr size_t DB_DECODED_ID_COUNT = sizeof(DB_DECODED_IDS) / sizeof(DB_DECODED_IDS[0]);

struct DbPackProfile {
  const char *profile;
  const char *platform;
  uint16_t blocks;
  uint16_t cells;
  uint8_t cellsPerBlock;
  const char *chemistry;
};

constexpr DbPackProfile DB_PACK_PROFILES[] = {
  {"PRIUS_GEN2",        "NHW20", 14, 168, 12, "NiMH"},
  {"PRIUS_GEN3",        "ZVW30", 14, 168, 12, "NiMH"},
  {"PRIUS_PHV_GEN1",    "ZVW35",  8,  56,  7, "Li-ion NMC"},
  {"CAMRY_HYBRID_GEN1", "AHV40", 17, 204, 12, "NiMH"},
};
