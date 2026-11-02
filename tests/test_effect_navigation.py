"""Exercise actual effect selection with a two-item playlist."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]


class EffectNavigationTests(unittest.TestCase):
    def test_s2_minimum_brightness_keeps_selected_effect(self):
        main = (ROOT / 'firmware/LedPanelWiFi_v1.14/a_main.ino').read_text()
        start = main.index('      uint8_t br = specialMode ? specialBrightness : deviceBrightness;')
        end = main.index('\n    }\n  } else', start)
        dispatch = main[start:end]
        source = r'''
#include <cassert>
#include <cstdint>
bool specialMode=false, loadingFlag=false, isAlarming=false;
bool allowHorizontal=true, allowVertical=false;
uint8_t specialBrightness=1, deviceBrightness=1, thisMode=20;
enum {MC_CLOCK=0,MC_TEXT=50,MC_DRAW=51,MC_LOADIMAGE=52};
int rendered=-1;
long long now=2000, prevShowTimer=0;
long long millis() { return now; }
long long abs(long long n) { return n < 0 ? -n : n; }
struct {void clear() {}} FastLED;
void FastLEDshow() {}
void customRoutine(int mode) { rendered=mode; }
void dispatch() {
'''+dispatch+r'''
}
int main() {
  dispatch();
#if defined(PANEL_PROFILE_S2_MINI)
  assert(rendered==20); // raw brightness 1 must not silently become clock mode
#else
  assert(rendered==MC_CLOCK); // preserve legacy behavior for other profiles
#endif
  deviceBrightness=3; dispatch(); assert(rendered==20);
  thisMode=MC_CLOCK; dispatch(); assert(rendered==MC_CLOCK); // explicit clock still works
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'dim.cpp'
            binary = Path(directory) / 'dim'
            cpp.write_text(source)
            for flags in ([], ['-DPANEL_PROFILE_S2_MINI=1']):
                subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                *flags, str(cpp), '-o', str(binary)], check=True)
                subprocess.run([str(binary)], check=True)

    def test_s2_frame_cap_returns_without_blocking_and_handles_timer_wrap(self):
        custom = (ROOT / 'firmware/LedPanelWiFi_v1.14/custom.ino').read_text()
        source = r'''
#include <cassert>
#include <cstdint>
#define PANEL_PROFILE_S2_MINI 1
#define USE_E131 0
uint32_t now=0, prevShowTimer=0;
uint32_t millis() { return now; }
bool outsideSlotLit=true;
struct { int frames=0; void show() { assert(!outsideSlotLit); ++frames; } } FastLED;
void applyPanelVisibility() { outsideSlotLit=false; }
'''
        source += function(custom, 'void FastLEDshow(')
        source += r'''
int main() {
  for(now=0;now<25;++now) FastLEDshow();
  assert(FastLED.frames==0);
  FastLEDshow(); assert(FastLED.frames==1 && prevShowTimer==25);
  now=49; FastLEDshow(); assert(FastLED.frames==1);
  outsideSlotLit=true; // another raw-buffer effect fills an unmapped slot
  now=50; FastLEDshow(); assert(FastLED.frames==2 && !outsideSlotLit);
  prevShowTimer=UINT32_MAX-10; now=10;
  FastLEDshow(); assert(FastLED.frames==2);
  now=20; FastLEDshow(); assert(FastLED.frames==3);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'frames.cpp'
            binary = Path(directory) / 'frames'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_two_random_effects_alternate_instead_of_repeating_first(self):
        main = (ROOT / 'firmware/LedPanelWiFi_v1.14/a_main.ino').read_text()
        source = r'''
#include <cassert>
#include <string>
#include <cstdint>
#define USE_SD 0
struct String : std::string {
  using std::string::string;
  int indexOf(char c) const { auto index=find(c); return index==npos ? -1 : int(index); }
};
const char* IDX_LINE="0123456789";
int MAX_EFFECT=10, selected=-1;
uint8_t effect_order_idx=0;
String effect_order="01";
uint8_t random8(int) { return 0; }
void setEffect(int mode) { selected=mode; }
'''
        source += function(main, 'void setRandomMode(')
        source += r'''
int main() {
  setRandomMode(); assert(selected==1 && effect_order_idx==1);
  setRandomMode(); assert(selected==0 && effect_order_idx==0);
  effect_order="39";
  setRandomMode(); assert(selected==9);
  setRandomMode(); assert(selected==3);
  effect_order="7"; setRandomMode(); assert(selected==7);
  effect_order=""; setRandomMode(); assert(selected==0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'navigation.cpp'
            binary = Path(directory) / 'navigation'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
