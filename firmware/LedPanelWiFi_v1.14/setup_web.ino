#if defined(PANEL_DEVICE_CREDENTIALS)

static const char PANEL_SETUP_PAGE[] PROGMEM = R"html(
<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel setup</title>
<style>
body{font:16px system-ui;margin:40px auto;padding:0 20px;max-width:420px}
label{display:block;margin:20px 0}input,button{box-sizing:border-box;width:100%;padding:12px;font:inherit}
small{display:block;color:#555;margin-top:6px}button{cursor:pointer}
</style>
<h1>Set up your panel</h1>
<form method="post" action="/setup">
<label>Administrator password
<input type="password" name="admin_password" autocomplete="new-password" required>
<small>Use this password to log in as admin.</small></label>
<label>Home Wi-Fi name
<input name="ssid" maxlength="32" autocomplete="off" required></label>
<label>Home Wi-Fi password
<input type="password" name="wifi_password" minlength="8" maxlength="64" autocomplete="off" required></label>
<button>Save and connect</button>
</form></html>
)html";

bool allowPanelSetupRequest(AsyncWebServerRequest *request) {
  if (!panelNeedsSetup || panelSetupSaved ||
      request->client()->localIP() != WiFi.softAPIP()) return false;
  if (!request->hasHeader("Origin")) return true;
  return request->header("Origin") == String("http://") + request->host();
}

void handlePanelSetupPage(AsyncWebServerRequest *request) {
  if (!allowPanelSetupRequest(request)) {
    request->send(403, "text/plain", "Setup is unavailable.");
    return;
  }
  AsyncWebServerResponse *response = request->beginResponse_P(200, "text/html", PANEL_SETUP_PAGE);
  response->addHeader("Cache-Control", "no-store");
  request->send(response);
}

void handlePanelSetupSave(AsyncWebServerRequest *request) {
  if (!allowPanelSetupRequest(request)) {
    request->send(403, "text/plain", "Setup is unavailable.");
    return;
  }
  if (!request->hasParam("admin_password", true) ||
      !request->hasParam("ssid", true) || !request->hasParam("wifi_password", true)) {
    request->send(400, "text/plain", "Fill in all fields.");
    return;
  }
  String password = request->getParam("admin_password", true)->value();
  String ssid = request->getParam("ssid", true)->value();
  String wifiPassword = request->getParam("wifi_password", true)->value();
  if (password.isEmpty() ||
      ssid.isEmpty() || ssid.length() > 32 || wifiPassword.length() < 8 || wifiPassword.length() > 64) {
    request->send(400, "text/plain", "Enter an administrator password and valid Wi-Fi details.");
    return;
  }

  putSsid(ssid);
  putPass(wifiPassword);
  putUseDHCP(true);
  putUseSoftAP(false);
  putSoftAPPass("");
  if (!EEPROM.commit() || !savePanelAdminPassword(password)) {
    request->send(500, "text/plain", "Could not save settings. Please try again.");
    return;
  }
  request->send(200, "text/html", "<h1>Settings saved</h1><p>The panel is restarting. Reconnect to your home Wi-Fi and open <a href='http://GlassPanel.local'>GlassPanel.local</a>. Log in as admin with the password you chose.</p>");
  panelSetupSavedAt = millis();
  panelSetupSaved = true;
}

void initPanelSetup() {
  server.on("/", HTTP_GET, handlePanelSetupPage);
  server.on("/setup", HTTP_GET, handlePanelSetupPage);
  server.on("/setup", HTTP_POST, handlePanelSetupSave);
  server.onNotFound([](AsyncWebServerRequest *request) { request->send(404); });
}

#endif
