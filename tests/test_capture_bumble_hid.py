import asyncio
import unittest
from tools.capture_bumble_hid import relax_link, with_report_id


class BumbleReportTests(unittest.TestCase):
    def test_prefixes_report_id_like_raw_input(self):
        # Captura real: Raw Input entrega 0107f40119; Bumble entrega 07f40119 (handle 0x0027, Report Reference 01 01).
        self.assertEqual(with_report_id(bytes([1, 1]), bytes.fromhex('07f40119')).hex(), '0107f40119')
        self.assertEqual(with_report_id(bytes([3, 1]), b'\x01\x02\x03').hex(), '03010203')

    def test_ignores_non_input_or_malformed_references(self):
        for reference in (bytes([1, 2]), bytes([1, 3]), b'\x01', b'', b'\x01\x01\x00'):
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
