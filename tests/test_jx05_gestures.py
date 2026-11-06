from datetime import datetime
import json
from pathlib import Path
import unittest
from tools.jx05_gestures import Gestures
from tools.map_jx05 import DEFAULTS

CASES = json.loads((Path(__file__).parent / 'fixtures/jx05_buttons.json').read_text())


class GestureTests(unittest.TestCase):
    def test_hold_duration_ignores_internal_releases_and_resets(self):
        for value in (1, 2):
            d = Gestures()
            for now in (0, .75, 1.5, 2.25, 3):
                self.assertIsNotNone(d.feed(bytes([3,value,0,0,0]), now))
                self.assertEqual(d.held_seconds, now)
                self.assertIsNone(d.feed(bytes([3,value,0,0,0]), now + .01))
                self.assertIsNone(d.feed(bytes([3,0,0,0,0]), now + .02))
            d.feed(bytes([3,value,0,0,0]), 5)
            self.assertEqual(d.held_seconds, 0)
            d.feed(bytes([3,0,0,0,0]), 5.02)
            d.feed(bytes([3,3-value,0,0,0]), 5.5)
            self.assertEqual(d.held_seconds, 0)
            d.feed(bytes.fromhex('0100f4e115'), 5.6)
            self.assertIsNone(d.repeat_start)

    def test_real_short_and_held_presses_with_duplicates(self):
        for case in CASES:
            for copies in (1, 3):
                with self.subTest(case=case['name'], copies=copies):
                    decoder, actions = Gestures(), []
                    for row in case['reports']:
                        for _ in range(copies):
                            result = decoder.feed(bytes.fromhex(row['hex']), datetime.fromisoformat(row['time']).timestamp())
                            if result:
                                self.assertEqual(result, case['name'].split('_')[0])
                                actions.append(DEFAULTS[result])
                    self.assertEqual(actions, [case['expected_action']] * case['expected_count'])

    def test_disconnect_timeout_and_partial_gesture(self):
        rows = CASES[0]['reports']
        for cutoff in range(1, len(rows)):
            decoder = Gestures()
            for row in rows[:cutoff]:
                decoder.feed(bytes.fromhex(row['hex']), 0)
            decoder.reset()
            self.assertTrue(all(decoder.feed(bytes.fromhex(row['hex']), .1) is None for row in rows[cutoff:]))
        decoder = Gestures()
        for row in rows[:-1]: decoder.feed(bytes.fromhex(row['hex']), 0)
        self.assertIsNone(decoder.feed(bytes.fromhex(rows[-1]['hex']), 2))

    def test_other_controls_and_release_do_not_move(self):
        decoder = Gestures()
        for data in [b'', b'\x03\x00\x00\x00', b'\x03\x04\x00\x00', b'\x01\x00\xf4\xe1\x15']:
            self.assertIsNone(decoder.feed(data, 0))

    def test_center_requires_complete_short_tap(self):
        press, release = bytes.fromhex('0107f40119'), bytes.fromhex('0100f40119')
        d = Gestures()
        self.assertIsNone(d.feed(release, 0))
        self.assertIsNone(d.feed(press, .1))
        self.assertIsNone(d.feed(press, .2))
        self.assertEqual(d.feed(release, .3), 'center')
        self.assertIsNone(d.feed(release, .4))
        d.feed(press, .5)
        self.assertIsNone(d.feed(release, 2))
        d.feed(press, 3)
        d.reset()
        self.assertIsNone(d.feed(release, 3.1))

    def test_consumer_padding_is_not_part_of_report(self):
        for padding in range(256):
            d = Gestures()
            self.assertEqual(d.feed(bytes([3, 1, 0, 0, padding]), 0), 'lower')
            self.assertIsNone(d.feed(bytes([3, 1, 0, 0, 255 - padding]), .1))
            self.assertIsNone(d.feed(bytes([3, 0, 0, 0, padding]), .2))
            self.assertEqual(d.feed(bytes([3, 2, 0, 0, padding]), .3), 'upper')
