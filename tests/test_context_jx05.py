import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from tools.context_jx05 import Classifier, choose_action
from tools.map_jx05 import DEFAULTS


class ContextTests(unittest.TestCase):
    def test_presentations_always_win_over_music(self):
        mapping = dict(DEFAULTS, center='present')
        for app in ('powerpoint', 'google', 'xaringan'):
            self.assertEqual(choose_action(app, 'left', mapping, True), 'previous')
            self.assertEqual(choose_action(app, 'upper', mapping, True), 'previous')
            self.assertEqual(choose_action(app, 'center', mapping, True), app)
        for button, action in [('left', 'track-previous'), ('right', 'track-next'),
                               ('center', 'play-pause'), ('upper', 'volume-up'), ('lower', 'volume-down')]:
            self.assertEqual(choose_action('other', button, mapping, True), action)
            self.assertEqual(choose_action('other', button, mapping, False), 'none')
            self.assertEqual(choose_action('unknown', button, mapping, True), 'none')

    def test_foreground_process_and_google_url(self):
        classify = Classifier().classify
        self.assertEqual(classify(r'C:\Office\POWERPNT.EXE', ''), 'powerpoint')
        self.assertEqual(classify(r'C:\Chrome\chrome.exe', 'https://docs.google.com/presentation/d/example/edit'), 'google')
        self.assertEqual(classify('chrome.exe', ''), 'unknown')
        self.assertEqual(classify('notepad.exe', ''), 'other')

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
