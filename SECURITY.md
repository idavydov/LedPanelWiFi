# Device administrator password

Before building, add a unique password of at least 16 characters to your local
`firmware/LedPanelWiFi_v1.14/a_def_pass.h`:

```cpp
#define PANEL_ADMIN_PASSWORD "<your unique password of at least 16 characters>"
```

Replace the placeholder. Use a password different from your Wi-Fi password.
The build fails if this setting is missing or shorter than 16 characters.
When `A_DEF_PASS` is disabled, provide the same definition through build flags.
Do not commit the password header.

Open the panel's address in a browser and log in as `admin` with this password.
The UI, WebSocket controls, uploads and downloadable settings backups require
authentication. The existing UI and bundled web assets need no changes.
Browser WebSocket connections must come from the panel's own origin; open the
UI from the device rather than a separate development server.

OTA updates, when enabled with `USE_OTA`, require the same password. Supply it
to your OTA uploader. Tools that cannot authenticate must use USB instead;
do not remove OTA authentication to accommodate them. Changing the password
requires rebuilding and flashing the firmware; it does not reset EEPROM.

The web server still uses HTTP. Authentication restricts access but does not
encrypt passwords or settings in transit. Use the panel on a trusted network.
