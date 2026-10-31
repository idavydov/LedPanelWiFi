#if defined(IR_RECEIVE_PIN)

IRrecv irReceiver(IR_RECEIVE_PIN, 256, 15, true);
IRBindings irBindings;
IRPressTracker irPress;
IRLogLimiter irLog;
QueueHandle_t irCommands = nullptr;
struct IRCommand { uint32_t client; char text[192]; };
const char* const irActions[] = {"up", "right", "down", "left", "play", "next", "maze", "snake", "tetris", "arkanoid"};
int8_t irLearning = -1;
uint32_t irLearningOwner = 0, irLearningStarted = 0, irWatchingAt = 0, irWatchingOwner = 0;
uint32_t irLastDispatch = 0, irSequence = 0, irQuietAt = 0;
bool irWatching = false, irWaitForRelease = false;
String irNotice;

String irCodeId(int16_t protocol, uint16_t bits, uint64_t value) {
  char hex[17];
  snprintf(hex, sizeof(hex), "%016llX", (unsigned long long)value);
  return String(protocol) + ":" + String(bits) + ":" + hex;
}

void irSendMessage(JsonDocument& payload, uint32_t client = 0) {
  if (client ? !ws.availableForWrite(client) : !ws.availableForWriteAll()) return;
  String body;
  serializeJson(payload, body);
  StaticJsonDocument<96> envelope;
  envelope["e"] = "ir";
  envelope["d"] = body.c_str();
  String message;
  serializeJson(envelope, message);
  if (client) ws.text(client, message);
  else ws.textAll(message);
}

const char* irResetReason() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "Power on";
    case ESP_RST_BROWNOUT: return "Brownout (low supply voltage)";
    case ESP_RST_PANIC: return "Software crash";
    case ESP_RST_INT_WDT: return "Interrupt watchdog";
    case ESP_RST_TASK_WDT: return "Task watchdog";
    case ESP_RST_WDT: return "Watchdog";
    case ESP_RST_SW: return "Software restart";
    case ESP_RST_EXT: return "Reset pin";
    default: return "Other / unknown";
  }
}

void irSendState(uint32_t client = 0) {
  DynamicJsonDocument state(8192);
  state["kind"] = "state";
  state["pin"] = IR_RECEIVE_PIN;
  state["level"] = digitalRead(IR_RECEIVE_PIN);
  state["uptime"] = millis() / 1000;
  state["heap"] = ESP.getFreeHeap();
  state["minHeap"] = ESP.getMinFreeHeap();
  state["largestHeapBlock"] = ESP.getMaxAllocHeap();
  state["rssi"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  state["resetReason"] = irResetReason();
  state["logSkipped"] = irLog.skipped;
  state["capacity"] = IRBindings::capacity;
  state["learning"] = irLearning >= 0 ? irActions[irLearning] : "";
  state["notice"] = irNotice;
  JsonArray list = state.createNestedArray("bindings");
  for (uint8_t i = 0; i < irBindings.count; ++i) {
    const IRBinding& binding = irBindings.entries[i];
    JsonObject item = list.createNestedObject();
    item["id"] = irCodeId(binding.code.protocol, binding.code.bits, binding.code.value);
    item["action"] = irActions[binding.action];
    item["protocol"] = typeToString((decode_type_t)binding.code.protocol);
    item["bits"] = binding.code.bits;
    char value[17];
    snprintf(value, sizeof(value), "%016llX", (unsigned long long)binding.code.value);
    item["code"] = value;
  }
  irSendMessage(state, client);
}

bool irPersistBindings(const IRBindings& updated) {
  Preferences preferences;
  if (!preferences.begin("panel-ir", false)) return false;
  bool ok = preferences.putBytes("bindings", &updated, sizeof(updated)) == sizeof(updated);
  preferences.end();
  if (ok) irBindings = updated;
  return ok;
}

void initializeIRRemote() {
  irCommands = xQueueCreate(8, sizeof(IRCommand));
  if (!irCommands) return;
  Preferences preferences;
  if (preferences.begin("panel-ir", true)) {
    IRBindings stored;
    if (preferences.getBytesLength("bindings") == sizeof(stored) &&
        preferences.getBytes("bindings", &stored, sizeof(stored)) == sizeof(stored) && stored.valid())
      irBindings = stored;
    preferences.end();
  }
  irReceiver.enableIRIn();
}

void enqueueIRCommand(const String& text, uint32_t client) {
  if (!irCommands || text.length() >= sizeof(IRCommand::text)) return;
  IRCommand command = {};
  command.client = client;
  text.toCharArray(command.text, sizeof(command.text));
  xQueueSend(irCommands, &command, 0);
}

void irHandleCommand(const char* text, uint32_t client) {
  StaticJsonDocument<256> command;
  if (deserializeJson(command, text)) return;
  String operation = command["op"] | "";
  if (operation == "state") {
    bool watching = command["watch"] | true;
    if (watching || irWatchingOwner == client) {
      irWatching = watching;
      irWatchingOwner = watching ? client : 0;
      irWatchingAt = millis();
    }
    irSendState(client);
    return;
  }
  if (operation == "learn") {
    String action = command["action"] | "";
    for (uint8_t i = 0; i < IR_ACTION_COUNT; ++i) {
      if (action != irActions[i]) continue;
      irLearning = i;
      irLearningOwner = client;
      irLearningStarted = millis();
      irWaitForRelease = true;
      irQuietAt = millis() - 350;
      irNotice = "Press a remote button within 15 seconds.";
      irSendState();
      return;
    }
  } else if (operation == "cancel") {
    if (irLearningOwner == client) {
      irLearning = -1;
      irNotice = "Learning cancelled.";
    }
  } else if (operation == "remove") {
    String id = command["id"] | "";
    for (uint8_t i = 0; i < irBindings.count; ++i) {
      const IRCode& code = irBindings.entries[i].code;
      if (id != irCodeId(code.protocol, code.bits, code.value)) continue;
      IRBindings updated = irBindings;
      updated.remove(i);
      irNotice = irPersistBindings(updated) ? "Binding removed." : "Could not save binding changes.";
      break;
    }
  }
  irSendState();
}

bool irGameSelected() {
  return thisMode == MC_MAZE || thisMode == MC_SNAKE || thisMode == MC_TETRIS || thisMode == MC_ARKANOID;
}

String irApplyAction(uint8_t action, bool held, uint32_t now) {
  if (isTurnedOff || isNightClock) return "ignored: panel is off";
  if (action >= IR_PLAY && held) return "ignored: held control button";
  if (held && uint32_t(now - irLastDispatch) < uint32_t(getGameButtonSpeed()) * 10)
    return "ignored: repeat throttled";
  irLastDispatch = now;
  if (action <= IR_LEFT) {
    if (!irGameSelected() || gameDemo) return "ignored: choose a game first";
    buttons = action;
    gamePaused = false;
  } else if (action == IR_PLAY) {
    if (!irGameSelected() || gameDemo) return "ignored: choose a game first";
    gamePaused = !gamePaused;
  } else {
    const uint8_t modes[] = {MC_MAZE, MC_SNAKE, MC_TETRIS, MC_ARKANOID};
    uint8_t selected = 0;
    if (action == IR_NEXT) {
      for (uint8_t i = 0; i < 4; ++i) if (thisMode == modes[i]) selected = (i + 1) % 4;
    } else selected = action - IR_MAZE;
    setManualModeTo(true);
    setEffect(modes[selected]);
    if (selected == 0) effectTimer.setInterval(10);
    gameDemo = false;
    gamePaused = true;
    set_CurrentSpecialMode(-1);
  }
  return "applied";
}

void tickIRRemote() {
  if (!irCommands) return;
  IRCommand command;
  if (xQueueReceive(irCommands, &command, 0) == pdTRUE && ws.hasClient(command.client))
    irHandleCommand(command.text, command.client);
  uint32_t now = millis();
  if (irLearning >= 0 && (uint32_t(now - irLearningStarted) >= 15000 || !ws.hasClient(irLearningOwner))) {
    irLearning = -1;
    irNotice = "Learning timed out or the browser disconnected.";
    irSendState();
  }
  if (irWaitForRelease && uint32_t(now - irQuietAt) >= 350) irWaitForRelease = false;
  decode_results result = {};
  if (!irReceiver.decode(&result)) return;

  IRCode code = {(int16_t)result.decode_type, result.bits, result.value};
  bool known = result.decode_type != UNKNOWN && !result.overflow && result.bits <= 64 &&
               (result.repeat || result.bits > 0);
  if (result.decode_type == RC5 || result.decode_type == RC5X)
    code.value = (uint64_t(result.address) << 32) | result.command;
  if (result.decode_type == RC6 && result.bits >= 4 && result.bits <= 64)
    code.value &= ~(uint64_t(1) << (result.bits - 4));
  bool held = false;
  bool resolved = known && irPress.resolve(code, result.repeat, now, held);
  int matched = resolved ? irBindings.find(code) : -1;
  String outcome = known ? "unmapped" : "unrecognized protocol or capture overflow";

  if (irLearning >= 0) {
    irQuietAt = now;
    irWaitForRelease = true;
    if (resolved && !result.repeat && !held && code.bits > 0 && code.bits <= 64) {
      IRBindings updated = irBindings;
      if (matched >= 0) {
        irNotice = irBindings.entries[matched].action == irLearning ? "This code is already assigned here." : "This code belongs to another action; remove it there first.";
      } else if (!updated.add(code, irLearning)) irNotice = "Binding storage is full (32 codes). Remove a code first.";
      else irNotice = irPersistBindings(updated) ? "Button learned and saved." : "Could not save the new binding.";
      irLearning = -1;
      outcome = "learning finished";
      irSendState();
    } else outcome = "learning: waiting for a fresh recognized press";
  } else if (irWaitForRelease) {
    irQuietAt = now;
    outcome = "ignored: release the learned button";
  } else if (matched >= 0) outcome = irApplyAction(irBindings.entries[matched].action, held, now);

  ++irSequence;
  if (irWatching && uint32_t(now - irWatchingAt) < 12000 && ws.hasClient(irWatchingOwner) &&
      irLog.allow(now, ws.availableForWrite(irWatchingOwner), outcome == "learning finished")) {
    DynamicJsonDocument frame(2048);
    frame["kind"] = "frame";
    frame["sequence"] = irSequence;
    frame["skipped"] = irLog.skipped;
    frame["uptime"] = now;
    frame["protocol"] = typeToString(result.decode_type);
    frame["bits"] = result.bits;
    char raw[17];
    snprintf(raw, sizeof(raw), "%016llX", (unsigned long long)result.value);
    frame["code"] = raw;
    frame["key"] = resolved ? irCodeId(code.protocol, code.bits, code.value) : "";
    frame["repeat"] = result.repeat;
    frame["held"] = held;
    frame["overflow"] = result.overflow;
    frame["rawLength"] = result.rawlen;
    frame["action"] = matched >= 0 ? irActions[irBindings.entries[matched].action] : "";
    frame["outcome"] = outcome;
    JsonArray pulses = frame.createNestedArray("pulses");
    for (uint16_t i = 1; i < result.rawlen && i <= 32; ++i) pulses.add(uint32_t(result.rawbuf[i]) * kRawTick);
    irSendMessage(frame, irWatchingOwner);
  }
  irReceiver.resume();
}

#endif
