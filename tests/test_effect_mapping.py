"""Exercise mapped blur, blending, and coordinate traversal with sparse LEDs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'

COMMON = r'''
#include <cassert>
#include <cstdint>
#include <algorithm>
#include <cstring>
struct CHSV { CHSV(int,int,int) {} };
struct CRGB {
  int r=0,green=0,blue=0;
  CRGB()=default;
  CRGB(int a,int b,int c):r(a),green(b),blue(c){}
  CRGB(CHSV):CRGB(40,50,60){}
  static const CRGB Black;
  void nscale8(int n) { r=r*n/256; green=green*n/256; blue=blue*n/256; }
  CRGB& operator+=(CRGB c) { r=std::min(255,r+c.r); green=std::min(255,green+c.green); blue=std::min(255,blue+c.blue); return *this; }
  void operator|=(CRGB c) { r|=c.r; green|=c.green; blue|=c.blue; }
  int getAverageLight() { return (r+green+blue)/3; }
};
const CRGB CRGB::Black={0,0,0};
struct Buffer {
  CRGB data[200];
  CRGB& operator[](int n) { assert(n>=0 && n<200); return data[n]; }
} leds;
int pWIDTH=8,pHEIGHT=8,NUM_LEDS=200,idx=-1;
int imap[2048],visits[2048];
int getPixelNumber(int x,int y) {
  if(x<0 || y<0 || x>=pWIDTH || y>=pHEIGHT) return -1;
  ++visits[y*pWIDTH+x]; return imap[y*pWIDTH+x];
}
void nblend(CRGB& target,CRGB color,int amount) {
  target.nscale8(255-amount); color.nscale8(amount); target+=color;
}
void reset(int w,int h) {
  pWIDTH=w; pHEIGHT=h;
  for(int& n:imap) n=-1;
  for(int& n:visits) n=0;
  for(auto& c:leds.data) c=CRGB();
}
'''


class EffectMappingTests(unittest.TestCase):
    def run_cpp(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            cpp = Path(tmp) / 'effects.cpp'
            binary = Path(tmp) / 'effects'
            cpp.write_text(source)
            compiled = subprocess.run(['g++', '-std=gnu++17', '-Wall', '-Wextra',
                                       str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(binary)], check=True)

    def test_blur_and_blending_absorb_holes_and_preserve_unmapped_slots(self):
        effects = (FIRMWARE / 'effects.ino').read_text()
        source = COMMON + function(effects, 'void blendPixelXY(')
        source += function(effects, 'void blurMappedFrame(')
        source += r'''
int main() {
  reset(8,8);
  // Use late physical addresses and an internal hole in an otherwise full map.
  for(int i=0;i<64;++i) imap[i]=100+i;
  imap[27]=-1; imap[28]=199;
  leds[0]=CRGB(77,77,77);
  for(int i=0;i<64;++i) if(imap[i]>=0) leds[imap[i]]=CRGB((i*13)%256,0,0);
  int grid[64],next[64];
  for(int i=0;i<64;++i) grid[i]=imap[i]<0 ? 0 : leds[imap[i]].r;
  // Independent convolution reference, with holes absorbing light.
  for(int axis=0;axis<2;++axis) {
    for(int y=0;y<8;++y) for(int x=0;x<8;++x) {
      int i=y*8+x;
      if(imap[i]<0) { next[i]=0; continue; }
      int a=axis==0 ? (x ? i-1 : -1) : (y ? i-8 : -1);
      int b=axis==0 ? (x<7 ? i+1 : -1) : (y<7 ? i+8 : -1);
      next[i]=grid[i]*127/256 + (a<0 ? 0 : grid[a]*64/256) + (b<0 ? 0 : grid[b]*64/256);
    }
    std::copy(next,next+64,grid);
  }
  blurMappedFrame(128);
  for(int i=0;i<64;++i) if(imap[i]>=0) assert(leds[imap[i]].r==grid[i]);
  assert(leds[0].r==77);
  blendPixelXY(3,3,CRGB(255,0,0),128); // hole
  blendPixelXY(-1,0,CRGB(255,0,0),128); // outside
  blendPixelXY(4,3,CRGB(255,0,0),255); // slot 200
  assert(leds[199].r>=254 && leds[0].r==77);
  reset(8,8); blurMappedFrame(255); // entirely empty map is also safe
}
'''
        self.run_cpp(source)

    def test_pacifica_and_shadows_visit_entire_large_shape_and_clear_old_game(self):
        effects = (FIRMWARE / 'effects.ino').read_text()
        source = COMMON + r'''
using CRGBPalette16=int;
constexpr int LINEARBLEND=0,MC_SHADOWS=1;
bool loadingFlag=true;
int clears=0,deviceBrightness=3,thisMode=1;
struct { void clear() { ++clears; for(auto& c:leds.data) c=CRGB(); } } FastLED;
int beatsin8(int,int a,int) { return a; }
int beatsin88(int,int a,int) { return a; }
int beat8(int) { return 0; }
int sin8(int) { return 0; }
int sin16(int) { return 0; }
int scale8(int x,int y) { return x*y/256; }
int scale16(int x,int y) { return x*y/65536; }
int qadd8(int x,int y) { return std::min(255,x+y); }
CRGB ColorFromPalette(int,int,int,int) { return CRGB(40,50,60); }
uint32_t millis() { return 1000; }
int getEffectContrastValue(int) { return 255; }
int getBrightnessCalculated(int,int) { return 3; }
int map(int,int,int,int a,int) { return a; }
int map8(int,int a,int) { return a; }
'''
        for name in ('void pacifica_one_layer(', 'void pacifica_add_whitecaps(',
                     'void pacifica_deepen_colors(', 'void shadowsRoutine('):
            source += function(effects, name)
        source += r'''
void checkVisits() {
  for(int i=0;i<pWIDTH*pHEIGHT;++i) assert(visits[i]==1);
  std::fill(visits,visits+2048,0);
}
int main() {
  reset(32,16); imap[511]=199; imap[300]=5; imap[0]=10;
  int palette=0;
  pacifica_one_layer(palette,0,100,50,0); checkVisits();
  assert(leds[199].r==40 && leds[5].r==40);
  pacifica_add_whitecaps(); checkVisits();
  pacifica_deepen_colors(); checkVisits();
  for(auto& c:leds.data) c=CRGB(255,255,255); // old game frame
  shadowsRoutine(); checkVisits();
  assert(clears==1 && !loadingFlag);
  assert(leds[199].r>0 && leds[199].r<100 && leds[0].r==0);
  shadowsRoutine(); checkVisits(); assert(clears==1);
}
'''
        self.run_cpp(source)
