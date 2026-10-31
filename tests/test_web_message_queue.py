"""Exercise the actual ESP32 network-to-loop handoff with host queue doubles."""
import pathlib
import subprocess
import tempfile
import unittest

from test_network_security import function


class WebMessageQueueTests(unittest.TestCase):
    def test_callback_copies_and_defers_processing(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        web = (root / 'firmware/LedPanelWiFi_v1.14/web.ino').read_text()
        definitions = web[web.index('struct PendingWebMessage'):]
        # End at the guard following the queue declarations.
        definitions = definitions[:definitions.index('#endif')]
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#define ESP32 1
#define MAX_BUFFER_SIZE 32
#define WS_TEXT 1
#define pdTRUE 1
std::deque<void*> queue;
using QueueHandle_t = void*;
int allocations = 0;
void* allocate(size_t size) { ++allocations; return std::malloc(size); }
void release(void* p) { --allocations; std::free(p); }
#define malloc allocate
#define free release
int xQueueSend(QueueHandle_t, void* item, int timeout) {
  assert(timeout == 0);
  if (queue.size() == 4) return 0;
  queue.push_back(*static_cast<void**>(item)); return 1;
}
int xQueueReceive(QueueHandle_t, void* item, int timeout) {
  assert(timeout == 0);
  if (queue.empty()) return 0;
  *static_cast<void**>(item) = queue.front(); queue.pop_front(); return 1;
}
struct AwsFrameInfo { bool final; size_t index, len; int opcode; };
struct AsyncWebSocketClient { uint32_t id() { return 7; } } client;
bool connected = true;
struct Socket {
  AsyncWebSocketClient* client(uint32_t id) { assert(id == 7); return connected ? &::client : nullptr; }
} ws;
int processed = 0;
void processWebSocketMessage(void* arg, uint8_t* data, size_t len, AsyncWebSocketClient* c) {
  auto info = static_cast<AwsFrameInfo*>(arg);
  assert(info->final && info->index == 0 && info->len == len && info->opcode == WS_TEXT);
  assert(c == &client && len == 3 && std::memcmp(data, "abc", 3) == 0);
  ++processed;
}
'''
        source += definitions
        source += function(web, 'void handleWebSocketMessage(')
        source += function(web, 'void tickWebSocketMessages(')
        source += r'''
int main() {
  pendingWebMessages = &queue;
  uint8_t data[] = {'a','b','c'};
  AwsFrameInfo info = {true, 0, 3, WS_TEXT};
  handleWebSocketMessage(&info, data, 3, &client);
  data[0] = 'z'; // callback must own a copy, not the network buffer
  assert(processed == 0 && allocations == 1);
  tickWebSocketMessages();
  assert(processed == 1 && allocations == 0);
  data[0] = 'a';
  for (int i = 0; i < 5; ++i) handleWebSocketMessage(&info, data, 3, &client);
  assert(queue.size() == 4 && allocations == 4); // overflow is bounded and freed
  connected = false;
  for (int i = 0; i < 4; ++i) tickWebSocketMessages();
  assert(processed == 1 && allocations == 0); // disconnected clients discarded
  info.final = false;
  handleWebSocketMessage(&info, data, 3, &client);
  info.final = true; info.len = 33;
  handleWebSocketMessage(&info, data, 33, &client);
  assert(queue.empty() && allocations == 0);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'queue.cpp'
            binary = pathlib.Path(directory) / 'queue'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
