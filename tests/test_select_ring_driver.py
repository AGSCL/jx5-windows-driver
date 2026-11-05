import ctypes as c
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from select_ring_driver import DeviceInfo, DriverInfo, DriverDetail, validate_instance


class SelectionTests(unittest.TestCase):
    def test_x64_windows_layout(self):
        self.assertEqual(c.sizeof(DeviceInfo), 32)
        self.assertEqual(c.sizeof(DriverInfo), 1568)
        self.assertEqual(c.sizeof(DriverDetail), 1584)

    def test_rejects_another_service_or_ring(self):
        instance = ('BTHLEDEVICE\\{00001812-0000-1000-8000-00805F9B34FB}'
                    '_DEV_VID&0105AC_PID&0220_REV&0110_B7FC01C6F37E\\A&49E30AC&19&0023')
        validate_instance(instance)
        for invalid in (instance.replace('1812', '1800'),
                        instance.replace('B7FC01C6F37E', '111111111111'), 'USB\\OTHER'):
            with self.assertRaises(ValueError):
                validate_instance(invalid)
