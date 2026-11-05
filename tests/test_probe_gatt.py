import importlib.util
from pathlib import Path
from types import SimpleNamespace as Item
import unittest

spec = importlib.util.spec_from_file_location(
    "probe_gatt", Path(__file__).resolve().parents[1] / "tools" / "probe_gatt.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Scanner:
    @staticmethod
    async def discover(**kwargs):
        return {"ring": (Item(name="JX-05", address="ring"), Item(local_name="JX-05"))}


class Client:
    def __init__(self, services, notify):
        self.services = services
        self.notify = notify
        self.is_connected = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.is_connected = False

    async def start_notify(self, characteristic, callback):
        self.notify(characteristic, callback)


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def run_probe(self, services, notify):
        messages = []
        code = await module.probe(Scanner, lambda *a, **kw: Client(services, notify),
                                  listen_seconds=0.001, emit=messages.append)
        return code, messages

    async def test_hidden_hid_is_not_success(self):
        code, messages = await self.run_probe([], lambda *a: None)
        self.assertEqual(code, 3)
        self.assertTrue(any("HID_NO_VISIBLE" in m for m in messages))

    async def test_subscription_without_data_is_not_success(self):
        char = Item(uuid=module.REPORT, properties=["notify"], handle=39)
        code, _ = await self.run_probe([Item(uuid=module.HID_SERVICE, characteristics=[char])],
                                       lambda *a: None)
        self.assertEqual(code, 5)

    async def test_repeated_report_uuid_subscribes_by_object(self):
        chars = [Item(uuid=module.REPORT, properties=["notify"], handle=h) for h in (39, 43)]
        seen = []

        def notify(char, callback):
            self.assertIn(char, chars)
            seen.append(char.handle)
            callback(char, bytearray([1, 2]))

        code, messages = await self.run_probe(
            [Item(uuid=module.HID_SERVICE, characteristics=chars)], notify)
        self.assertEqual(code, 0)
        self.assertEqual(seen, [39, 43])
        self.assertTrue(any("informes=2" in m for m in messages))
