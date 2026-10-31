"""IR mapping, persistence, repeat handling, and game dispatch regressions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_network_security import function


FIRMWARE = Path(__file__).resolve().parents[1] / 'firmware/LedPanelWiFi_v1.14'


class IRRemoteTests(unittest.TestCase):
    def test_bindings_repeats_and_game_actions(self):
        firmware = (FIRMWARE / 'ir_remote.ino').read_text()
        source = r'''
#include <cassert>
#include <string>
#include "ir_remote_model.h"
using String = std::string;
IRBindings irBindings;
bool storageWorks = true;
struct Preferences {
  bool begin(const char*, bool) { return storageWorks; }
  size_t putBytes(const char*, const void*, size_t size) { return storageWorks ? size : 0; }
  void end() {}
};
constexpr uint8_t MC_MAZE=27, MC_SNAKE=28, MC_TETRIS=29, MC_ARKANOID=30;
uint8_t thisMode=MC_SNAKE, buttons=4;
bool isTurnedOff=false, isNightClock=false, gameDemo=false, gamePaused=true;
bool manual=false;
int special=0;
uint32_t irLastDispatch=0;
uint8_t getGameButtonSpeed() { return 10; }
void setManualModeTo(bool value) { manual=value; }
void setEffect(uint8_t value) { thisMode=value; }
void set_CurrentSpecialMode(int8_t value) { special=value; }
struct { int interval=0; void setInterval(int value) { interval=value; } } effectTimer;
'''
        for signature in ('bool irPersistBindings(', 'bool irGameSelected(', 'String irApplyAction('):
            source += function(firmware, signature) + '\n'
        source += r'''
int main() {
  IRLogLimiter log;
  assert(!log.allow(0,false));
  assert(log.skipped == 1 && !log.sent);
  assert(log.allow(1000,true));
  assert(!log.allow(1099,true));
  assert(log.allow(1100,true));
  assert(log.allow(1101,true,true)); // Learning feedback bypasses only the rate limit.
  assert(!log.allow(1102,false,true)); // Never enqueue against a full socket queue.
  log.sentAt=UINT32_MAX-40;
  assert(!log.allow(20,true));
  assert(log.allow(100,true));

  IRCode one={3,32,0xFFFF000012345678ULL}, two={3,32,0x12345678ULL};
  IRCode otherProtocol={4,32,0x12345678ULL}, otherBits={3,16,0x5678};
  IRBindings mapping;
  assert(mapping.valid());
  assert(mapping.add(one,IR_UP) && mapping.add(two,IR_UP));
  assert(mapping.add(otherProtocol,IR_LEFT) && mapping.add(otherBits,IR_RIGHT));
  assert(mapping.count == 4 && mapping.valid());
  assert(!mapping.add(one,IR_LEFT)); // A single code cannot conflict across actions.
  assert(!mapping.add({3,0,0},IR_UP) && !mapping.add({-1,32,1},IR_UP));
  assert(mapping.find(one) == 0 && mapping.find(two) == 1);
  assert(mapping.find(otherProtocol) == 2 && mapping.find(otherBits) == 3);
  assert(irPersistBindings(mapping) && irBindings.count == 4);
  IRBindings changed=mapping;
  assert(changed.remove(0) && changed.find(one) == -1 && changed.find(two) == 0);
  storageWorks=false;
  assert(!irPersistBindings(changed) && irBindings.find(one) == 0);
  storageWorks=true;
  assert(irPersistBindings(changed) && irBindings.find(one) == -1);
  assert(!changed.remove(99));
  IRBindings full;
  for (uint8_t i=0; i<IRBindings::capacity; ++i) assert(full.add({3,32,i},IR_UP));
  assert(!full.add({3,32,99},IR_UP));
  full.count=33;
  assert(!full.valid());
  changed.version=99;
  assert(!changed.valid());

  IRPressTracker press;
  IRCode code={3,0,UINT64_MAX};
  bool held;
  assert(!press.resolve(code,true,100,held)); // Orphan repeat.
  code=one;
  assert(press.resolve(code,false,100,held) && !held);
  code={3,0,UINT64_MAX};
  assert(press.resolve(code,true,210,held) && held && code == one);
  code={4,0,UINT64_MAX};
  assert(!press.resolve(code,true,240,held)); // Another protocol cannot inherit a key.
  code=two;
  assert(press.resolve(code,false,260,held) && !held);
  code=two;
  assert(press.resolve(code,false,300,held) && held); // Repeated full Sony-style frames.
  code={3,0,UINT64_MAX};
  assert(!press.resolve(code,true,700,held)); // Stale repeats never stick a button.
  press.receivedAt=UINT32_MAX-40;
  code=two;
  assert(press.resolve(code,false,20,held) && held); // Uptime wraparound.

  assert(irApplyAction(IR_PLAY,false,1000) == "applied" && !gamePaused);
  irApplyAction(IR_PLAY,true,1100);
  assert(!gamePaused); // Holding Start must not toggle repeatedly.
  irApplyAction(IR_LEFT,false,1200);
  assert(buttons == 3);
  buttons=4;
  irApplyAction(IR_LEFT,true,1250);
  assert(buttons == 4);
  irApplyAction(IR_LEFT,true,1320);
  assert(buttons == 3);
  isTurnedOff=true; buttons=4;
  irApplyAction(IR_UP,false,1500);
  assert(buttons == 4);
  isTurnedOff=false;
  gameDemo=true;
  irApplyAction(IR_UP,false,1600);
  assert(buttons == 4);
  irApplyAction(IR_MAZE,false,1700);
  assert(thisMode == MC_MAZE && !gameDemo && gamePaused && manual && special == -1);
  assert(effectTimer.interval == 10);
  irApplyAction(IR_NEXT,false,1800);
  assert(thisMode == MC_SNAKE);
  irApplyAction(IR_ARKANOID,false,1900);
  irApplyAction(IR_NEXT,false,2000);
  assert(thisMode == MC_MAZE);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(FIRMWARE), str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
