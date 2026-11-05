import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace as Item
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from monitor_jx05 import capture, monitor, TARGETS


class Client:
    def __init__(self, chars, notify, disconnected):
        self.services = [Item(uuid='service', characteristics=chars)]
        self.notify = notify
        self.disconnected = disconnected
        self.is_connected = True
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True
        self.is_connected = False

    async def start_notify(self, char, callback):
        self.notify(char, callback)


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, chars, notify):
        state = {'packets': 0}
        messages = []
        ready = asyncio.Event()
        def emit(message):
            messages.append(message)
            if message.startswith(('ESCUCHANDO:', 'BLOQUEADO:')):
                ready.set()
        def factory(address, **kwargs):
            nonlocal client
            self.assertEqual(address, 'B7:FC:01:C6:F3:7E')
            self.assertFalse(kwargs['winrt']['use_cached_services'])
            client = Client(chars, notify, kwargs['disconnected_callback'])
            return client
        client = None
        task = asyncio.create_task(capture(factory, state, emit))
        try:
            await asyncio.wait_for(ready.wait(), 1)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.closed)
        return state, messages

    async def test_objects_duplicates_release_and_unrelated_service(self):
        chars = [Item(uuid=u, handle=h, properties=['notify'])
                 for h, u in enumerate(sorted(TARGETS) + [sorted(TARGETS)[0]], 10)]
        unrelated = Item(uuid='00002a4d-0000-1000-8000-00805f9b34fb', handle=42, properties=['notify'])
        seen = []
        def notify(char, callback):
            self.assertTrue(any(char is c for c in chars))
            seen.append(char.handle)
            for packet in (b'\x01', b'\x01', b'\x00'):
                callback(char, packet)
        state, messages = await self.exercise(chars + [unrelated], notify)
        self.assertEqual(seen, [10, 11, 12])
        self.assertEqual(state['packets'], 9)
        self.assertEqual(state['capture'], 'ESCUCHANDO')
        self.assertEqual(state['last_packet']['bytes'], '00')
        self.assertIn('+00:00', state['last_packet']['time'])
        self.assertEqual(len([m for m in messages if m.startswith('PAQUETE ')]), 9)

    async def test_denied_and_missing_are_not_ready(self):
        char = Item(uuid=sorted(TARGETS)[0], handle=10, properties=['notify'])
        def denied(*args):
            raise PermissionError('denied')
        for chars in ([char], [], [Item(uuid=char.uuid, handle=10, properties=['read'])]):
            state, _ = await self.exercise(chars, denied)
            self.assertEqual(state['capture'], 'BLOQUEADO')
            self.assertEqual(state['subscriptions'], [])

    async def test_partial_subscription_keeps_accessible_channel(self):
        chars = [Item(uuid=u, handle=h, properties=['notify']) for h, u in enumerate(sorted(TARGETS))]
        def notify(char, callback):
            if char.handle == 0:
                raise PermissionError('denied')
        state, _ = await self.exercise(chars, notify)
        self.assertEqual([c['handle'] for c in state['subscriptions']], [1])
        self.assertEqual(state['capture'], 'ESCUCHANDO')

    async def test_disconnect_rediscovers_objects_and_stop_closes(self):
        state = {'packets': 0}
        clients, objects, messages = [], [], []
        stop = False
        def factory(address, **kwargs):
            char = Item(uuid=sorted(TARGETS)[0], handle=10 + len(clients), properties=['notify'])
            def notify(actual, callback):
                self.assertIs(actual, char)
                objects.append(actual)
            client = Client([char], notify, kwargs['disconnected_callback'])
            clients.append(client)
            return client
        def emit(message):
            nonlocal stop
            messages.append(message)
            if message.startswith('ESCUCHANDO:'):
                if len(clients) == 1:
                    clients[-1].is_connected = False
                    clients[-1].disconnected(clients[-1])
                else:
                    stop = True
        await asyncio.wait_for(monitor(factory, state, emit, lambda: None, lambda: stop,
                                       tick=.001, retry_base=.001, retry_max=.004), 1)
        self.assertEqual(len(clients), 2)
        self.assertIsNot(objects[0], objects[1])
        self.assertTrue(all(c.closed for c in clients))
        self.assertEqual(state['subscriptions'], [])
        self.assertEqual(state['connection'], 'DISCONNECTED')

    async def test_backoff_increases_and_caps(self):
        state, waits = {'packets': 0}, []
        def factory(*args, **kwargs):
            raise OSError('offline')
        def emit(message):
            if message.startswith('REINTENTO'):
                waits.append(message)
        await asyncio.wait_for(monitor(factory, state, emit, lambda: None, lambda: len(waits) == 4,
                                       tick=.001, retry_base=.001, retry_max=.004), 1)
        self.assertEqual(waits, ['REINTENTO en 0.001 s', 'REINTENTO en 0.002 s',
                                'REINTENTO en 0.004 s', 'REINTENTO en 0.004 s'])


if __name__ == '__main__':
    unittest.main()
