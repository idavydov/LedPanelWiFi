#pragma once
#include <stdint.h>

// Coordinates use a lower-left origin; factory slots are 1..200.
struct PanelMapDraft {
  static const int slots = 200;
  int16_t x[slots], y[slots];
  uint8_t width = 20, height = 10;
  PanelMapDraft() { clear(); }
  void clear() { for (int i = 0; i < slots; ++i) x[i] = y[i] = -1; }
  bool dimensions(int w, int h) {
    if (w < 8 || h < 8 || w > 64 || h > 64 || w * h > 2048) return false;
    width = w; height = h; clear(); return true;
  }
  bool assign(int id, int px, int py) {
    if (id < 1 || id > slots || px < 0 || py < 0 || px >= width || py >= height) return false;
    if (x[id - 1] >= 0) return false;
    for (int i = 0; i < slots; ++i) if (x[i] == px && y[i] == py) return false;
    x[id - 1] = px; y[id - 1] = py; return true;
  }
  int16_t at(int px, int py) const {
    for (int i = 0; i < slots; ++i) if (x[i] == px && y[i] == py) return i;
    return -1;
  }
  int count() const {
    int n = 0; for (int i = 0; i < slots; ++i) if (x[i] >= 0) ++n; return n;
  }
  bool valid() const {
    PanelMapDraft checked;
    if (!checked.dimensions(width, height)) return false;
    for (int i = 0; i < slots; ++i) {
      if (x[i] == -1 && y[i] == -1) continue;
      if (!checked.assign(i + 1, x[i], y[i])) return false;
    }
    return checked.count() > 0;
  }
};

struct PanelMapRecord {
  uint32_t version = 0x4D415001;
  PanelMapDraft map;
  bool valid() const { return version == 0x4D415001 && map.valid(); }
};

inline uint16_t panelBufferSize(int width, int height) {
  return width * height < 200 ? 200 : width * height;
}
