"""Upload an S2 Mini firmware or LittleFS image with an interactive password."""
import argparse
import getpass
import importlib.util
import os
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[1]


def upload(espota, host, image, password, filesystem=False, local_address='0.0.0.0'):
    # Call the installed uploader in-process: the password never enters shell
    # history, command-line arguments, environment variables, or a config file.
    espota.TIMEOUT = 10
    espota.PROGRESS = True
    return espota.serve(host, local_address, 3232,
                        random.SystemRandom().randint(10000, 60000), password,
                        str(image), espota.SPIFFS if filesystem else espota.FLASH)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Panel IP address or hostname, e.g. GlassPanel.local')
    parser.add_argument('--filesystem', action='store_true', help='Upload LittleFS instead of firmware.')
    parser.add_argument('--local-address', default='0.0.0.0', help='Local network interface for the OTA callback.')
    args = parser.parse_args()
    image = ROOT / '.pio/build/esp32_s2_mini' / ('littlefs.bin' if args.filesystem else 'firmware.bin')
    if not image.is_file():
        parser.error(f'Missing {image.name}; build it with PlatformIO first.')
    core = Path(os.environ.get('PLATFORMIO_CORE_DIR', Path.home() / '.platformio'))
    tool = core / 'packages/framework-arduinoespressif32/tools/espota.py'
    if not tool.is_file():
        parser.error('Arduino ESP32 OTA tool missing; build the S2 Mini environment first.')
    if not sys.stdin.isatty():
        parser.error('Run from an interactive terminal so the password can be entered without echo.')
    spec = importlib.util.spec_from_file_location('espota', tool)
    espota = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(espota)
    password = getpass.getpass('Panel administrator / OTA password: ')
    return upload(espota, args.host, image, password, args.filesystem, args.local_address)


if __name__ == '__main__':
    sys.exit(main())
