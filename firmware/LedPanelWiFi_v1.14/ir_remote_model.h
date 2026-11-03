#pragma once
#include <stdint.h>

enum IRGameAction : uint8_t {
  IR_UP, IR_RIGHT, IR_DOWN, IR_LEFT, IR_PLAY, IR_NEXT,
  IR_MAZE, IR_SNAKE, IR_TETRIS, IR_ARKANOID,
  IR_EFFECT_PREV, IR_EFFECT_NEXT, IR_POWER, IR_ACTION_COUNT
};

struct IRCode {
  int16_t protocol;
  uint16_t bits;
  uint64_t value;
  bool operator==(const IRCode& other) const {
    return protocol == other.protocol && bits == other.bits && value == other.value;
  }
};

struct IRBinding {
  IRCode code;
  uint8_t action;
};

// Fixed-size, versioned NVS record. Multiple codes may map to the same action.
struct IRBindings {
  enum : uint8_t { capacity = 32 };
  uint32_t version = 1;
  uint8_t count = 0;
  IRBinding entries[capacity] = {};

  bool valid() const {
    if (version != 1 || count > capacity) return false;
    for (uint8_t i = 0; i < count; ++i) {
      if (entries[i].code.protocol <= 0 || entries[i].code.bits == 0 ||
          entries[i].code.bits > 64 || entries[i].action >= IR_ACTION_COUNT) return false;
      for (uint8_t j = 0; j < i; ++j)
        if (entries[i].code == entries[j].code) return false;
    }
    return true;
  }

  int find(const IRCode& code) const {
    for (uint8_t i = 0; i < count; ++i)
      if (entries[i].code == code) return i;
    return -1;
  }

  bool add(const IRCode& code, uint8_t action) {
    if (count == capacity || action >= IR_ACTION_COUNT || code.protocol <= 0 ||
        code.bits == 0 || code.bits > 64 || find(code) >= 0) return false;
    entries[count++] = {code, action};
    return true;
  }

  bool remove(uint8_t index) {
    if (index >= count) return false;
    for (uint8_t i = index + 1; i < count; ++i) entries[i - 1] = entries[i];
    entries[--count] = {};
    return true;
  }
};

// Short repeat frames inherit the last full code only while that press is fresh.
struct IRPressTracker {
  IRCode last = {};
  bool hasLast = false;
  bool repeatAllowed = false;
  uint32_t receivedAt = 0;
  void invalidateRepeats() { repeatAllowed = false; }
  bool resolve(IRCode& code, bool repeat, uint32_t now, bool& held) {
    held = hasLast && uint32_t(now - receivedAt) < 300;
    if (repeat) {
      if (!held || !repeatAllowed || code.protocol != last.protocol) { invalidateRepeats(); return false; }
      code = last;
    } else {
      held = held && code == last;
    }
    last = code;
    receivedAt = now;
    hasLast = true;
    repeatAllowed = true;
    return true;
  }
};

// A single plausible but damaged capture must not become a saved assignment.
struct IRLearnConfirmation {
  enum Result { First, Changed, Confirmed };
  IRCode candidate = {};
  bool seen = false;
  void reset() { seen = false; }
  Result observe(const IRCode& code) {
    if (seen && code == candidate) return Confirmed;
    const Result result = seen ? Changed : First;
    candidate = code;
    seen = true;
    return result;
  }
};

// Debug traffic is optional. Never let it outpace a slow browser connection.
struct IRLogLimiter {
  uint32_t sentAt = 0;
  uint32_t skipped = 0;
  bool sent = false;
  bool allow(uint32_t now, bool writable, bool important = false) {
    if (!writable || (!important && sent && uint32_t(now - sentAt) < 100)) {
      ++skipped;
      return false;
    }
    sent = true;
    sentAt = now;
    return true;
  }
};
