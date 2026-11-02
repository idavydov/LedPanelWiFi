"""Test real mapping commands with ArduinoJson, fake sockets and fake NVS."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_network_security import function


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


class PanelMappingTests(unittest.TestCase):
    def test_validation_chunk_ownership_persistence_failure_and_preview(self):
        firmware = (FIRMWARE / 'panel_mapping.ino').read_text()
        source = r'''
#include <cassert>
#include <cstring>
#include <cstdio>
#include <new>
#include <string>
#include "ArduinoJson.h"
#include "panel_mapping_model.h"
using String = std::string;
PanelMapDraft mappingDraft;
uint32_t mappingOwner=0, mappingDraftAt=0, mappingPreviewOwner=0, mappingPreviewAt=0;
int mappingSlot=0;
bool mappingUploading=false, needRestart=false, loadingFlag=false, isTurnedOff=false;
uint32_t needRestartTime=0, now=100;
uint32_t millis() { return now; }
struct { bool connected=true; bool hasClient(uint32_t) { return connected; } } ws;
bool storageWorks=true;
PanelMapRecord stored;
int sMATRIX_TYPE=2, pWIDTH=8, pHEIGHT=8, mapListLen=0;
int16_t* imap=nullptr;
String mapFiles[5];
PanelSlotMask panelSlotMask;
bool panelMaskReady=false;
int getPixelNumber(int x, int y) { return imap ? imap[x+(pHEIGHT-y-1)*pWIDTH] : -1; }
struct Preferences {
  bool begin(const char* name, bool) { assert(std::string(name)=="panel-layout"); return storageWorks; }
  size_t putBytes(const char*, const void* value, size_t size) {
    assert(size==sizeof(stored)); if(!storageWorks) return 0;
    std::memcpy(&stored,value,size); return size;
  }
  void end() {}
  size_t getBytesLength(const char*) { return sizeof(stored); }
  size_t getBytes(const char*, void* value, size_t size) { std::memcpy(value,&stored,size); return size; }
};
int savedWidth=0, savedHeight=0, savedType=0, commits=0;
void putMatrixMapWidth(int n) { savedWidth=n; }
void putMatrixMapHeight(int n) { savedHeight=n; }
void putMatrixSegmentType(int n) { savedType=n; }
void saveSettings() { ++commits; }
String lastKind, lastOp, lastError;
void mappingReply(uint32_t, const char* kind, const char* op, const String& error=String()) {
  lastKind=kind; lastOp=op; lastError=error;
}
struct CRGB { int value; CRGB(int v=0):value(v){} static const CRGB White; static const CRGB Black; };
const CRGB CRGB::White={255};
const CRGB CRGB::Black={0};
CRGB ledStorage[2048];
CRGB* leds=ledStorage;
struct {
  int brightness=0, frames=0;
  void clear(bool show=false) { for(auto& pixel:ledStorage) pixel.value=0; if(show) ++frames; }
  void show(int scale) { brightness=scale; ++frames; }
} FastLED;
'''
        source += function(firmware, 'void initializePanelVisibility(')
        source += function(firmware, 'void applyPanelVisibility(')
        source += function(firmware, 'bool loadStoredMapping(')
        source += function(firmware, 'void handleMappingCommand(')
        source += function(firmware, 'bool renderMappingPreview(')
        source += r'''
int main() {
  PanelSlotMask visibility;
  visibility.include(6); visibility.include(199);
  visibility.include(-1); visibility.include(200); // invalid/hole addresses never become visible
  int physical[200]; for (auto& value : physical) value=255;
  visibility.apply(physical, 0);
  for (int i=0;i<200;++i) assert(physical[i]==(i==6 || i==199 ? 255 : 0));
  // Reapply after a raw-buffer effect overwrites every slot.
  for (auto& value : physical) value=123;
  visibility.apply(physical, 0);
  assert(physical[0]==0 && physical[6]==123 && physical[199]==123);
  assert(panelBufferSize(8,8)==200 && panelBufferSize(20,20)==400);
  assert(!mappingDraft.dimensions(7,8) && !mappingDraft.dimensions(64,64));
  handleMappingCommand(R"({"op":"identify","id":200})",1);
  assert(renderMappingPreview() && leds[199].value==255 && leds[0].value==0 && FastLED.brightness==3);
  handleMappingCommand(R"({"op":"stop"})",2); // other browser cannot stop it
  assert(mappingSlot==200);
  now+=10001;
  int previewFrames=FastLED.frames;
  assert(!renderMappingPreview() && mappingSlot==0 && loadingFlag);
  assert(FastLED.frames==previewFrames+1); // immediately transmit black when identification ends
  handleMappingCommand(R"({"op":"identify","id":200})",1);
  isTurnedOff=true;
  assert(!renderMappingPreview() && mappingSlot==0); // power switch also stops identification
  handleMappingCommand(R"({"op":"identify","id":200})",1);
  assert(lastKind=="error" && mappingSlot==0);
  isTurnedOff=false;
  handleMappingCommand(R"({"op":"identify","id":201})",1);
  assert(lastKind=="error" && mappingSlot==0);
  handleMappingCommand(R"({"op":"begin","width":8,"height":8})",1);
  assert(lastKind=="ack");
  handleMappingCommand(R"({"op":"begin","width":10,"height":10})",2);
  assert(lastKind=="error" && mappingOwner==1);
  handleMappingCommand(R"({"op":"chunk","rows":[[200,0,0],[7,1,1]]})",1);
  assert(lastKind=="ack" && mappingDraft.at(0,0)==199 && mappingDraft.at(1,1)==6);
  storageWorks=false;
  handleMappingCommand(R"({"op":"commit"})",1);
  assert(lastKind=="error" && !needRestart && commits==0);
  storageWorks=true;
  handleMappingCommand(R"({"op":"begin","width":8,"height":8})",1);
  handleMappingCommand(R"({"op":"chunk","rows":[[200,0,0],[7,1,1]]})",1);
  handleMappingCommand(R"({"op":"commit"})",1);
  assert(lastKind=="saved" && needRestart && commits==1 && savedWidth==8 && savedHeight==8 && savedType==2);
  assert(stored.valid() && stored.map.at(0,0)==199 && stored.map.at(7,7)==-1);
  assert(loadStoredMapping() && imap[56]==199 && imap[49]==6 && imap[0]==-1);
  assert(mapListLen==1 && mapFiles[0]=="8x8");
  initializePanelVisibility();
  for(auto& pixel:ledStorage) pixel.value=255;
  applyPanelVisibility();
  for(int i=0;i<200;++i) assert(leds[i].value==(i==6 || i==199 ? 255 : 0));
  delete[] imap; imap=nullptr;
  stored.map.x[0]=0; stored.map.y[0]=0;
  assert(!stored.valid()); // reject corrupted duplicate coordinates
  assert(!loadStoredMapping() && imap==nullptr);
  needRestart=false;
  handleMappingCommand(R"({"op":"begin","width":8,"height":8})",1);
  handleMappingCommand(R"({"op":"chunk","rows":[[1,0,0],[2,0,0]]})",1);
  assert(lastKind=="error" && !mappingUploading && !needRestart);
  handleMappingCommand(R"({"op":"begin","width":8,"height":8})",1);
  handleMappingCommand(R"({"op":"chunk","rows":[[0,0,0]]})",1);
  assert(lastKind=="error");
  handleMappingCommand(R"({"op":"begin","width":8,"height":8})",1);
  now+=30000;
  handleMappingCommand(R"({"op":"commit"})",1);
  assert(lastKind=="error" && !needRestart);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'mapping.cpp'
            binary = Path(directory) / 'mapping'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(FIRMWARE), '-I', str(ROOT / 'libraries/ArduinoJson/src'),
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
