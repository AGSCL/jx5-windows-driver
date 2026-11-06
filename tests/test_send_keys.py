import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tools.monitor_jx05 import send_key, foreground_fullscreen, foreground_class


class SendKeysTests(unittest.TestCase):
    def test_arrow_pair_and_failed_partial_cleanup(self):
        for action, keys in [('next', [0x27]), ('previous', [0x25]),
                             ('powerpoint', [0x10, 0x74]), ('google', [0x11, 0x74]), ('xaringan', [0x46])]:
            calls = []
            def fake(count, inputs, size):
                self.assertEqual(size, 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
                calls.append([(inputs[i].kind, inputs[i].payload.keyboard.vk,
                               inputs[i].payload.keyboard.flags) for i in range(count)])
                return count
            with patch('ctypes.WinDLL', return_value=SimpleNamespace(SendInput=fake)), \
                    patch('tools.monitor_jx05.foreground_class', return_value='PPTFrameClass'), \
                    patch('tools.monitor_jx05.foreground_fullscreen', return_value=False):
                send_key(action)
            self.assertEqual(calls, [[(1, key, 0) for key in keys] + [(1, key, 2) for key in reversed(keys)]])
        counts = []
        def partial(count, inputs, size):
            counts.append(count)
            return 1
        with patch('ctypes.WinDLL', return_value=SimpleNamespace(SendInput=partial)):
            with self.assertRaises(RuntimeError): send_key('next')
        self.assertEqual(counts, [2, 1])

    def test_partial_shortcut_releases_only_pressed_keys(self):
        for sent, held in [(0, []), (1, [0x10]), (2, [0x74, 0x10]), (3, [0x10])]:
            calls = []
            def partial(count, inputs, size):
                calls.append([(inputs[i].payload.keyboard.vk, inputs[i].payload.keyboard.flags) for i in range(count)])
                return sent if len(calls) == 1 else count
            with patch('ctypes.WinDLL', return_value=SimpleNamespace(SendInput=partial)), \
                    patch('tools.monitor_jx05.foreground_class', return_value='PPTFrameClass'):
                with self.assertRaises(RuntimeError): send_key('powerpoint')
            self.assertEqual(calls[1:], [[(key, 2) for key in held]] if held else [])

    def test_powerpoint_toggle_uses_current_window_not_a_counter(self):
        calls = []
        def fake(count, inputs, size):
            calls.append([inputs[i].payload.keyboard.vk for i in range(count)])
            return count
        with patch('ctypes.WinDLL', return_value=SimpleNamespace(SendInput=fake)), \
                patch('tools.monitor_jx05.foreground_class', side_effect=['screenClass', 'PPTFrameClass', 'PodiumParent', 'PPTFrameClass']):
            for _ in range(4): send_key('powerpoint')
        self.assertEqual(calls, [[0x1b, 0x1b], [0x10, 0x74, 0x74, 0x10],
                                [0x1b, 0x1b], [0x10, 0x74, 0x74, 0x10]])

    def test_google_leaves_fullscreen(self):
        calls = []
        def fake(count, inputs, size):
            calls.append([inputs[i].payload.keyboard.vk for i in range(count)])
            return count
        with patch('ctypes.WinDLL', return_value=SimpleNamespace(SendInput=fake)), \
                patch('tools.monitor_jx05.foreground_fullscreen', return_value=True):
            send_key('google')
        self.assertEqual(calls, [[0x1b, 0x1b]])

    def test_window_detection_bindings_and_fullscreen_bounds(self):
        from ctypes import wintypes as w
        def class_name(hwnd, buffer, capacity):
            buffer.value = 'screenClass'
            return len(buffer.value)
        user = SimpleNamespace(GetForegroundWindow=lambda: 123, GetClassNameW=class_name)
        with patch('ctypes.WinDLL', return_value=user):
            self.assertEqual(foreground_class(), 'screenClass')
        for caption, bottom, hr, expected in [(0, 1080, 0, True), (0, 1040, 0, False),
                                               (0xc00000, 1080, 0, False), (0, 1080, -1, None)]:
            def bounds(hwnd, attribute, pointer, size):
                self.assertEqual(attribute, 9)
                pointer._obj.left, pointer._obj.top = -1920, 0
                pointer._obj.right, pointer._obj.bottom = 0, bottom
                return hr
            def monitor(handle, pointer):
                self.assertEqual(pointer._obj.size, ctypes.sizeof(pointer._obj))
                pointer._obj.screen = w.RECT(-1920, 0, 0, 1080)
                return True
            user = SimpleNamespace(GetForegroundWindow=lambda:123, GetWindowLongW=lambda h,i:caption,
                                   MonitorFromWindow=lambda h,f:456, GetMonitorInfoW=monitor)
            with patch('ctypes.WinDLL', side_effect=[user, SimpleNamespace(DwmGetWindowAttribute=bounds)]):
                if expected is None:
                    with self.assertRaises(RuntimeError): foreground_fullscreen()
                else:
                    self.assertEqual(foreground_fullscreen(), expected)
