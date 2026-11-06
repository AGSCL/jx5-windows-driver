import json
from pathlib import Path
import re
import unittest
from tools.analyze_att import parse_hid_items


class ReportMapTests(unittest.TestCase):
    def test_exact_original_and_vendor_report_sizes(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'driver/report_maps.h').read_text()
        arrays = [bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', body))
                  for body in re.findall(r'= \{(.*?)\};', source, re.S)]
        original, vendor = arrays
        actual = json.loads((root / 'tests/fixtures/jx05_report_map_complete.json').read_text())
        self.assertEqual(original.hex(), actual['report_map_hex'])
        captured_vendor = json.loads((root / 'tests/fixtures/jx05_report_map_vendor.json').read_text())
        self.assertEqual(vendor.hex(), captured_vendor['map_hex'])
        self.assertEqual(captured_vendor['mtu'], 23)
        self.assertEqual(len(original), 126)
        self.assertEqual(len(vendor), 126)
        self.assertEqual(vendor[:7], bytes.fromhex('0600ff0901a101'))
        self.assertEqual(parse_hid_items(vendor)['collections'], 1)
        self.assertEqual(parse_hid_items(vendor)['reports'], parse_hid_items(original)['reports'])
