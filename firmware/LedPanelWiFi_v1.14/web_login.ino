#if defined(PANEL_PROFILE_S2_MINI)
#include "panel_sessions.h"
#include <esp_system.h>

PanelSessions panelSessions;

static const char PANEL_LOGIN_PAGE[] PROGMEM = R"html(
<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in to GlassPanel</title>
<style>body{font:16px system-ui;max-width:360px;margin:12vh auto;padding:20px}
label{display:block;margin:20px 0}input,button{box-sizing:border-box;width:100%;padding:12px;font:inherit}
input{display:block;margin-top:6px}button{cursor:pointer}.error{color:#b32020}</style>
<h1>GlassPanel</h1><p>Sign in with your administrator password.</p>
<p class="error" id="error" hidden>Username or password incorrect. Please try again.</p>
<form action="/login" method="post">
<label>Username<input id="username" name="username" autocomplete="username" value="admin" required></label>
<label>Password<input id="password" name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Sign in</button></form>
<script>document.getElementById('error').hidden=!new URLSearchParams(location.search).has('error');</script>
</html>
)html";

bool panelSameOrigin(AsyncWebServerRequest* request) {
  if (!request->hasHeader("Origin")) return false;
  String origin = request->header("Origin");
  return origin == String("http://") + request->host() || origin == String("https://") + request->host();
}

bool panelRequestAuthenticated(AsyncWebServerRequest* request) {
  if (request->hasHeader("Origin") && !panelSameOrigin(request)) return false;
  return panelSessions.valid(request->header("Cookie").c_str(), millis());
}

void panelAuthRedirect(AsyncWebServerRequest* request, const char* path, const String& cookie) {
  auto* response = request->beginResponse(303, "text/plain", "");
  response->addHeader("Location", path);
  response->addHeader("Cache-Control", "no-store");
  if (cookie.length()) response->addHeader("Set-Cookie", cookie);
  request->send(response);
}

void initPanelLogin() {
  server.on("/login", HTTP_GET, [](AsyncWebServerRequest* request) {
    auto* response = request->beginResponse_P(200, "text/html; charset=utf-8", PANEL_LOGIN_PAGE);
    response->addHeader("Cache-Control", "no-store");
    response->addHeader("X-Frame-Options", "DENY");
    request->send(response);
  });
  server.on("/login", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!panelSameOrigin(request)) { request->send(403, "text/plain", "Use the panel's own sign-in page."); return; }
    if (!request->hasParam("username", true) || !request->hasParam("password", true) ||
        request->getParam("username", true)->value() != PANEL_ADMIN_USER ||
        request->getParam("password", true)->value() != PANEL_ADMIN_PASSWORD) {
      panelAuthRedirect(request, "/login?error=1", String()); return;
    }
    uint8_t random[32]; char token[65];
    esp_fill_random(random, sizeof(random));
    static const char hex[] = "0123456789abcdef";
    for (unsigned i = 0; i < sizeof(random); ++i) { token[i*2] = hex[random[i] >> 4]; token[i*2+1] = hex[random[i] & 15]; }
    token[64] = 0;
    panelSessions.issue(token, millis());
    panelAuthRedirect(request, "/", String("panel_sid=") + token + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200");
  });
  server.on("/auth/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    auto* response = request->beginResponse(panelRequestAuthenticated(request) ? 200 : 401, "text/plain", "");
    response->addHeader("Cache-Control", "no-store"); request->send(response);
  });
  server.on("/logout", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!panelSameOrigin(request)) { request->send(403, "text/plain", "Wrong origin."); return; }
    bool authenticated = panelRequestAuthenticated(request);
    panelSessions.revoke(request->header("Cookie").c_str());
    if (authenticated) ws.closeAll(); // Other authenticated tabs can reconnect.
    panelAuthRedirect(request, "/login", "panel_sid=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0");
  });
}
#endif
