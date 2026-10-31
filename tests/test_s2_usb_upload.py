"""USB port selection tests; these never open or read a serial port."""
import runpy
import sys
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/s2_usb_upload.py'
select_port = runpy.run_path(str(SCRIPT))['select_bootloader_port']


def port(name, product='0002', location='1-4:1.0', serial='0'):
    return {'port': name, 'hwid': f'USB VID:PID=303A:{product} SER={serial} LOCATION={location}'}


class S2USBUploadTests(unittest.TestCase):
    def test_wait_tolerates_slow_reconnect_and_reused_name(self):
        namespace = runpy.run_path(str(SCRIPT))
        clock = SimpleNamespace(now=0)
        namespace['wait_for_s2_port'].__globals__['time'] = SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        original = port('/dev/ttyACM0', '80C2')
        def list_ports():
            if clock.now < 1:
                return [original]
            if clock.now < 8:
                return []
            return [port('/dev/ttyACM0')]
        class Environment:
            def subst(self, value): return '/dev/ttyACM0'
            def Exit(self, code): raise RuntimeError(code)
        with patch.dict(sys.modules, {'platformio.util': SimpleNamespace(get_serial_ports=list_ports)}):
            self.assertEqual(namespace['wait_for_s2_port'](Environment(), [original]), '/dev/ttyACM0')
        self.assertGreater(clock.now, 8)

    def test_same_device_node_after_reboot(self):
        original = port('/dev/ttyACM0', '80C2')
        self.assertEqual(select_port(original, [port('/dev/ttyACM0')]), '/dev/ttyACM0')

    def test_follows_changed_node_using_physical_usb_location(self):
        original = port('/dev/ttyACM0', '80C2')
        self.assertEqual(select_port(original, [port('/dev/ttyACM1', location='1-4:1.1')]), '/dev/ttyACM1')

    def test_does_not_pick_another_board_or_running_application(self):
        original = port('/dev/ttyACM0', '80C2')
        self.assertIsNone(select_port(original, [original, port('/dev/ttyACM1', location='1-5:1.0')]))
        self.assertIsNone(select_port(original, []))
        self.assertIsNone(select_port(original, [port('/dev/ttyACM0', location='1-5:1.0')]))

    def test_ambiguous_or_unidentified_replacement_is_rejected(self):
        self.assertIsNone(select_port(port('/dev/ttyACM0'), [port('/dev/ttyACM1'), port('/dev/ttyACM2')]))
        self.assertIsNone(select_port({'port': '/dev/ttyACM0'}, [port('/dev/ttyACM1')]))

    def test_explicit_rom_port_is_accepted_without_metadata(self):
        self.assertEqual(select_port({'port': '/dev/ttyACM0'}, [port('/dev/ttyACM0')]), '/dev/ttyACM0')

    def test_installs_platformio_wait_hook(self):
        class Environment:
            def AddMethod(self, method, name):
                self.method = method
                self.name = name
        env = Environment()
        runpy.run_path(str(SCRIPT), init_globals={'Import': lambda name: None, 'env': env})
        self.assertEqual(env.name, 'WaitForNewSerialPort')
        self.assertEqual(env.method.__name__, 'wait_for_s2_port')
