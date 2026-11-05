import ctypes as c
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "probe_native_gatt", Path(__file__).resolve().parents[1] / "tools/probe_native_gatt.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeTests(unittest.TestCase):
    def test_windows_abi_layout(self):
        self.assertEqual(c.sizeof(module.Guid), 16)
        self.assertEqual(c.sizeof(module.LeUuid), 20)
        self.assertEqual(c.sizeof(module.Service), 24)
        self.assertEqual(module.Characteristic.uuid.offset, 4)
        self.assertEqual(c.sizeof(module.Characteristic), 36)
        self.assertEqual(module.Registration.chars.offset, 4)
        self.assertEqual(c.sizeof(module.Registration), 40)

    def test_registration_rejection_does_not_unregister(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        api = SimpleNamespace(BluetoothGATTRegisterEvent=Mock(return_value=-2147024809),
                              BluetoothGATTUnregisterEvent=Mock())
        char = module.Characteristic()
        char.uuid.is_short = 1
        char.uuid.value.short = 0x2a4d
        char.notify = 1
        self.assertEqual(module.try_register(api, None, [char], lambda _: None), 0)
        api.BluetoothGATTUnregisterEvent.assert_not_called()

    def test_denied_query_does_not_fetch(self):
        calls = []
        def denied(*args):
            calls.append(args)
            return -2147024891
        self.assertIsNone(module.query_array(denied, (None,), module.Service, lambda _: None, "TEST"))
        self.assertEqual(len(calls), 1)
