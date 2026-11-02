#if defined(PANEL_PROFILE_S2_MINI)

PanelMapDraft mappingDraft;
uint32_t mappingOwner = 0, mappingDraftAt = 0, mappingPreviewOwner = 0, mappingPreviewAt = 0;
int mappingSlot = 0;
bool mappingUploading = false;

bool loadStoredMapping() {
  if (sMATRIX_TYPE != 2) return false;
  Preferences preferences;
  if (!preferences.begin("panel-layout", true)) return false;
  PanelMapRecord record;
  bool ok = preferences.getBytesLength("map") == sizeof(record) &&
    preferences.getBytes("map", &record, sizeof(record)) == sizeof(record);
  preferences.end();
  if (!ok || !record.valid() || record.map.width != pWIDTH || record.map.height != pHEIGHT) return false;
  imap = new (std::nothrow) int16_t[uint16_t(pWIDTH) * pHEIGHT];
  if (!imap) return false;
  for (int y = 0; y < pHEIGHT; ++y) for (int x = 0; x < pWIDTH; ++x)
    imap[x + (pHEIGHT - y - 1) * pWIDTH] = record.map.at(x, y);
  // The active custom layout is stored in NVS, independently of filesystem OTA.
  char name[12];
  snprintf(name, sizeof(name), "%ux%u", unsigned(pWIDTH), unsigned(pHEIGHT));
  mapFiles[0] = name;
  mapListLen = 1;
  return true;
}

void mappingReply(uint32_t client, const char* kind, const char* op, const String& error = String()) {
  if (!ws.availableForWrite(client)) return;
  DynamicJsonDocument payload(4096);
  payload["kind"] = kind;
  payload["op"] = op;
  payload["error"] = error;
  if (String(kind) == "state") {
    payload["width"] = pWIDTH;
    payload["height"] = pHEIGHT;
    payload["slots"] = 200;
    payload["watchdogSeconds"] = 30;
    String text;
    // Export the actual active addressing, including ordinary segment wiring.
    for (int id = 0; id < 200; ++id) {
      bool found = false;
      for (int y = 0; y < pHEIGHT && !found; ++y) {
        for (int x = 0; x < pWIDTH; ++x) {
          if (getPixelNumber(x, y) == id) {
            text += String(id + 1) + ":" + x + "," + y + "\n";
            found = true; break;
          }
        }
      }
      if (id % 8 == 0) delay(1);
    }
    payload["text"] = text;
  }
  String body, message;
  serializeJson(payload, body);
  StaticJsonDocument<96> envelope;
  envelope["e"] = "mapping";
  envelope["d"] = body.c_str();
  serializeJson(envelope, message);
  ws.text(client, message);
}

void handleMappingCommand(const String& text, uint32_t client) {
  DynamicJsonDocument command(2048);
  if (deserializeJson(command, text)) return;
  String op = command["op"] | "";
  if (op == "state") { mappingReply(client, "state", "state"); return; }
  if (op == "identify") {
    if (isTurnedOff) { mappingReply(client, "error", "identify", "Turn the panel on before identifying LEDs."); return; }
    int id = command["id"] | 0;
    if (id < 1 || id > 200) { mappingReply(client, "error", "identify", "Use a slot from 1 to 200."); return; }
    mappingSlot = id; mappingPreviewOwner = client; mappingPreviewAt = millis();
    mappingReply(client, "ack", "identify"); return;
  }
  if (op == "stop") {
    if (mappingPreviewOwner == client) mappingSlot = 0;
    return;
  }
  if (op == "begin") {
    if (mappingUploading && mappingOwner != client && millis() - mappingDraftAt < 30000 && ws.hasClient(mappingOwner)) {
      mappingReply(client, "error", "begin", "Another browser is saving a map."); return;
    }
    int width = command["width"] | 0, height = command["height"] | 0;
    if (!mappingDraft.dimensions(width, height)) {
      mappingReply(client, "error", "begin", "Use dimensions 8..64 with at most 2048 cells."); return;
    }
    mappingOwner = client; mappingDraftAt = millis(); mappingUploading = true;
    mappingReply(client, "ack", "begin"); return;
  }
  if (!mappingUploading || mappingOwner != client || millis() - mappingDraftAt >= 30000) {
    mappingReply(client, "error", op.c_str(), "Map save expired; try again."); return;
  }
  mappingDraftAt = millis();
  if (op == "chunk") {
    JsonArray rows = command["rows"].as<JsonArray>();
    if (rows.isNull() || rows.size() > 10) {
      mappingUploading = false;
      mappingReply(client, "error", "chunk", "Invalid map chunk."); return;
    }
    for (JsonVariant row : rows) {
      if (!row.is<JsonArray>() || row.size() != 3 || !row[0].is<int>() || !row[1].is<int>() || !row[2].is<int>() ||
          !mappingDraft.assign(row[0].as<int>(), row[1].as<int>(), row[2].as<int>())) {
        mappingUploading = false;
        mappingReply(client, "error", "chunk", "Duplicate or out-of-range slot/coordinate."); return;
      }
    }
    mappingReply(client, "ack", "chunk"); return;
  }
  if (op != "commit") return;
  mappingUploading = false;
  if (!mappingDraft.count()) { mappingReply(client, "error", "commit", "Assign at least one LED."); return; }
  // Preserve the active custom layout across future filesystem OTA updates.
  Preferences preferences;
  PanelMapRecord record;
  record.map = mappingDraft;
  bool stored = preferences.begin("panel-layout", false);
  if (stored) {
    stored = preferences.putBytes("map", &record, sizeof(record)) == sizeof(record);
    preferences.end();
  }
  if (!stored) {
    mappingReply(client, "error", "commit", "Could not persist active map; settings were not changed."); return;
  }
  putMatrixMapWidth(mappingDraft.width); putMatrixMapHeight(mappingDraft.height);
  putMatrixSegmentType(2);
  saveSettings();
  mappingSlot = 0;
  mappingReply(client, "saved", "commit");
  needRestart = true; needRestartTime = millis();
}

bool renderMappingPreview() {
  static bool wasActive = false;
  static uint32_t lastFrame = 0;
  if (mappingSlot && (isTurnedOff || !ws.hasClient(mappingPreviewOwner) || millis() - mappingPreviewAt >= 10000)) mappingSlot = 0;
  if (!mappingSlot) {
    if (wasActive) { FastLED.clear(); loadingFlag = true; wasActive = false; }
    return false;
  }
  wasActive = true;
  if (millis() - lastFrame >= 50) {
    lastFrame = millis();
    FastLED.clear();
    leds[mappingSlot - 1] = CRGB::White;
    FastLED.show(3); // Temporary ~1% identification brightness; saved brightness is untouched.
  }
  return true;
}

#endif
