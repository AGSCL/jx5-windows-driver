from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from monitor_jx05 import needs_generic


class MonitorTests(unittest.TestCase):
    def test_only_original_driver_on_exact_ring_is_replaced_once(self):
        instance = ('BTHLEDEVICE\\{00001812-0000-1000-8000-00805F9B34FB}'
                    '_DEV_VID&0105AC_PID&0220_REV&0110_B7FC01C6F37E\\A&49E30AC&1D&0023')
        device = {'instance': instance, 'driver': 'hidbthle.inf'}
        self.assertTrue(needs_generic(device, set()))
        self.assertFalse(needs_generic(device, {instance.lower()}))
        self.assertFalse(needs_generic(dict(device, driver='bthleenum.inf'), set()))
        self.assertFalse(needs_generic(dict(device, driver='unknown.inf'), set()))
        with self.assertRaises(ValueError):
            needs_generic(dict(device, instance=instance.replace('1812', '1800')), set())
