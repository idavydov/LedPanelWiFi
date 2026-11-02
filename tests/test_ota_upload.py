import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ota_upload', ROOT / 'tools/ota_upload.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class OTAUploadTests(unittest.TestCase):
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
