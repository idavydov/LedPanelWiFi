"""Flicker must replace game pixels through the factory-slot coordinate map."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]


class FlickerTests(unittest.TestCase):
    def test_sparse_map_replaces_paddle_and_preserves_noise_coordinates(self):
        effects = (ROOT / 'firmware/LedPanelWiFi_v1.14/effects.ino').read_text()
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
int pWIDTH=8, pHEIGHT=8, NUM_LEDS=400, MC_FLICKER=1;
bool loadingFlag=true;
struct CHSV { int h,s,v; CHSV(int a,int b,int c):h(a),s(b),v(c){} };
struct CRGB { int h=0,s=0,v=0; CRGB()=default; CRGB(CHSV c):h(c.h),s(c.s),v(c.v){} };
CRGB leds[400];
int imap[64];
struct { void clear() { for(auto& p:leds) p=CRGB(); } } FastLED;
void drawPixelXY(int x,int y,CRGB c) {
  int slot=imap[y*8+x]; if(slot>=0) leds[slot]=c;
}
int q44(int,int) { return 0; }
void fill_raw_2dnoise16into8(uint8_t* out,int w,int h,int,int,int,int,
                            uint32_t,int,uint32_t,int,uint32_t) {
  for(int i=0;i<w*h;++i) out[i]=i+1;
}
void fill_raw_2dnoise8(uint8_t* out,int w,int h,int,uint16_t,int,uint16_t,int,uint16_t) {
  for(int i=0;i<w*h;++i) out[i]=100+i;
}
void setRandomMode() { assert(false); }
uint16_t random16() { return 42; }
int getEffectSpeedValue(int) { return 100; }
int map8(int,int,int) { return 3; }
'''
        source += effects[effects.index('uint32_t xf,yf,v_time,hue_time,hxy;'):
                          effects.index('void drawFlickerFrame()')]
        source += function(effects, 'void drawFlickerFrame(')
        source += function(effects, 'void flickerRoutine(')
        source += r'''
int main() {
  // None of these coordinates live in the first 64 physical slots.
  for(int i=0;i<64;++i) imap[i]=100+i;
  imap[0]=399; imap[17]=-1;
  // Simulate a paddle left by Arkanoid, plus an unmapped pixel.
  for(auto& p:leds) p.v=255;
  flickerRoutine();
  assert(!loadingFlag && leds[399].v==1 && leds[399].h==163);
  for(int i=1;i<64;++i) if(imap[i]>=0) {
    assert(leds[imap[i]].v==i+1 && leds[imap[i]].h==163-i);
  }
  assert(leds[0].v==0 && leds[100].v==0 && leds[117].v==0);
  // Every frame overwrites all mapped pixels, even after initialization.
  leds[399].v=255;
  flickerRoutine(); assert(leds[399].v==1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp = Path(tmp) / 'flicker.cpp'
            binary = Path(tmp) / 'flicker'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=gnu++17', '-Wall', '-Wextra', str(cpp),
                            '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)
