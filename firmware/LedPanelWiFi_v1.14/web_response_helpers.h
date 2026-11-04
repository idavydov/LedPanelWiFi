#pragma once
#include <stddef.h>
#include <stdint.h>

// End before a complete UTF-8 character, never inside its continuation bytes.
inline size_t webUtf8Prefix(const char* text, size_t length, size_t limit) {
  if (length <= limit) return length;
  size_t end = limit;
  while (end && (uint8_t(text[end]) & 0xC0) == 0x80) --end;
  return end;
}
