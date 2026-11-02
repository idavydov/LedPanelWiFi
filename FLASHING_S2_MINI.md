# ESP32-S2 Mini first flash

The `esp32_s2_mini` environment targets a LOLIN/WEMOS S2 Mini with 4 MiB flash.
It uses GPIO 3, WS2812-compatible 800 kHz output, and FastLED `RGB` (NeoPixel
`NEO_RGB`). The temporary canvas is 20 × 10, parallel rows from the bottom left:
`slot = y * 20 + x + 1`. It transmits all 200 slots, including any missing
factory-addressed LEDs. The final slot is index 199 at `(19, 9)`.

Optional peripherals, weather requests, and E1.31 are disabled. Brightness
defaults to 3/255 (about 1%). OTA remains enabled with administrator authentication.

## Build

```sh
python3 tools/prepare_s2_mini.py
pio run -e esp32_s2_mini
pio run -e esp32_s2_mini -t buildfs
```

The preparation script unpacks bundled FastLED 3.6.0 and ESPAsyncWebServer 1.2.3
into ignored `.pio/vendor/s2_mini/`. PlatformIO pins Arduino 2.0.17 through
`espressif32@6.13.0`. The firmware uses `esp32_4MiB.csv` for OTA and LittleFS.

## Flash when ready

Close any serial monitor and use the running panel's USB serial port below.
The uploader requests bootloader mode over USB, follows the board if its port
changes, and restarts the application afterward. Normally no buttons are needed.

```sh
pio run -e esp32_s2_mini -t upload --upload-port /dev/ttyACM0
pio run -e esp32_s2_mini -t uploadfs --upload-port /dev/ttyACM0
```

Wait for the panel's USB application port to return before the second command;
its name can change. If the installed firmware is unresponsive or no USB port
appears, hold BOOT, tap RESET, release BOOT, and upload to that recovery port.

Upload both on the first flash. Later firmware-only changes need just `upload`;
run `uploadfs` again only when the web assets change, since it replaces existing
files. Existing EEPROM settings can override this profile; check GPIO 3,
RGB, and 200 slots in the UI if this board previously ran this project. Do not
erase a configured device without preserving anything you need.

## First boot

Join the open `PanelAP` network and open `http://192.168.4.1`. Choose an
administrator password and enter your home Wi-Fi name and password. The panel
saves them on the device and restarts; reconnect to home Wi-Fi and open
`http://GlassPanel.local`, logging in as `admin` with your chosen password.

Later, adjust the canvas and index map to match the LEDs on the glass. Retain
factory slot numbers and the 200-slot output; removing an LED does not renumber
the others.

## Index map

The matrix settings select a preloaded map; they do not edit LED positions.
The supplied `data/20x10.map` preserves the current parallel layout and all
200 slots. Upload the filesystem over OTA (below), open Settings → Matrix, choose Index map,
select `20x10`, and press Apply. One restart after Apply is expected.

For a custom layout, create a CSV with 10 rows and 20 columns, top row first.
Each cell is a zero-based factory slot index (`0`..`199`), or `-1` for an empty
position. Slot 200 is index `199`; removing LEDs never shifts these numbers.
Keep this canvas size for the current profile to retain the 200-slot output.

```sh
python3 tools/make_index_map.py --csv /path/to/layout.csv
pio run -e esp32_s2_mini -t buildfs
python3 tools/ota_upload.py GlassPanel.local --filesystem
```

Running the generator without `--csv` restores the starter map. Map files are
binary, with signature `A5 A5`, width and height bytes, then signed 16-bit
little-endian indices; renaming a CSV to `.map` does not work.

### Wi-Fi / OTA updates

Close the panel's browser tabs before updating. The running firmware supports
authenticated firmware and filesystem OTA on port 3232. Use the panel's IP if
`GlassPanel.local` does not resolve. The helper prompts for the administrator
password without saving it or putting it in command-line arguments.

```sh
# Firmware, when firmware source changed:
pio run -e esp32_s2_mini
python3 tools/ota_upload.py GlassPanel.local

# UI and/or index map:
pio run -e esp32_s2_mini -t buildfs
python3 tools/ota_upload.py GlassPanel.local --filesystem
```

Wait for the panel to restart between uploads. Filesystem OTA replaces LittleFS
contents, including custom maps/files; it preserves NVS credentials and EEPROM
settings. For this UI/map fix, only the filesystem update is needed. After a
filesystem upload, reload the UI to fetch the new bundles. If the upload cannot
connect back, allow the uploader's incoming TCP connection on the local firewall;
`--local-address` selects an interface on computers with multiple networks.

## IR remote

Connect VS1838B VCC to 3V3, GND to GND, and OUT to GPIO 5. In the IR remote tab,
click Add code for an action and press the remote button. Up to 32 codes are
saved on the board; several codes can share an action. The live log shows
protocols, codes, repeats, matches, and raw timings without a serial console.
The same tab shows reset reason and memory readings. Use Set 1% brightness to
lower an existing saved brightness setting without resetting the device.

If the browser cannot stay connected, run `pio device monitor -b 115200`
on the application USB port and send `?` (no Enter required). It prints only
reset reason, uptime and heap sizes. Reset codes: 4 = software crash,
5 = interrupt watchdog, 6 = task watchdog, 7 = other watchdog, 9 = brownout,
1 = power on, 3 = software restart. Check after an unexpected reset;
the uploader itself can cause a watchdog restart. Close the monitor before uploading.

After changing the UI, run `npm ci --legacy-peer-deps` and `npm run build` in
`web/`, then `python3 tools/package_web.py` from the repository root. Build and
upload both firmware and filesystem for the IR feature; no erase is needed.
