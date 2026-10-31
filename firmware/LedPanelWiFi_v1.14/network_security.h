#pragma once

#if defined(PANEL_DEVICE_CREDENTIALS) && defined(ESP32)
#include <Preferences.h>

static const char PANEL_ADMIN_USER[] = "admin";
static String panelAdminPassword;
static bool panelNeedsSetup = true;
static volatile bool panelSetupSaved = false;
static volatile unsigned long panelSetupSavedAt = 0;
#define PANEL_ADMIN_PASSWORD panelAdminPassword.c_str()

static bool initializePanelSecurity() {
  Preferences preferences;
  if (!preferences.begin("panel-security", false)) return false;
  panelNeedsSetup = !preferences.getBool("configured", false);
  if (!panelNeedsSetup) panelAdminPassword = preferences.getString("admin", "");
  preferences.end();
  return panelNeedsSetup || !panelAdminPassword.isEmpty();
}

static bool savePanelAdminPassword(const String& password) {
  if (!panelNeedsSetup || password.isEmpty()) return false;
  Preferences preferences;
  if (!preferences.begin("panel-security", false)) return false;
  bool ok = preferences.putString("admin", password) == password.length();
  if (ok) ok = preferences.putBool("configured", true) != 0;
  preferences.end();
  return ok;
}
#else
// Define this as a plain string literal in a_def_pass.h or build flags.
// Do not provide a shared/default password: missing configuration must fail closed.
#ifndef PANEL_ADMIN_PASSWORD
#error "Define PANEL_ADMIN_PASSWORD in a_def_pass.h or build flags."
#else
static_assert(sizeof(PANEL_ADMIN_PASSWORD) > 1,
              "PANEL_ADMIN_PASSWORD must not be empty.");
static const char PANEL_ADMIN_USER[] = "admin";
#endif
#endif
