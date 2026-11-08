import asyncio
import unittest
from tools.capture_bumble_hid import NoInputReports, _session, relax_link, with_report_id

try:
    from bumble.core import CommandTimeoutError
    from bumble.transport.common import TransportLostError
except ImportError:  # bumble solo esta en .jx05-monitor/venv-bumble
    CommandTimeoutError = None


def run_session(error):
    """Ejecuta _session con un connect que siempre falla; para tras el primer 'retry'."""
    events = []

    class Device:
        async def connect(self, *args, **kwargs):
            raise error

    async def main():
        stop = asyncio.Event()

        def on_event(event, **fields):
            events.append((event, fields.get('detail')))
            stop.set()

        await _session(Device(), on_event, stop, retry=0)

    asyncio.run(main())
    return events


@unittest.skipIf(CommandTimeoutError is None, 'requiere bumble')
class BumbleSessionTests(unittest.TestCase):
    def test_retries_recoverable_link_errors(self):
        for error in (CommandTimeoutError(), NoInputReports(), asyncio.TimeoutError()):
            self.assertEqual(run_session(error), [('retry', type(error).__name__)])

    def test_missing_dongle_retries_and_can_stop(self):
        from unittest import mock
        from tools import capture_bumble_hid
        events = []

        async def no_dongle(name):
            raise OSError('UB500 no encontrado')

        def on_event(event, **fields):
            events.append((event, fields.get('failed')))

        with mock.patch('bumble.transport.open_transport', no_dongle):
            result = capture_bumble_hid.run(on_event=on_event, stopped=lambda: ('retry', None) in events)
        self.assertEqual(result, 0)
        self.assertIn(('device_change', None), events)
        self.assertIn(('retry', None), events)
        self.assertEqual(events[-1], ('stopped', False))

    def test_lost_transport_is_reopened(self):
        from unittest import mock
        from tools import capture_bumble_hid
        events, attempts = [], []

        class Transport:
            async def __aenter__(self):
                source = mock.Mock()
                source.terminated = asyncio.get_running_loop().create_future()
                return source, mock.Mock()
            async def __aexit__(self, *args):
                pass

        async def open_transport(name):
            attempts.append(name)
            if len(attempts) == 1:
                raise TransportLostError()
            return Transport()

        async def session(device, on_event, stop):
            stop.set()

        async def timeout(awaitable, timeout):
            awaitable.close()
            raise asyncio.TimeoutError

        device = mock.Mock()
        device.power_on = mock.AsyncMock()
        with mock.patch('bumble.transport.open_transport', open_transport), \
             mock.patch('bumble.device.Device.with_hci', return_value=device), \
             mock.patch.object(capture_bumble_hid, '_session', session), \
             mock.patch.object(capture_bumble_hid.asyncio, 'wait_for', new=timeout):
            result = capture_bumble_hid.run(on_event=lambda event, **fields: events.append(event))
        self.assertEqual(result, 0)
        self.assertEqual(len(attempts), 2)
        self.assertIn('retry', events)

    def test_cancellation_and_lost_transport_are_not_swallowed(self):
        for error in (asyncio.CancelledError(), TransportLostError()):
            with self.assertRaises(type(error)):
                run_session(error)


class BumbleReportTests(unittest.TestCase):
    def test_prefixes_report_id_like_raw_input(self):
        # Captura real: Raw Input entrega 0107f40119; Bumble entrega 07f40119 (handle 0x0027, Report Reference 01 01).
        self.assertEqual(with_report_id(bytes([1, 1]), bytes.fromhex('07f40119')).hex(), '0107f40119')
        self.assertEqual(with_report_id(bytes([3, 1]), b'\x01\x02\x03').hex(), '03010203')

    def test_ignores_non_input_or_malformed_references(self):
        for reference in (bytes([1, 2]), bytes([1, 3]), b'\x01', b'', b'\x01\x01\x00',
                          bytes([2, 1]), bytes([4, 1]), bytes([5, 1]), bytes([6, 1])):
            self.assertIsNone(with_report_id(reference, b'\x00'))

    def test_relax_link_requests_slow_parameters_and_tolerates_rejection(self):
        events, calls = [], []

        class Conn:
            def __init__(self, fail): self.fail = fail
            async def update_parameters(self, *args):
                calls.append(args)
                if self.fail: raise RuntimeError('rechazado')

        emit = lambda event, **f: events.append((event, f.get('mode')))
        asyncio.run(relax_link(Conn(False), emit))
        asyncio.run(relax_link(Conn(True), emit))
        self.assertEqual(calls, [(30, 60, 4, 2000)] * 2)
        self.assertEqual(events, [('link_mode', 'relaxed'), ('link_mode_unavailable', None)])


if __name__ == '__main__':
    unittest.main()
