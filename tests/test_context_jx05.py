import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import patch
from tools.context_jx05 import Classifier, Router, Windows, choose_action
from tools.map_jx05 import DEFAULTS


class ContextTests(unittest.TestCase):
    def test_unavailable_media_query_is_inert_but_failed_command_raises(self):
        native = Windows.__new__(Windows)
        native.dll = SimpleNamespace(JxMedia=lambda command, window: -2147023436)
        self.assertEqual(native.media(), 0)
        with self.assertRaises(RuntimeError): native.media(3, 123)

    def test_presentations_always_win_over_music(self):
        mapping = dict(DEFAULTS, center='present')
        for app in ('powerpoint', 'google', 'xaringan'):
            self.assertEqual(choose_action(app, 'left', mapping, True), 'previous')
            self.assertEqual(choose_action(app, 'upper', mapping, True), 'previous')
            self.assertEqual(choose_action(app, 'center', mapping, True), app)
        for button, action in [('left', 'track-previous'), ('right', 'track-next'),
                               ('center', 'play-pause'), ('upper', 'volume-up'), ('lower', 'volume-down')]:
            self.assertEqual(choose_action('other', button, mapping, True), action)
            self.assertEqual(choose_action('other', button, mapping, False), action if button in ('upper', 'lower') else 'none')
            self.assertEqual(choose_action('unknown', button, mapping, True), 'none')

    def test_volume_without_player_preserves_presentation_priority(self):
        for button, action in [('upper', 'volume-up'), ('lower', 'volume-down')]:
            self.assertEqual(choose_action('other', button, DEFAULTS, None), action)
            for context in ('powerpoint', 'google', 'xaringan'):
                self.assertEqual(choose_action(context, button, DEFAULTS, False), DEFAULTS[button])
            self.assertEqual(choose_action('unknown', button, DEFAULTS, False), 'none')

    def test_foreground_process_and_google_url(self):
        classify = Classifier().classify
        self.assertEqual(classify(r'C:\Office\POWERPNT.EXE', ''), 'powerpoint')
        self.assertEqual(classify(r'C:\Chrome\chrome.exe', 'https://docs.google.com/presentation/d/example/edit'), 'google')
        self.assertEqual(classify('chrome.exe', ''), 'unknown')
        self.assertEqual(classify('notepad.exe', ''), 'other')
        self.assertEqual(classify('chrome.exe', 'Untitled document'), 'unknown')

    def test_worker_routes_native_music_and_presentation(self):
        for process, button, action, command in [('music.exe', 'center', None, 3),
                                                ('music.exe', 'right', None, 2),
                                                ('music.exe', 'upper', None, None),
                                                ('music.exe', 'lower', None, None),
                                                ('POWERPNT.EXE', 'center', 'powerpoint', None)]:
            calls, keys, volumes = [], [], []
            native = SimpleNamespace(window=lambda: 123,
                foreground=lambda: SimpleNamespace(window=123, process=process, url=''),
                media=lambda command=0, window=0: calls.append((command, window)) or (5 if command == 0 else 1),
                volume=volumes.append)
            with patch('tools.context_jx05.Windows', return_value=native):
                router = Router(keys.append)
            try:
                router.configure(True, dict(DEFAULTS, center='present'))
                router.submit(button)
                while True:
                    result = router.results.get(timeout=2)
                    if result['kind'] == 'action': break
                self.assertEqual(keys, [action] if action else [])
                self.assertEqual(volumes, [1] if button == 'upper' else [-1] if button == 'lower' else [])
                if button in ('upper', 'lower'): self.assertEqual(calls, [])
                self.assertEqual([c for c in calls if c[0]], [(command, 123)] if command else [])
                if process == 'POWERPNT.EXE': self.assertEqual(calls, [])
            finally:
                router.stop()

    def test_volume_accelerates_at_three_seconds_and_short_press_resets(self):
        volumes = []
        native = SimpleNamespace(window=lambda: 123,
            foreground=lambda: SimpleNamespace(window=123, process='notepad.exe', url=''),
            media=lambda: 0, volume=lambda direction: volumes.append(direction) or 50)
        with patch('tools.context_jx05.Windows', return_value=native):
            router = Router(lambda action: self.fail('Unexpected keyboard input'))
        try:
            router.configure(True, DEFAULTS)
            for button, duration in [('upper',2.99), ('upper',3), ('lower',4), ('upper',0)]:
                router.submit(button, duration)
                while router.results.get(timeout=2)['kind'] != 'action': pass
            self.assertEqual(volumes, [1,2,-2,1])
        finally:
            router.stop()

    def test_disable_or_focus_change_discards_inflight_button(self):
        for disable in (True, False):
            entered, release, done = threading.Event(), threading.Event(), threading.Event()
            keys = []
            window = [123]
            def foreground():
                entered.set()
                release.wait(2)
                done.set()
                return SimpleNamespace(window=123, process='POWERPNT.EXE', url='')
            native = SimpleNamespace(window=lambda: window[0], foreground=foreground)
            with patch('tools.context_jx05.Windows', return_value=native):
                router = Router(keys.append)
            try:
                router.configure(True, DEFAULTS)
                router.submit('right')
                self.assertTrue(entered.wait(2))
                if disable: router.configure(False, DEFAULTS)
                else: window[0] = 456
                release.set()
                self.assertTrue(done.wait(2))
                router.stop()
                self.assertEqual(keys, [])
            finally:
                release.set()
                router.stop()

    def test_tab_change_in_same_window_does_not_emit(self):
        keys = []
        pages = iter(['https://docs.google.com/presentation/d/a/edit', 'https://example.test/'])
        native = SimpleNamespace(window=lambda: 123,
            foreground=lambda: SimpleNamespace(window=123, process='msedge.exe', url=next(pages)))
        with patch('tools.context_jx05.Windows', return_value=native):
            router = Router(keys.append)
        try:
            router.configure(True, DEFAULTS)
            router.submit('right')
            while True:
                result = router.results.get(timeout=2)
                if result['kind'] != 'context': break
            self.assertEqual(result, dict(kind='skipped', reason='changed-tab'))
            self.assertEqual(keys, [])
        finally:
            router.stop()

    def test_local_xaringan_and_inert_failed_web_lookup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'deck.html'
            path.write_text('<html><script>remark.create({});</script></html>')
            self.assertEqual(Classifier().classify('msedge.exe', path.as_uri() + '#3'), 'xaringan')
        with patch('tools.context_jx05.urlopen', side_effect=OSError('offline')):
            self.assertEqual(Classifier().classify('chrome.exe', 'https://example.test/talk'), 'unknown')

    def test_web_xaringan_and_cache_ignores_slide_fragment(self):
        page = io.BytesIO(b'<html><div class="remark-slide-content">slide</div></html>')
        page.geturl = lambda: 'https://example.test/deck.html'
        classifier = Classifier()
        with patch('tools.context_jx05.urlopen', return_value=page) as request:
            self.assertEqual(classifier.classify('chrome.exe', 'https://example.test/deck.html#1'), 'xaringan')
            self.assertEqual(classifier.classify('chrome.exe', 'https://example.test/deck.html#2'), 'xaringan')
            self.assertEqual(request.call_count, 1)
