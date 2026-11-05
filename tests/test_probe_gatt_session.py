import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

spec = importlib.util.spec_from_file_location(
    "probe_gatt_session", Path(__file__).resolve().parents[1] / "tools/probe_gatt_session.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Session:
    session_status = 0
    maintain_connection = False

    def add_session_status_changed(self, callback):
        self.callback = callback
        return 1

    def remove_session_status_changed(self, token):
        self.callback = None

    def change(self, status):
        self.session_status = status
        self.callback(self, SimpleNamespace(error=0))


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hid_access_denied_closes_service_without_enumerating(self):
        service = SimpleNamespace(
            request_access_async=AsyncMock(return_value=SimpleNamespace(name="DENIED_BY_SYSTEM")),
            get_characteristics_async=AsyncMock(), close=Mock())
        result = SimpleNamespace(status=SimpleNamespace(name="SUCCESS"),
                                 protocol_error=None, services=[service])
        device = SimpleNamespace(get_gatt_services_for_uuid_async=AsyncMock(return_value=result))
        messages = []
        code = await module.check_hid_access(device, 0, messages.append)
        self.assertEqual(code, 3)
        self.assertIn("ACCESO_HID: DENIED_BY_SYSTEM", messages)
        service.get_characteristics_async.assert_not_called()
        service.close.assert_called_once()

    async def test_hid_check_result_is_preserved_and_session_released(self):
        session = Session()
        session.session_status = 1
        check = AsyncMock(return_value=3)
        code = await module.monitor(session, on_active=check, emit=lambda _: None)
        self.assertEqual(code, 3)
        check.assert_awaited_once()
        self.assertFalse(session.maintain_connection)

    async def test_requested_connection_is_not_success(self):
        session = Session()
        code = await module.monitor(session, connect_timeout=0.01, emit=lambda _: None)
        self.assertEqual(code, 4)
        self.assertFalse(session.maintain_connection)

    async def test_active_session_is_measured_and_released(self):
        session = Session()
        session.session_status = 1
        code = await module.monitor(session, seconds=0.01, emit=lambda _: None)
        self.assertEqual(code, 0)
        self.assertFalse(session.maintain_connection)
        self.assertIsNone(session.callback)

    async def test_drop_during_measurement_is_failure(self):
        session = Session()
        session.session_status = 1
        asyncio.get_running_loop().call_later(0.01, session.change, 0)
        messages = []
        code = await module.monitor(session, seconds=1, emit=messages.append)
        self.assertEqual(code, 4)
        self.assertTrue(any("SESION_PERDIDA" in message for message in messages))
        self.assertFalse(session.maintain_connection)
