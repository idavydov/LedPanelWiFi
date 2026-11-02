"""Exercise upstream event queue code under a burst and connection cleanup."""
import pathlib
import subprocess
import tempfile
import unittest

from test_network_security import function


class AsyncTCPQueueTests(unittest.TestCase):
    def test_s2_long_event_burst_yields_to_idle_without_disabling_watchdog(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        upstream = (root / 'libraries/AsyncTCP/src/AsyncTCP.cpp').read_text()
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#define CONFIG_ASYNC_TCP_COOPERATIVE_MS 10
#define CONFIG_ASYNC_TCP_USE_WDT 1
#define ASYNC_TCP_MAX_TASK_SLEEP 1000
#define ESP_OK 0
#define pdTRUE 1
#define async_tcp_log_d(...) ((void)0)
#define async_tcp_log_w(...) ((void)0)
#define async_tcp_log_elapsed(tag, statement) statement
uint32_t now=0, sinceYield=0;
int yields=0, feeds=0, events=0;
uint32_t millis() { return now; }
void vTaskDelay(int ticks) { assert(ticks==1 && now-sinceYield<=12); ++yields; ++now; sinceYield=now; }
int esp_task_wdt_add(void*) { return ESP_OK; }
void esp_task_wdt_delete(void*) {}
void esp_task_wdt_reset() { ++feeds; }
struct Done {};
void ulTaskNotifyTake(int, int) { throw Done{}; }
void vTaskDelete(void*) {}
void* _async_service_task_handle=nullptr;
struct Packet {} packet;
Packet* _get_async_event() { return events<100 ? &packet : nullptr; }
struct AsyncTCP_detail { static void handle_async_event(Packet*) { ++events; now+=4; } };
'''
        source += function(upstream, 'static void _async_service_task(')
        source += r'''
int main() {
  try { _async_service_task(nullptr); } catch (Done&) {}
  assert(events==100 && yields>=33 && feeds>=100);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'fairness.cpp'
            binary = pathlib.Path(directory) / 'fairness'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra',
                            '-Wno-unused-parameter', str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_burst_cleanup_and_poll_coalescing(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        library = root / 'libraries/AsyncTCP/src'
        upstream = (library / 'AsyncTCP.cpp').read_text()
        source = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <utility>
#include "AsyncTCPSimpleIntrusiveList.h"
#define CONFIG_ASYNC_TCP_QUEUE_SIZE 64
#define async_tcp_log_d(...) ((void)0)
struct AsyncClient {} a, b;
enum { LWIP_TCP_RECV, LWIP_TCP_POLL, LWIP_TCP_SENT };
int released = 0, buffersReleased = 0, notified = 0;
struct lwip_tcp_event_packet_t {
  lwip_tcp_event_packet_t* next = nullptr;
  int event;
  AsyncClient* client;
  struct { void* pb = nullptr; } recv;
  int sequence;
  lwip_tcp_event_packet_t(int kind, AsyncClient* c, int n) : event(kind), client(c), sequence(n) {}
  ~lwip_tcp_event_packet_t() { ++released; }
};
void pbuf_free(void*) { ++buffersReleased; }
struct queue_mutex_guard {};
static SimpleIntrusiveList<lwip_tcp_event_packet_t> _async_queue;
static int _async_service_task_handle = 1;
void xTaskNotifyGive(int task) { assert(task == 1); ++notified; }
static uint32_t _xor_shift_state = 31;
'''
        for signature in ('static uint32_t _xor_shift_next(',
                          'static void _free_event(',
                          'static inline void _send_async_event(',
                          'static inline void _prepend_async_event(',
                          'static inline lwip_tcp_event_packet_t *_get_async_event(',
                          'static size_t _remove_events_for_client('):
            source += function(upstream, signature) + '\n'
        source += r'''
int main() {
  // Exceed the old queue's 32 slots without a consumer running.
  for (int i = 0; i < 128; ++i)
    _send_async_event(new lwip_tcp_event_packet_t(LWIP_TCP_SENT, i % 2 ? &a : &b, i));
  assert(notified == 128 && _async_queue.size() == 128);
  assert(_remove_events_for_client(&a) == 64);
  assert(released == 64 && _async_queue.size() == 64);
  for (int i = 0; i < 128; i += 2) {
    auto event = _get_async_event();
    assert(event && event->client == &b && event->sequence == i);
    _free_event(event);
  }
  assert(!_get_async_event() && released == 128);
  // Polls for one client collapse; a following ACK remains ordered.
  _send_async_event(new lwip_tcp_event_packet_t(LWIP_TCP_POLL, &a, 1));
  _send_async_event(new lwip_tcp_event_packet_t(LWIP_TCP_POLL, &a, 2));
  _send_async_event(new lwip_tcp_event_packet_t(LWIP_TCP_SENT, &b, 3));
  auto poll = _get_async_event();
  assert(poll->sequence == 1 && _async_queue.size() == 1);
  _free_event(poll);
  auto ack = _get_async_event();
  assert(ack->sequence == 3);
  _free_event(ack);
  // Cleanup also releases queued receive buffers.
  auto rx = new lwip_tcp_event_packet_t(LWIP_TCP_RECV, &a, 4);
  rx->recv.pb = &a;
  _prepend_async_event(rx);
  assert(_remove_events_for_client(&a) == 1 && buffersReleased == 1);
  assert(_async_queue.size() == 0 && _async_queue.validate_tail());
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'tcp_queue.cpp'
            binary = pathlib.Path(directory) / 'tcp_queue'
            cpp.write_text(source)
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra',
                            '-Wno-unused-variable', '-I', str(library),
                            str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
