import importlib.util
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('make_index_map', ROOT / 'tools/make_index_map.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class IndexMapTests(unittest.TestCase):
    def test_starter_matches_firmware_binary_format_and_parallel_coordinates(self):
        data = (ROOT / 'firmware/LedPanelWiFi_v1.14/data/20x10.map').read_bytes()
        self.assertEqual(data[:4], b'\xa5\xa5\x14\x0a')
        self.assertEqual(len(data), 404)
        indices = struct.unpack('<200h', data[4:])
        self.assertEqual(sorted(indices), list(range(200)))
        for y in range(10):
            for x in range(20):
                self.assertEqual(indices[x + (9 - y) * 20], y * 20 + x)

    def test_custom_map_keeps_fixed_addresses_and_empty_cells(self):
        rows = [[-1] * 20 for _ in range(10)]
        rows[0][0], rows[9][19] = 199, 0
        data = generator.encode_map(rows)
        indices = struct.unpack('<200h', data[4:])
        self.assertEqual(indices[0], 199)
        self.assertEqual(indices[-1], 0)
        self.assertEqual(indices[1], -1)

    def test_reject_invalid_dimensions_addresses_and_duplicates(self):
        for rows in ([[0]], [[200] * 20 for _ in range(10)],
                     [[-2] * 20 for _ in range(10)], [[0] * 20 for _ in range(10)]):
            with self.assertRaises(ValueError):
                generator.encode_map(rows)
