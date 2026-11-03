"""Run the actual learning branch against fresh, held, and inconsistent captures."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


class IRLearningTests(unittest.TestCase):
    def test_only_two_matching_separate_presses_persist_a_new_binding(self):
        firmware = (FIRMWARE / 'ir_remote.ino').read_text()
        start = firmware.index('  if (irLearning >= 0) {\n    bool released')
        end = firmware.index('\n  ++irSequence;', start)
        source = r'''
#include <cassert>
#include <string>
#include "ir_remote_model.h"
using String=std::string;
IRBindings irBindings;
IRPressTracker irPress;
IRLearnConfirmation irLearnConfirmation;
int irLearning=IR_UP, writes=0;
uint32_t irQuietAt=0;
bool irWaitForRelease=false;
String irNotice;
const char* irActions[]={"up","right","down","left"};
String irCodeId(int16_t, uint16_t, uint64_t value) { return std::to_string(value); }
void irSendState() {}
bool irPersistBindings(const IRBindings& updated) { ++writes; irBindings=updated; return true; }
String irApplyAction(uint8_t, bool, uint32_t) { return "applied"; }
String deliver(IRCode code, bool repeat, uint32_t now, bool known=true) {
  if(irWaitForRelease && uint32_t(now-irQuietAt)>=350) irWaitForRelease=false;
  if(!known) irPress.invalidateRepeats();
  bool held=false;
  bool resolved=known && irPress.resolve(code,repeat,now,held);
  int matched=resolved ? irBindings.find(code) : -1;
  struct { bool repeat; } result={repeat};
  String outcome;
'''+firmware[start:end]+r'''
  return outcome;
}
void learn(int action=IR_UP) {
  irLearning=action; irLearnConfirmation.reset(); irPress=IRPressTracker();
  irWaitForRelease=false;
}
int main() {
  IRCode a={3,32,0x1234}, b={3,32,0x5678}, shortRepeat={3,0,0};
  deliver(a,false,1000);
  assert(writes==0 && irLearning==IR_UP);
  deliver(a,false,1100); // full-code repeat from a held Sony-style remote
  deliver(shortRepeat,true,1150); // short NEC repeat
  deliver(a,false,1250); // no release gap yet
  assert(writes==0);
  deliver(a,false,1600);
  assert(writes==1 && irLearning==-1 && irBindings.find(a)==0);

  learn(IR_LEFT);
  deliver(b,false,2000);
  IRCode c=b; ++c.value;
  deliver(c,false,2500); // inconsistent capture cannot save an assignment
  assert(writes==1 && irLearning==IR_LEFT && irNotice.find("nothing saved")!=String::npos);
  deliver(c,false,3000);
  assert(writes==2 && irBindings.find(c)==1);

  learn(IR_RIGHT);
  deliver(a,false,4000); // existing assignment cannot be overwritten
  assert(writes==2 && irLearning==-1 && irBindings.entries[0].action==IR_UP);
  assert(irNotice.find("another action")!=String::npos);

  learn(IR_DOWN);
  deliver(b,false,5000);
  deliver(b,false,5500,false); // a bad capture does not confirm the candidate
  assert(writes==2 && irLearning==IR_DOWN);
  deliver(b,false,6000);
  assert(writes==3 && irBindings.find(b)==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'learning.cpp'
            binary = Path(directory) / 'learning'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(FIRMWARE), str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
