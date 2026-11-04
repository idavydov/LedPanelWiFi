"""Regression tests for cooperative settings replies and UTF-8 chunk boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


class WebResponseTests(unittest.TestCase):
    def test_settings_replies_yield_between_batches_and_keep_unsent_keys(self):
        source = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>
struct String:std::string {
  using std::string::string;
  String(const std::string& value):std::string(value){}
  char charAt(size_t i) const { return i<size()?at(i):0; }
  int indexOf(char c) const { auto p=find(c); return p==npos ? -1 : int(p); }
  void remove(size_t start,size_t count) { erase(start,count); }
  String substring(size_t start,size_t end) const { return substr(start,end-start); }
  void trim() { auto a=find_first_not_of(" "); if(a==npos)clear(); else *this=substr(a,find_last_not_of(" ")-a+1); }
};
struct {
  int clients=1; bool writable=true;
  int count() { return clients; }
  bool availableForWriteAll() { return writable; }
} ws;
int thisMode=0;
bool addDuringRead=false,stopAfterFirst=false;
String* pending;
std::vector<String> sent;
String getStateValue(const String& key,int,bool) {
  if(addDuringRead) {
    assert(pending->find("|B|")!=std::string::npos);
    *pending+="X|"; addDuringRead=false;
  }
  return key+"-value";
}
void SendWebKey(const String& key,const String& value) {
  assert(value==key+"-value"); sent.push_back(key);
  if(stopAfterFirst) ws.writable=false;
}
'''
        source += function((FIRMWARE / 'utility.ino').read_text(), 'void SendCurrentState(')
        source += r'''
int main() {
  String keys="|A|B|C|UP|"; pending=&keys; addDuringRead=true;
  SendCurrentState(keys);
  assert(sent.size()==2 && sent[0]=="A" && sent[1]=="B" && keys=="|C|UP|X|");
  ws.writable=false;
  SendCurrentState(keys); assert(sent.size()==2 && keys=="|C|UP|X|");
  ws.writable=true; SendCurrentState(keys);
  assert(sent.size()==4 && keys=="|X|");
  SendCurrentState(keys); assert(sent.size()==5 && keys.empty());
  keys="|A|B|"; stopAfterFirst=true;
  SendCurrentState(keys); assert(keys=="|B|"); // queue filled mid-batch: retain remainder
  ws.clients=0; SendCurrentState(keys); assert(keys.empty());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'replies.cpp'
            binary = Path(directory) / 'replies'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_every_chunk_is_valid_utf8_and_reassembles_exactly(self):
        source = r'''
#include <iostream>
#include <iterator>
#include <string>
#include "web_response_helpers.h"
int main(int,char** argv) {
  std::string text{std::istreambuf_iterator<char>(std::cin),{}};
  size_t limit=std::stoul(argv[1]),offset=0;
  while(offset<text.size()) {
    size_t n=webUtf8Prefix(text.data()+offset,text.size()-offset,limit);
    if(!n) return 1;
    std::cout.write(text.data()+offset,n); std::cout.put('\0'); offset+=n;
  }
}
'''
        text = ('ASCII, café, цвет, 中, 🌲🙂\n' * 150).encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'utf8.cpp'
            binary = Path(directory) / 'utf8'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-I', str(FIRMWARE), str(cpp), '-o', str(binary)], check=True)
            for limit in (4, 5, 7, 31, 463, 1999):
                with self.subTest(limit=limit):
                    result = subprocess.run([str(binary), str(limit)], input=text, capture_output=True, check=True)
                    chunks = result.stdout.split(b'\0')[:-1]
                    self.assertEqual(b''.join(chunks), text)
                    for chunk in chunks:
                        self.assertLessEqual(len(chunk), limit)
                        chunk.decode('utf-8', errors='strict')
