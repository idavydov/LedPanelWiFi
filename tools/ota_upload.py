"""Upload over OTA; cache successful passwords in the desktop keyring by default."""
import argparse
import getpass
import importlib.util
import os
from pathlib import Path
import random
import subprocess
import sys
import socket
import time


ROOT = Path(__file__).resolve().parents[1]
KEYRING_SERVICE = 'LedPanelWiFi.OTA'
SYSTEM_PYTHON = Path('/usr/bin/python3')


def cache_key(host):
    return 'admin@' + host.strip().rstrip('.').lower() + ':3232'


def password_store():
    """Choose a native OS keyring; never fall back to a plaintext file backend."""
    try:
        import keyring.backend
        native = ('keyring.backends.SecretService', 'keyring.backends.kwallet',
                  'keyring.backends.macOS', 'keyring.backends.Windows', 'keyring.backends.libsecret')
        backends = [backend for backend in keyring.backend.get_all_keyring()
                    if type(backend).__module__.startswith(native) and backend.priority > 0]
        return max(backends, key=lambda backend: backend.priority) if backends else None
    except Exception:
        return None


def try_system_python(argv):
    """Venvs/uv may lack desktop bindings already installed for system Python."""
    if not SYSTEM_PYTHON.is_file() or os.path.abspath(sys.executable) == str(SYSTEM_PYTHON):
        return
    script = str(Path(__file__).resolve())
    try:
        # Probe backend availability only; never retrieve a cached credential.
        result = subprocess.run([str(SYSTEM_PYTHON), script, '--keyring-probe'],
                                capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return
    if result.returncode == 0:
        print('Using system Python for desktop keyring support.', flush=True)
        os.execv(str(SYSTEM_PYTHON), [str(SYSTEM_PYTHON), script, *argv])


def forget_password(store, host):
    if store.get_password(KEYRING_SERVICE, cache_key(host)) is None:
        return False
    store.delete_password(KEYRING_SERVICE, cache_key(host))
    return True


def upload_with_cache(espota, host, image, filesystem=False, local_address='0.0.0.0',
                      store=None, prompt=None, filesystem_image=None):
    password = None
    if store is not None:
        try:
            password = store.get_password(KEYRING_SERVICE, cache_key(host))
        except Exception:
            print('Password cache is unavailable; prompting instead.', file=sys.stderr)
            store = None
    if password is None:
        if prompt is None:
            if not sys.stdin.isatty():
                raise RuntimeError('No cached password. Run from an interactive terminal to enter it without echo.')
            prompt = getpass.getpass
        password = prompt('Panel administrator / OTA password: ')
    else:
        print('Using the cached OTA password.')
    result = upload(espota, host, image, password, filesystem, local_address)
    if result == 0 and store is not None:
        try:
            store.set_password(KEYRING_SERVICE, cache_key(host), password)
        except Exception:
            print('Upload succeeded, but the password could not be cached.', file=sys.stderr)
    if result != 0 or filesystem_image is None:
        return result
    print('Firmware uploaded. Waiting for the panel to restart…', flush=True)
    try:
        wait_for_restart(host)
    except TimeoutError:
        print('Firmware uploaded, but the panel did not become ready. Filesystem was not uploaded.', file=sys.stderr)
        return 1
    print('Panel is back. Uploading filesystem…', flush=True)
    result = upload(espota, host, filesystem_image, password, True, local_address)
    if result == 0:
        print('Firmware and filesystem uploaded. Reload the web UI after the panel restarts.')
    else:
        print('Firmware uploaded; filesystem upload failed. Retry with --filesystem.', file=sys.stderr)
    return result


def wait_for_restart(host, timeout=180):
    """Wait for startup without requesting pages, settings, or credentials."""
    deadline = time.monotonic() + timeout
    time.sleep(5)  # Do not mistake the old application's final ACK for readiness.
    consecutive = 0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, 80), timeout=2):
                pass
            consecutive += 1
            if consecutive >= 2:
                return
        except OSError:
            consecutive = 0
        time.sleep(1)
    raise TimeoutError('Panel restart timed out')


def upload(espota, host, image, password, filesystem=False, local_address='0.0.0.0'):
    # Call the installed uploader in-process: the password never enters shell
    # history, command-line arguments, environment variables, or a config file.
    espota.TIMEOUT = 10
    espota.PROGRESS = True
    return espota.serve(host, local_address, 3232,
                        random.SystemRandom().randint(10000, 60000), password,
                        str(image), espota.SPIFFS if filesystem else espota.FLASH)


def main():
    if sys.argv[1:] == ['--keyring-probe']:
        return 0 if password_store() is not None else 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='Panel IP address or hostname, e.g. GlassPanel.local')
    images = parser.add_mutually_exclusive_group()
    images.add_argument('--filesystem', action='store_true', help='Upload LittleFS instead of firmware.')
    images.add_argument('--both', action='store_true', help='Upload firmware, wait for restart, then upload LittleFS.')
    parser.add_argument('--local-address', default='0.0.0.0', help='Local network interface for the OTA callback.')
    caching = parser.add_mutually_exclusive_group()
    caching.add_argument('--no-cache', action='store_true', help='Prompt without reading or writing the password cache.')
    caching.add_argument('--forget', action='store_true', help='Remove this host\'s cached password and exit.')
    args = parser.parse_args()
    store = None if args.no_cache else password_store()
    if store is None and not args.no_cache:
        try_system_python(sys.argv[1:])
    if args.forget:
        if store is None:
            parser.error('Desktop keyring unavailable. Run /usr/bin/python3 tools/ota_upload.py HOST --forget '
                         'from your normal desktop terminal; sandboxed terminals may block D-Bus.')
        try:
            removed = forget_password(store, args.host)
        except Exception:
            parser.error('Could not access the desktop keyring to forget this password.')
        print('Cached password removed.' if removed else 'No cached password for this host.')
        return 0
    if store is None and not args.no_cache:
        print('Desktop keyring unavailable; password will not be cached. '
              'Run from a normal desktop terminal with D-Bus access, or use --no-cache.', file=sys.stderr)
    image = ROOT / '.pio/build/esp32_s2_mini' / ('littlefs.bin' if args.filesystem else 'firmware.bin')
    filesystem_image = image.with_name('littlefs.bin') if args.both else None
    for required in ([image, filesystem_image] if args.both else [image]):
        if not required.is_file():
            parser.error(f'Missing {required.name}; build it with PlatformIO first.')
    core = Path(os.environ.get('PLATFORMIO_CORE_DIR', Path.home() / '.platformio'))
    tool = core / 'packages/framework-arduinoespressif32/tools/espota.py'
    if not tool.is_file():
        parser.error('Arduino ESP32 OTA tool missing; build the S2 Mini environment first.')
    spec = importlib.util.spec_from_file_location('espota', tool)
    espota = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(espota)
    try:
        return upload_with_cache(espota, args.host, image, args.filesystem, args.local_address,
                                 store, filesystem_image=filesystem_image)
    except RuntimeError as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
