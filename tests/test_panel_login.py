"""Browser sessions and actual S2 login routes, using synthetic credentials only."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_network_security import function

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / 'firmware/LedPanelWiFi_v1.14'


class PanelLoginTests(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'login.cpp'
            binary = Path(directory) / 'login'
            cpp.write_text(source)
            result = subprocess.run(['g++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                     '-I', str(FIRMWARE), str(cpp), '-o', str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(binary)], check=True)

    def test_cookie_validation_expiry_rollover_rotation_and_revocation(self):
        self.compile_run(r'''
#include <cassert>
#include <string>
#include "panel_sessions.h"
int main() {
  PanelSessions sessions;
  std::string token(64,'a'), cookie="panel_sid="+token;
  assert(!sessions.valid(cookie.c_str(),0));
  sessions.issue(token.c_str(),100);
  assert(sessions.valid(cookie.c_str(),100));
  assert(sessions.valid(("other=x; "+cookie+"; tail=y").c_str(),101));
  assert(!sessions.valid(("x"+cookie).c_str(),101));
  assert(!sessions.valid((cookie+"x").c_str(),101));
  assert(!sessions.valid(cookie.substr(0,cookie.size()-1).c_str(),101));
  assert(!sessions.valid((cookie+"; "+cookie).c_str(),101));
  assert(!sessions.valid("panel_sid=",101));
  assert(!sessions.valid(nullptr,101));
  assert(!sessions.valid("",101));
  assert(sessions.valid(cookie.c_str(),100+PanelSessions::lifetime-1));
  assert(!sessions.valid(cookie.c_str(),100+PanelSessions::lifetime));
  sessions.issue(token.c_str(),UINT32_MAX-10);
  assert(sessions.valid(cookie.c_str(),10));
  sessions.revoke(cookie.c_str()); assert(!sessions.valid(cookie.c_str(),11));
  for(int i=0;i<5;++i) sessions.issue(std::string(64,'a'+i).c_str(),100+i);
  assert(!sessions.valid(cookie.c_str(),110)); // fifth login evicts oldest of four
  assert(sessions.valid(("panel_sid="+std::string(64,'e')).c_str(),110));
  PanelSessions rebooted;
  assert(!rebooted.valid(("panel_sid="+std::string(64,'e')).c_str(),110));
}
''')

    def test_actual_routes_protect_pages_uploads_and_websockets(self):
        login = (FIRMWARE / 'web_login.ino').read_text()
        web = (FIRMWARE / 'web.ino').read_text()
        main = (FIRMWARE / 'LedPanelWiFi_v1.14.ino').read_text()
        source = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <functional>
#include <string>
#include "panel_sessions.h"
#define PANEL_PROFILE_S2_MINI 1
using String=std::string;
const char* PANEL_ADMIN_USER="admin";
const char* PANEL_ADMIN_PASSWORD="synthetic-test-password";
const char* PANEL_LOGIN_PAGE="login form";
constexpr int HTTP_GET=1,HTTP_POST=2;
uint32_t now=100;
uint32_t millis() { return now; }
void esp_fill_random(void* out,size_t size) {
  static uint8_t next=0; auto* bytes=(uint8_t*)out;
  for(size_t i=0;i<size;++i) bytes[i]=next++;
}
struct AsyncWebServerResponse {
  int code; String body;
  std::map<String,String> headers;
  AsyncWebServerResponse(int c,const String& b):code(c),body(b){}
  void addHeader(const String& name,const String& value) { headers[name]=value; }
};
struct Param { String text; String value() { return text; } };
struct AsyncWebServerRequest {
  int verb=HTTP_GET,code=0; bool basic=false;
  String hostname="panel.local",body;
  std::map<String,String> headers,responseHeaders;
  std::map<String,Param> params;
  int method() { return verb; }
  String host() { return hostname; }
  bool hasHeader(const String& name) { return headers.count(name); }
  String header(const String& name) { return headers[name]; }
  bool hasParam(const String& name,bool) { return params.count(name); }
  Param* getParam(const String& name,bool) { return &params[name]; }
  AsyncWebServerResponse* beginResponse(int c,const char*,const String& b) { return new AsyncWebServerResponse(c,b); }
  AsyncWebServerResponse* beginResponse_P(int c,const char*,const char* b) { return new AsyncWebServerResponse(c,b); }
  void send(AsyncWebServerResponse* response) { code=response->code; body=response->body; responseHeaders=response->headers; delete response; }
  void send(int c,const char*,const char* b) { code=c; body=b; }
};
struct Server {
  std::map<std::pair<String,int>,std::function<void(AsyncWebServerRequest*)>> routes;
  void on(const char* path,int verb,std::function<void(AsyncWebServerRequest*)> fn) { routes[{path,verb}]=fn; }
  void addHandler(void*) {}
} server;
struct Socket {
  std::function<bool(AsyncWebServerRequest*)> filter;
  int closed=0;
  void closeAll() { ++closed; }
  void setFilter(std::function<bool(AsyncWebServerRequest*)> fn) { filter=fn; }
  void onEvent(int) {}
} ws;
int onEvent=0;
PanelSessions panelSessions;
'''
        for signature in ('bool panelSameOrigin(', 'bool panelRequestAuthenticated(',
                          'void panelAuthRedirect(', 'void initPanelLogin('):
            source += function(login, signature)
        source += function(web, 'bool authenticateWebRequest(')
        source += function(web, 'void initWebSocket(')
        start = main.index('// Upload callbacks run before')
        guard = main[start:main.index('static unsigned long startTimer;', start)]
        source += 'int writes=0; void upload(AsyncWebServerRequest* request) {\n' + guard + '\n++writes;\n}\n'
        source += r'''
void route(const char* path,int verb,AsyncWebServerRequest& request) {
  request.verb=verb; request.code=0; request.responseHeaders.clear();
  server.routes.at({path,verb})(&request);
}
int main() {
  initPanelLogin(); initWebSocket();
  AsyncWebServerRequest request;
  route("/login",HTTP_GET,request); assert(request.code==200);
  assert(request.responseHeaders["Cache-Control"]=="no-store");
  assert(!authenticateWebRequest(&request)); assert(request.code==303);
  assert(request.responseHeaders["Location"]=="/login");
  request.basic=true; assert(!panelRequestAuthenticated(&request)); // cached Basic must not defeat logout
  upload(&request); assert(writes==0); assert(!ws.filter(&request));
  request.params["username"].text="admin";
  request.params["password"].text=PANEL_ADMIN_PASSWORD;
  request.headers["Origin"]="http://evil.example";
  route("/login",HTTP_POST,request); assert(request.code==403);
  request.headers["Origin"]="http://panel.local";
  request.params["password"].text="wrong";
  route("/login",HTTP_POST,request); assert(request.code==303);
  assert(request.responseHeaders["Location"]=="/login?error=1");
  assert(!request.responseHeaders.count("Set-Cookie"));
  request.params["password"].text=PANEL_ADMIN_PASSWORD;
  route("/login",HTTP_POST,request); assert(request.code==303);
  String cookie=request.responseHeaders["Set-Cookie"];
  assert(cookie.find("HttpOnly")!=String::npos && cookie.find("SameSite=Strict")!=String::npos);
  request.headers["Cookie"]=cookie.substr(0,cookie.find(';'));
  assert(panelRequestAuthenticated(&request)); assert(ws.filter(&request));
  upload(&request); assert(writes==1);
  request.headers["Origin"]="http://evil.example";
  assert(!ws.filter(&request)); upload(&request); assert(writes==1);
  route("/logout",HTTP_POST,request); assert(request.code==403);
  request.headers["Origin"]="http://panel.local";
  assert(panelRequestAuthenticated(&request));
  route("/auth/status",HTTP_GET,request); assert(request.code==200);
  route("/logout",HTTP_POST,request); assert(request.code==303 && ws.closed==1);
  assert(request.responseHeaders["Set-Cookie"].find("Max-Age=0")!=String::npos);
  assert(!panelRequestAuthenticated(&request)); assert(!ws.filter(&request));
  route("/auth/status",HTTP_GET,request); assert(request.code==401);
  route("/logout",HTTP_POST,request); assert(ws.closed==1); // anonymous callers cannot disconnect other users
  request.verb=HTTP_GET;
  assert(!authenticateWebRequest(&request));
  request.verb=HTTP_POST; assert(!authenticateWebRequest(&request)); assert(request.code==401);
  request.headers.erase("Cookie"); request.headers.erase("Origin");
  route("/login",HTTP_POST,request); assert(request.code==403);
}
'''
        self.compile_run(source)

    def test_login_uses_password_manager_fields_and_cookie_gate_for_static_files(self):
        login = (FIRMWARE / 'web_login.ino').read_text()
        self.assertIn('autocomplete="username"', login)
        self.assertIn('autocomplete="current-password"', login)
        self.assertIn('method="post"', login)
        main = (FIRMWARE / 'LedPanelWiFi_v1.14.ino').read_text()
        static = main[main.index('server.serveStatic('):main.index('server.onNotFound(')]
        self.assertIn('.setFilter([](AsyncWebServerRequest* request) { return panelRequestAuthenticated(request); })', static)
