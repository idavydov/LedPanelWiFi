#pragma once

// Temporary 20 x 10 row-major canvas on A. A/B each transmit 200 fixed slots.
// Keep slots for removed factory-addressed LEDs; never compact the output.
// FastLED RGB is the equivalent of NeoPixel NEO_RGB. WS2812B uses 800 kHz.
// Use USB CDC on the S2 Mini; LED data outputs are GPIO 3 (A) and 9 (B).

#undef HOST_NAME
#define HOST_NAME F("GlassPanel")

#undef LANG
#define LANG 'ENG'

#undef WIDTH
#define WIDTH 20

#undef HEIGHT
#define HEIGHT 10

#undef MATRIX_TYPE
#define MATRIX_TYPE 1

#undef MATRIX_INDEX
#define MATRIX_INDEX 1

#undef CONNECTION_ANGLE
#define CONNECTION_ANGLE 0

#undef STRIP_DIRECTION
#define STRIP_DIRECTION 0

#undef META_MATRIX_WIDTH
#define META_MATRIX_WIDTH 1

#undef META_MATRIX_HEIGHT
#define META_MATRIX_HEIGHT 1

#undef META_MATRIX_TYPE
#define META_MATRIX_TYPE 1

#undef META_MATRIX_ANGLE
#define META_MATRIX_ANGLE 0

#undef META_MATRIX_DIRECTION
#define META_MATRIX_DIRECTION 0

#undef COLOR_ORDER
#define COLOR_ORDER RGB

#undef LED_CHIP
#define LED_CHIP WS2812B

#undef LED_PIN
#define LED_PIN 3
#define LED_PIN_B 9

#undef DEVICE_TYPE
#define DEVICE_TYPE 1

#undef BUTTON_TYPE
#define BUTTON_TYPE 1

#undef USE_BUTTON
#define USE_BUTTON 0

#undef USE_OTA
#define USE_OTA 1

#undef USE_ANIMATION
#define USE_ANIMATION 0

#undef USE_POWER
#define USE_POWER 0

#undef USE_ALARM
#define USE_ALARM 0

#undef USE_AUX
#define USE_AUX 0

#undef USE_TM1637
#define USE_TM1637 0

#undef USE_WEATHER
#define USE_WEATHER 0

#undef USE_E131
#define USE_E131 0

#undef USE_SD
#define USE_SD 0

#undef FS_AS_SD
#define FS_AS_SD 0

#undef USE_MP3
#define USE_MP3 0

#undef DEBUG_SERIAL
#define DEBUG_SERIAL 0

#undef BRIGHTNESS
#define BRIGHTNESS 3

#undef DEFAULT_IP
#define DEFAULT_IP {0, 0, 0, 0}

#undef NETWORK_SSID
#define NETWORK_SSID PSTR("")

#undef NETWORK_PASS
#define NETWORK_PASS PSTR("")

#define PANEL_DEVICE_CREDENTIALS 1
#define DEFAULT_AP_PASS PSTR("")
#define IR_RECEIVE_PIN 5

static_assert(WIDTH * HEIGHT == 200, "Keep the starter canvas at 20x10; physical outputs are independent.");
