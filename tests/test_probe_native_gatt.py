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
        self.assertEqual(c.sizeof(module.Descriptor), 32)
        self.assertEqual(module.Descriptor.uuid.offset, 8)
        self.assertEqual(module.Descriptor.handle.offset, 28)
        self.assertEqual(c.sizeof(module.CharacteristicFormat), 48)
        self.assertEqual(module.DescriptorValue.data_size.offset, 72)
        self.assertEqual(module.DescriptorValue.data.offset, 76)
        self.assertEqual(c.sizeof(module.DescriptorValue), 80)

    def test_report_reference_requires_valid_uuid_size_and_type(self):
        value = module.DescriptorValue()
        value.kind = 6
        value.uuid.is_short = 1
        value.uuid.value.short = 0x2908
        value.data_size = 2
        raw = bytes(value)[:76] + bytes([3, 1])
        self.assertEqual(module.parse_report_reference(raw), (3, 1))
        for invalid in (raw[:77], raw[:77] + b'\x04', b'\x00' * 78,
                        raw[:72] + b'\xff\xff\xff\xff' + raw[76:]):
            with self.subTest(raw=invalid), self.assertRaises(ValueError):
                module.parse_report_reference(invalid)

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

    def test_denied_reference_read_does_not_fetch_a_buffer(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        api = SimpleNamespace(BluetoothGATTGetDescriptors=Mock(),
                              BluetoothGATTGetDescriptorValue=Mock(return_value=-2147024891))
        char = module.Characteristic()
        char.uuid.is_short, char.uuid.value.short = 1, 0x2a4d
        descriptor = module.Descriptor()
        descriptor.uuid.is_short, descriptor.uuid.value.short = 1, 0x2908
        with patch.object(module, 'query_array', return_value=[descriptor]):
            self.assertEqual(module.read_report_references(api, None, [char], lambda _: None), [])
        api.BluetoothGATTGetDescriptorValue.assert_called_once()
