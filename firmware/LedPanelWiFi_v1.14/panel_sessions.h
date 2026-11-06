#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

// Fixed-size RAM sessions: reboot invalidates every token, never the password.
class PanelSessions {
 public:
  static constexpr uint32_t lifetime = 12UL * 60 * 60 * 1000;
  bool valid(const char* cookie, uint32_t now) const {
    char token[65];
    if (!readCookie(cookie, token)) return false;
    for (const auto& session : sessions)
      if (session.token[0] && uint32_t(now - session.created) < lifetime && equal(session.token, token)) return true;
    return false;
  }
  void issue(const char* token, uint32_t now) {
    if (!token || strlen(token) != 64) return;
    unsigned target = 0;
    for (unsigned i = 0; i < 4; ++i) {
      if (!sessions[i].token[0] || uint32_t(now - sessions[i].created) >= lifetime) { target = i; break; }
      if (uint32_t(now - sessions[i].created) > uint32_t(now - sessions[target].created)) target = i;
    }
    memcpy(sessions[target].token, token, 65); sessions[target].created = now;
  }
  void revoke(const char* cookie) {
    char token[65];
    if (!readCookie(cookie, token)) return;
    for (auto& session : sessions) if (equal(session.token, token)) session.token[0] = 0;
  }
 private:
  struct Session { char token[65] = {}; uint32_t created = 0; } sessions[4];
  static bool equal(const char* a, const char* b) {
    unsigned difference = 0;
    for (unsigned i = 0; i < 64; ++i) difference |= uint8_t(a[i]) ^ uint8_t(b[i]);
    return difference == 0;
  }
  static bool readCookie(const char* cookie, char* token) {
    if (!cookie) return false;
    bool found = false;
    while (*cookie) {
      while (*cookie == ' ' || *cookie == ';') ++cookie;
      const char* end = strchr(cookie, ';');
      if (!end) end = cookie + strlen(cookie);
      size_t size = end - cookie;
      if (size >= 10 && !strncmp(cookie, "panel_sid=", 10)) {
        if (found || size != 74) return false;
        memcpy(token, cookie + 10, 64); token[64] = 0; found = true;
      }
      cookie = end;
    }
    return found;
  }
};
