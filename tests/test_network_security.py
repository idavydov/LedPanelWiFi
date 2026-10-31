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
    def compile(self, source, run=False, headers=None):
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'test.cpp'
            binary = pathlib.Path(directory) / 'test'
            cpp.write_text(source)
            for name, content in (headers or {}).items():
                (pathlib.Path(directory) / name).write_text(content)
            result = subprocess.run(
                ['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                 '-I', directory, '-I', str(FIRMWARE), str(cpp), '-o', str(binary)],
                capture_output=True, text=True)
            if run:
                self.assertEqual(result.returncode, 0, result.stderr)
                subprocess.run([str(binary)], check=True)
            return result

    def test_password_configuration_fails_closed(self):
        for password in (None, ''):
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

    def test_open_ap_setup_and_password_persistence(self):
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#define ESP32 1
#define PANEL_DEVICE_CREDENTIALS 1
#define PROGMEM
struct String : std::string {
  using std::string::string;
  using std::string::operator=;
  String(const std::string& value) : std::string(value) {}
  bool isEmpty() const { return empty(); }
};
static std::map<std::string, String> storage;
static bool storageAvailable = true, writesWork = true;
struct Preferences {
  bool begin(const char*, bool) { return storageAvailable; }
  String getString(const char* key, const char*) { return storage[key]; }
  bool getBool(const char* key, bool) { return storage[key] == "true"; }
  size_t putString(const char* key, const String& value) {
    if (!writesWork) return 0;
    storage[key] = value;
    return value.length();
  }
  size_t putBool(const char* key, bool) {
    if (!writesWork) return 0;
    storage[key] = "true";
    return 1;
  }
  void end() {}
};
#include "network_security.h"
struct { int softAPIP() { return 4; } } WiFi;
struct Client { int ip = 4; int localIP() { return ip; } };
struct Parameter { String text; const String& value() { return text; } };
struct AsyncWebServerResponse {
  int code; String body;
  void addHeader(const char*, const char*) {}
};
struct AsyncWebServerRequest {
  Client connection;
  std::map<std::string, Parameter> fields;
  String origin, hostname = "192.168.4.1", body;
  int status = 0;
  Client* client() { return &connection; }
  bool hasHeader(const char*) { return !origin.isEmpty(); }
  String header(const char*) { return origin; }
  String host() { return hostname; }
  bool hasParam(const char* name, bool) { return fields.count(name); }
  Parameter* getParam(const char* name, bool) { return &fields[name]; }
  void send(int code, const char* = "", const char* text = "") { status=code; body=text; }
  void send(AsyncWebServerResponse* response) { status=response->code; body=response->body; delete response; }
  AsyncWebServerResponse* beginResponse_P(int code, const char*, const char* text) {
    return new AsyncWebServerResponse{code, text};
  }
};
constexpr int HTTP_GET=0, HTTP_POST=1;
struct {
  void on(const char*, int, void (*)(AsyncWebServerRequest*)) {}
  void onNotFound(void (*)(AsyncWebServerRequest*)) {}
} server;
static String savedSsid, savedWifiPassword;
static bool dhcp=false, softAP=true, commitWorks=true;
void putSsid(const String& value) { savedSsid=value; }
void putPass(const String& value) { savedWifiPassword=value; }
void putUseDHCP(bool value) { dhcp=value; }
void putUseSoftAP(bool value) { softAP=value; }
void putSoftAPPass(const String&) {}
struct { bool commit() { return commitWorks; } } EEPROM;
unsigned long millis() { return 123; }
#include "setup_web.ino"
int main() {
  // A stored value without the completion marker does not lock out first setup.
  storage["admin"] = "previous-generated-value";
  assert(initializePanelSecurity());
  assert(panelNeedsSetup && panelAdminPassword.isEmpty());
  AsyncWebServerRequest request;
  handlePanelSetupPage(&request);
  assert(request.status == 200 && request.body.find("<form") != std::string::npos);
  handlePanelSetupSave(&request);
  assert(request.status == 400 && storage["configured"] != "true");
  assert(request.body.find("confirm_password") == std::string::npos);
  assert(request.body.find("minlength=\"16\"") == std::string::npos);
  request.fields["admin_password"].text = "7";
  request.fields["ssid"].text = "test-network";
  request.fields["wifi_password"].text = "test-wifi-password";
  request.connection.ip = 5; // Never accept setup via a station-network interface.
  handlePanelSetupSave(&request);
  assert(request.status == 403);
  request.connection.ip = 4;
  request.origin = "http://another.example";
  handlePanelSetupSave(&request);
  assert(request.status == 403);
  request.origin = "http://192.168.4.1";
  commitWorks = false;
  handlePanelSetupSave(&request);
  assert(request.status == 500 && storage["configured"] != "true");
  commitWorks = true;
  writesWork = false;
  handlePanelSetupSave(&request);
  assert(request.status == 500 && !panelSetupSaved);
  writesWork = true;
  handlePanelSetupSave(&request);
  assert(request.status == 200 && panelSetupSaved && panelSetupSavedAt == 123);
  assert(savedSsid == "test-network" && savedWifiPassword == "test-wifi-password");
  assert(dhcp && !softAP);
  assert(request.body.find("7") == std::string::npos);
  assert(request.body.find("test-wifi-password") == std::string::npos);
  handlePanelSetupSave(&request);
  assert(request.status == 403); // No second submission before reboot.
  assert(initializePanelSecurity());
  assert(!panelNeedsSetup && panelAdminPassword == "7");
  assert(!savePanelAdminPassword("different-user-password"));
  panelSetupSaved = false;
  handlePanelSetupPage(&request);
  assert(request.status == 403); // Setup stays closed after reboot.
  storageAvailable = false;
  assert(!initializePanelSecurity());
  storageAvailable = true;
  storage["admin"] = "";
  assert(!initializePanelSecurity());
}
'''
        self.compile(source, run=True, headers={'Preferences.h': '#pragma once\n'})

    def test_s2_profile_preserves_all_200_address_slots(self):
        utility = (FIRMWARE / 'utility.ino').read_text()
        signatures = ['uint8_t THIS_X(', 'uint8_t THIS_Y(', 'uint8_t THIS_W(',
                      'uint8_t THIS_SX(', 'uint8_t THIS_SY(', 'uint8_t THIS_SW(']
        helpers = '\n'.join(function(utility, signature) for signature in signatures)
        mapping = function(utility, 'int16_t getPixelNumber(')
        eeprom = (FIRMWARE / 'eeprom.ino').read_text()
        initializer = eeprom[eeprom.index('const int8_t defaultLedRGB'):]
        initializer = initializer[:initializer.index(';') + 1]
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
constexpr int RGB=1, RBG=2, GBR=3, BRG=4, BGR=5;
#include "profiles/esp32_s2_mini.h"
uint8_t pWIDTH=WIDTH, pHEIGHT=HEIGHT, sWIDTH=WIDTH, sHEIGHT=HEIGHT;
uint8_t sMATRIX_TYPE=MATRIX_TYPE, sCONNECTION_ANGLE=CONNECTION_ANGLE, sSTRIP_DIRECTION=STRIP_DIRECTION;
uint8_t mWIDTH=META_MATRIX_WIDTH, mHEIGHT=META_MATRIX_HEIGHT;
uint8_t mTYPE=META_MATRIX_TYPE, mANGLE=META_MATRIX_ANGLE, mDIRECTION=META_MATRIX_DIRECTION;
int16_t* imap=nullptr;
constexpr int NUM_LEDS=WIDTH*HEIGHT;
'''
        # Legacy helpers have unused coordinates in some orientations.
        source = '#pragma GCC diagnostic ignored "-Wunused-parameter"\n' + source
        source += helpers + '\n' + mapping + '\nint main() {\n' + initializer
        source += r'''
  assert(LED_PIN == 3);
  assert(defaultLedRGB == 1); // Persist RGB, rather than the old hardcoded GRB.
  assert(DEBUG_SERIAL == 0);
  bool seen[200] = {};
  for (int y = 0; y < HEIGHT; ++y) {
    for (int x = 0; x < WIDTH; ++x) {
      int slot = getPixelNumber(x, y);
      assert(slot >= 0 && slot < 200 && !seen[slot]);
      seen[slot] = true;
    }
  }
  for (bool used : seen) assert(used);
  assert(getPixelNumber(19, 9) == 199);
  assert(getPixelNumber(20, 9) == -1);
}
'''
        self.compile(source, run=True)


if __name__ == '__main__':
    unittest.main()
