import struct
import unittest
from tools.capture_raw_hid import reports


class RawReportsTests(unittest.TestCase):
    def test_batch_and_boundaries(self):
        packet = struct.pack('<II', 5, 2) + b'12345abcde'
        self.assertEqual(reports(packet), [b'12345', b'abcde'])
        for length in range(len(packet)):
            with self.assertRaises(ValueError):
                reports(packet[:length])
        for size, count in [(0, 2), (5, 0), (0xffffffff, 0xffffffff)]:
            with self.assertRaises(ValueError):
                reports(struct.pack('<II', size, count))
