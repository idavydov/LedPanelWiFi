import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch
from contextlib import redirect_stdout, redirect_stderr
import io
import tempfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ota_upload', ROOT / 'tools/ota_upload.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class OTAUploadTests(unittest.TestCase):
    def test_both_uploads_in_order_after_restart_with_one_password_lookup(self):
        uploader = Mock(FLASH=0, SPIFFS=100)
        sequence = []
        uploader.serve.side_effect = lambda *args: sequence.append(args[-1]) or 0
        store = Mock()
        store.get_password.return_value = None
        prompt = Mock(return_value='test-only-credential')
        with patch.object(helper, 'wait_for_restart', side_effect=lambda host: sequence.append('restart')) as wait, \
             redirect_stdout(io.StringIO()) as output:
            result = helper.upload_with_cache(uploader, 'panel.local', Path('firmware.bin'),
                store=store, prompt=prompt, filesystem_image=Path('littlefs.bin'))
        self.assertEqual(result, 0)
        self.assertEqual(sequence, [0, 'restart', 100])
        wait.assert_called_once_with('panel.local')
        prompt.assert_called_once()
        store.get_password.assert_called_once()
        self.assertEqual([call.args[5] for call in uploader.serve.call_args_list], ['firmware.bin', 'littlefs.bin'])
        self.assertTrue(all(call.args[4] == 'test-only-credential' for call in uploader.serve.call_args_list))
        self.assertNotIn('test-only-credential', output.getvalue())

    def test_both_stops_on_firmware_failure_or_restart_timeout(self):
        for first_result in (0, 1):
            with self.subTest(first_result=first_result):
                uploader = Mock(FLASH=0, SPIFFS=100)
                uploader.serve.return_value = first_result
                with patch.object(helper, 'wait_for_restart', side_effect=TimeoutError) as wait, \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result = helper.upload_with_cache(uploader, 'panel.local', Path('firmware.bin'),
                        prompt=lambda _: 'test-only-credential', filesystem_image=Path('littlefs.bin'))
                self.assertEqual(result, 1)
                self.assertEqual(uploader.serve.call_count, 1)
                self.assertEqual(wait.call_count, 1 if first_result == 0 else 0)

    def test_restart_wait_uses_only_tcp_connections_and_requires_stable_return(self):
        clock = [0]
        def sleep(seconds): clock[0] += seconds
        with patch.object(helper.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(helper.time, 'sleep', side_effect=sleep), \
             patch.object(helper.socket, 'create_connection', side_effect=[
                 OSError(), MagicMock(), OSError(), MagicMock(), MagicMock()]) as connect:
            helper.wait_for_restart('panel.local', timeout=20)
        self.assertEqual(connect.call_count, 5)
        self.assertEqual(clock[0], 9)
        for call in connect.call_args_list:
            self.assertEqual(call.args[0], ('panel.local', 80))
        clock[0] = 0
        with patch.object(helper.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(helper.time, 'sleep', side_effect=sleep), \
             patch.object(helper.socket, 'create_connection', side_effect=OSError()):
            with self.assertRaises(TimeoutError): helper.wait_for_restart('panel.local', timeout=8)

    def test_missing_second_image_fails_before_any_upload_or_password_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / '.pio/build/esp32_s2_mini'
            build.mkdir(parents=True)
            (build / 'firmware.bin').write_bytes(b'test')
            with patch.object(helper, 'ROOT', root), \
                 patch.object(helper.sys, 'argv', ['ota_upload.py', 'panel.local', '--both', '--no-cache']), \
                 patch.object(helper, 'upload_with_cache') as upload, \
                 redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as result: helper.main()
                self.assertEqual(result.exception.code, 2)
                self.assertIn('littlefs.bin', error.getvalue())
                upload.assert_not_called()

    def test_desktop_python_fallback_probes_only_metadata_and_keeps_password_out_of_argv(self):
        with patch.object(helper.sys, 'executable', '/test-venv/bin/python'), \
             patch.object(helper, 'SYSTEM_PYTHON', Path('/usr/bin/python3')), \
             patch.object(helper.subprocess, 'run', return_value=Mock(returncode=0)) as run, \
             patch.object(helper.os, 'execv') as execute, redirect_stdout(io.StringIO()):
            helper.try_system_python(['panel.local', '--filesystem'])
            self.assertEqual(run.call_args.args[0][-1], '--keyring-probe')
            execute.assert_called_once_with('/usr/bin/python3', [
                '/usr/bin/python3', str(ROOT / 'tools/ota_upload.py'), 'panel.local', '--filesystem'])
        with patch.object(helper.sys, 'executable', '/test-venv/bin/python'), \
             patch.object(helper.subprocess, 'run', return_value=Mock(returncode=1)), \
             patch.object(helper.os, 'execv') as execute:
            helper.try_system_python(['panel.local'])
            execute.assert_not_called()

    def test_first_success_caches_and_next_upload_reuses_without_prompt(self):
        uploader = Mock(FLASH=0, SPIFFS=100)
        uploader.serve.return_value = 0
        store = Mock()
        store.get_password.return_value = None
        prompt = Mock(return_value='test-only-credential')
        helper.upload_with_cache(uploader, 'Panel.local.', Path('test.bin'), store=store, prompt=prompt)
        store.set_password.assert_called_once_with(helper.KEYRING_SERVICE, 'admin@panel.local:3232', 'test-only-credential')
        store.get_password.return_value = 'test-only-credential'
        prompt.reset_mock()
        output = io.StringIO()
        with redirect_stdout(output):
            helper.upload_with_cache(uploader, 'panel.local', Path('test.bin'), filesystem=True, store=store, prompt=prompt)
        prompt.assert_not_called()
        self.assertNotIn('test-only-credential', output.getvalue())
        self.assertEqual(uploader.serve.call_args.args[-1], 100)

    def test_failed_upload_does_not_cache_unverified_password(self):
        uploader = Mock(FLASH=0, SPIFFS=100)
        uploader.serve.return_value = 1
        store = Mock()
        store.get_password.return_value = None
        self.assertEqual(helper.upload_with_cache(uploader, 'panel.local', Path('test.bin'),
                         store=store, prompt=lambda _: 'wrong-test-password'), 1)
        store.set_password.assert_not_called()

    def test_no_store_prompts_each_time_and_forget_is_scoped_to_host(self):
        uploader = Mock(FLASH=0, SPIFFS=100)
        uploader.serve.return_value = 0
        prompt = Mock(return_value='test-only-credential')
        helper.upload_with_cache(uploader, 'panel.local', Path('test.bin'), prompt=prompt)
        helper.upload_with_cache(uploader, 'panel.local', Path('test.bin'), prompt=prompt)
        self.assertEqual(prompt.call_count, 2)
        store = Mock()
        store.get_password.return_value = 'test-only-credential'
        self.assertTrue(helper.forget_password(store, 'Panel.local.'))
        store.delete_password.assert_called_once_with(helper.KEYRING_SERVICE, 'admin@panel.local:3232')
        self.assertNotEqual(helper.cache_key('panel.local'), helper.cache_key('192.0.2.1'))
        store.reset_mock()
        store.get_password.return_value = None
        self.assertFalse(helper.forget_password(store, 'other.local'))
        store.delete_password.assert_not_called()

    def test_unavailable_or_locked_cache_falls_back_without_printing_secret(self):
        uploader = Mock(FLASH=0, SPIFFS=100)
        uploader.serve.return_value = 0
        store = Mock()
        store.get_password.side_effect = RuntimeError('test-only-secret-in-exception')
        error = io.StringIO()
        with redirect_stderr(error):
            helper.upload_with_cache(uploader, 'panel.local', Path('test.bin'), store=store,
                                     prompt=lambda _: 'test-only-credential')
        self.assertNotIn('test-only-secret', error.getvalue())
        self.assertNotIn('test-only-credential', error.getvalue())
        store.set_password.assert_not_called()

    def test_filesystem_and_firmware_use_authenticated_in_process_uploader(self):
        for filesystem, command in ((True, 100), (False, 0)):
            with self.subTest(filesystem=filesystem):
                uploader = Mock(FLASH=0, SPIFFS=100)
                uploader.serve.return_value = 0
                result = helper.upload(uploader, 'panel.local', Path('test.bin'),
                                       'test-only-credential', filesystem)
                self.assertEqual(result, 0)
                args = uploader.serve.call_args.args
                self.assertEqual(args[:3], ('panel.local', '0.0.0.0', 3232))
                self.assertTrue(10000 <= args[3] <= 60000)
                self.assertEqual(args[4:], ('test-only-credential', 'test.bin', command))
                self.assertEqual(uploader.TIMEOUT, 10)
