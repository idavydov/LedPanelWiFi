"""Host-side security regressions; run with python3 -m unittest discover -s tests -v.

Compile the firmware's actual auth/initialization code against request doubles.
No board, Arduino toolchain or network downloads are needed.
"""
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class NetworkSecurityTests(unittest.TestCase):
    def compile(self, source, run=False):
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'test.cpp'
            binary = pathlib.Path(directory) / 'test'
            cpp.write_text(source)
            result = subprocess.run(
                ['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                 '-I', str(FIRMWARE), str(cpp), '-o', str(binary)],
                capture_output=True, text=True)
            if run:
                self.assertEqual(result.returncode, 0, result.stderr)
                subprocess.run([str(binary)], check=True)
            return result

    def test_password_configuration_fails_closed(self):
        for password in (None, '', 'short', '123456789012345'):
            with self.subTest(password=password):
                define = '' if password is None else f'#define PANEL_ADMIN_PASSWORD "{password}"\n'
                result = self.compile(define + '#include "network_security.h"\nint main() {}')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('PANEL_ADMIN_PASSWORD', result.stderr)

    def test_authentication_and_browser_origins(self):
        web = (FIRMWARE / 'web.ino').read_text()
        main = (FIRMWARE / 'LedPanelWiFi_v1.14.ino').read_text()
        upload_start = main.index('// Upload callbacks run before')
        upload_guard = main[upload_start:main.index('static unsigned long startTimer;', upload_start)]
        source = r'''
#include <cassert>
#include <functional>
#include <string>
#define PANEL_ADMIN_PASSWORD "test-only-password-1234"
#include "network_security.h"
using String = std::string;
struct AsyncWebServerRequest {
  String user, password, origin, hostname = "panel.local";
  int challenges = 0;
  bool authenticate(const char* u, const char* p) { return user == u && password == p; }
  void requestAuthentication() { ++challenges; }
  bool hasHeader(const char*) { return !origin.empty(); }
  String header(const char*) { return origin; }
  String host() { return hostname; }
};
struct Socket {
  String user, password;
  std::function<bool(AsyncWebServerRequest*)> filter;
  void setAuthentication(const char* u, const char* p) { user = u; password = p; }
  void setFilter(std::function<bool(AsyncWebServerRequest*)> f) { filter = f; }
  void onEvent(int) {}
} ws;
struct Server { void addHandler(Socket*) {} } server;
int onEvent = 0;
'''
        source += function(web, 'bool authenticateWebRequest(') + '\n'
        source += function(web, 'void initWebSocket()') + '\n'
        source += 'void upload(AsyncWebServerRequest* request, int& writes) {\n' + upload_guard + '\n++writes;\n}\n'
        source += r'''
int main() {
  AsyncWebServerRequest request;
  assert(!authenticateWebRequest(&request));
  assert(request.challenges == 1);
  int writes = 0;
  upload(&request, writes);
  assert(writes == 0);
  request.user = "admin";
  request.password = "wrong-password";
  assert(!authenticateWebRequest(&request));
  upload(&request, writes);
  assert(writes == 0);
  request.password = PANEL_ADMIN_PASSWORD;
  assert(authenticateWebRequest(&request));
  upload(&request, writes);
  assert(writes == 1);
  initWebSocket();
  assert(ws.user == "admin" && ws.password == PANEL_ADMIN_PASSWORD);
  assert(ws.filter(&request)); // Non-browser clients must still authenticate.
  request.origin = "http://panel.local";
  assert(ws.filter(&request));
  request.hostname = "192.168.0.100:8080";
  request.origin = "http://192.168.0.100:8080";
  assert(ws.filter(&request));
  request.origin = "http://192.168.0.100";
  assert(!ws.filter(&request));
  request.origin = "http://evil.example";
  assert(!ws.filter(&request));
  request.origin = "null";
  assert(!ws.filter(&request));
}
'''
        self.compile(source, run=True)

    def test_static_files_backups_and_ota_are_protected(self):
        main = (FIRMWARE / 'LedPanelWiFi_v1.14.ino').read_text()
        static_handler = main[main.index('server.serveStatic('):main.index('server.onNotFound(')]
        self.assertIn('.setAuthentication(PANEL_ADMIN_USER, PANEL_ADMIN_PASSWORD)', static_handler)
        self.assertIn('.setCacheControl("private, no-store")', static_handler)
        self.assertNotIn('addHeader("Access-Control-Allow-Origin", "*")', main)
        ota = main[main.index('ArduinoOTA.setHostname('):main.index('ArduinoOTA.begin();')]
        self.assertIn('ArduinoOTA.setPassword(PANEL_ADMIN_PASSWORD);', ota)
        web = (FIRMWARE / 'web.ino').read_text()
        self.assertIn('if (!authenticateWebRequest(request)) return;',
                      function(web, 'void handleNotFound('))


if __name__ == '__main__':
    unittest.main()
