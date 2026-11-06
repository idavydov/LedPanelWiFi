#pragma once
#include <stdint.h>

// Coordinates use a lower-left origin. A/B each retain factory slots 1..200.
struct PanelMapDraft {
  static const int slotsPerString = 200;
  static const int strings = 2;
  static const int slots = slotsPerString * strings;
  int16_t x[slots], y[slots];
  uint8_t width = 20, height = 10;
  PanelMapDraft() { clear(); }
  void clear() { for (int i = 0; i < slots; ++i) x[i] = y[i] = -1; }
  bool dimensions(int w, int h) {
    if (w < 8 || h < 8 || w > 64 || h > 64 || w * h > 2048) return false;
    width = w; height = h; clear(); return true;
  }
  bool assign(int id, int px, int py, int string = 0) {
    if (string < 0 || string >= strings || id < 1 || id > slotsPerString || px < 0 || py < 0 || px >= width || py >= height) return false;
    int index = string * slotsPerString + id - 1;
    if (x[index] >= 0) return false;
    for (int i = 0; i < slots; ++i) if (x[i] == px && y[i] == py) return false;
    x[index] = px; y[index] = py; return true;
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
      if (!checked.assign(i % slotsPerString + 1, x[i], y[i], i / slotsPerString)) return false;
    }
    return checked.count() > 0;
  }
};

struct PanelMapRecord {
  uint32_t version = 0x4D415002;
  PanelMapDraft map;
  bool valid() const { return version == 0x4D415002 && map.valid(); }
};

// Preserve the exact version-1 NVS layout for automatic migration to string A.
struct PanelLegacyMapRecord {
  uint32_t version = 0x4D415001;
  int16_t x[200], y[200];
  uint8_t width, height;
  bool upgrade(PanelMapRecord& record) const {
    if (version != 0x4D415001 || !record.map.dimensions(width, height)) return false;
    for (int i = 0; i < 200; ++i) {
      if (x[i] == -1 && y[i] == -1) continue;
      if (!record.map.assign(i + 1, x[i], y[i])) return false;
    }
    return record.valid();
  }
};

inline uint16_t panelBufferSize(int width, int height) {
  return width * height < PanelMapDraft::slots ? PanelMapDraft::slots : width * height;
}

struct PanelSlotMask {
  bool visible[PanelMapDraft::slots] = {};
  void include(int index) { if (index >= 0 && index < PanelMapDraft::slots) visible[index] = true; }
  template<typename Pixel> void apply(Pixel* pixels, const Pixel& black) const {
    for (int i = 0; i < PanelMapDraft::slots; ++i) if (!visible[i]) pixels[i] = black;
  }
};
