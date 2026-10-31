# ESP32-S2 Mini first flash

The `esp32_s2_mini` environment targets a LOLIN/WEMOS S2 Mini with 4 MiB flash.
It uses GPIO 3, WS2812-compatible 800 kHz output, and FastLED `RGB` (NeoPixel
`NEO_RGB`). The temporary canvas is 20 × 10, parallel rows from the bottom left:
`slot = y * 20 + x + 1`. It transmits all 200 slots, including any missing
factory-addressed LEDs. The final slot is index 199 at `(19, 9)`.

Optional peripherals, weather requests, and E1.31 are disabled. Brightness
starts at 16/255. OTA remains enabled with administrator authentication.

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

This profile uses manual ROM bootloader entry. Close any serial monitor, hold
BOOT, tap and release RESET, then release BOOT. Identify the port after this
sequence; it can differ from the running firmware's port. Substitute it below:

```sh
pio run -e esp32_s2_mini -t upload --upload-port /dev/ttyACM0
pio run -e esp32_s2_mini -t uploadfs --upload-port /dev/ttyACM0
```

The uploader leaves the board in download mode, so firmware and filesystem can
be uploaded consecutively. Tap RESET after both finish to start the application.
For a later upload, repeat BOOT + RESET first.

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
