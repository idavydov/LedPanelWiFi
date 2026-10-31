"""Follow the selected S2 Mini's native USB port after its 1200-baud reboot."""
import re
import time


def usb_field(port, field):
    match = re.search(r'\b' + field + r'=([^\s]+)', port.get('hwid', ''), re.I)
    return match.group(1).lower() if match else ''


def select_bootloader_port(original, ports):
    location = usb_field(original, 'LOCATION').split(':')[0]
    serial = usb_field(original, 'SER')
    if serial in ('0', '00000000', 'n/a'):
        serial = ''
    matches = []
    for port in ports:
        if usb_field(port, 'VID:PID') != '303a:0002':
            continue
        if location:
            same_board = usb_field(port, 'LOCATION').split(':')[0] == location
        elif serial:
            same_board = usb_field(port, 'SER') == serial
        else:
            same_board = port['port'] == original['port']
        if same_board:
            matches.append(port['port'])
    return matches[0] if len(matches) == 1 else None


def wait_for_s2_port(env, before):
    from platformio.util import get_serial_ports

    selected = env.subst('$UPLOAD_PORT')
    original = next((port for port in before if port['port'] == selected), {'port': selected})
    print('Waiting for this ESP32-S2 bootloader USB port (up to 15 seconds)...')
    deadline = time.monotonic() + 15
    previous = None
    while time.monotonic() < deadline:
        candidate = select_bootloader_port(original, get_serial_ports())
        # Two observations allow the device node to settle, including same-name reconnects.
        if candidate and candidate == previous:
            print('Using bootloader port:', candidate)
            return candidate
        previous = candidate
        time.sleep(0.25)
    print('USB bootloader did not appear. Close serial monitors and retry; '
          'use BOOT + RESET only if the firmware is unresponsive.')
    env.Exit(1)


try:
    Import('env')
except NameError:
    pass  # Importable for host tests without SCons.
else:
    env.AddMethod(wait_for_s2_port, 'WaitForNewSerialPort')
