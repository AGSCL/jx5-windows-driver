"""Presentation priority and residual Windows media control, in one worker thread."""
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import queue
import re
import threading
import time
from urllib.parse import urlsplit, urldefrag
from urllib.request import urlopen, Request, url2pathname

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = {'chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe'}
PRESENTATIONS = {'powerpoint', 'google', 'xaringan', 'revealjs'}
MARKER = re.compile(rb'remark\s*\.\s*create\s*\(|remark-slide-container|remark-slide-content|remark-latest(?:\.min)?\.js', re.I)
REVEAL_MARKER = re.compile(rb"""<div\s+class=["']reveal["']\s*>\s*<div\s+class=["']slides["']\s*>""", re.I)


def volume_step(held_seconds, level):
    """Puntos por repeticion: 5, 10 (>=1 s) o 15 (>=2 s); siempre 5 por debajo del 20 %."""
    if level < 20:
        return 5
    return 15 if held_seconds >= 2 else 10 if held_seconds >= 1 else 5


def choose_action(context, button, mapping, media_available):
    if context in PRESENTATIONS:
        action = mapping[button]
        return context if action == 'present' else action
    if context == 'other':
        if button in ('upper', 'lower'):
            return 'volume-up' if button == 'upper' else 'volume-down'
        if media_available:
            return {'left': 'track-previous', 'right': 'track-next', 'center': 'play-pause'}[button]
    return 'none'


class Classifier:
    def __init__(self):
        self.cache = {}

    def classify(self, process, url):
        name = process.replace('\\', '/').rsplit('/', 1)[-1].lower()
        if name == 'powerpnt.exe':
            return 'powerpoint'
        if name not in BROWSERS:
            return 'other' if name else 'unknown'
        if not url:
            return 'unknown'
        parsed = urlsplit(url)
        if parsed.scheme in ('https', 'http') and parsed.hostname == 'docs.google.com' and parsed.path.startswith('/presentation/'):
            return 'google'
        if parsed.scheme not in ('http', 'https', 'file'):
            return 'other' if parsed.scheme in ('about', 'chrome', 'edge') else 'unknown'
        key = urldefrag(url)[0]
        now = time.monotonic()
        if key in self.cache and now - self.cache[key][0] < 60:
            return self.cache[key][1]
        context = 'unknown'
        try:
            if parsed.scheme == 'file':
                if not parsed.path.lower().endswith(('.html', '.htm')):
                    return 'other'
                path = url2pathname(('//' + parsed.netloc if parsed.netloc else '') + parsed.path)
                source = open(path, 'rb')
            else:
                source = urlopen(Request(key, headers={'User-Agent': 'JX05 presentation detector'}), timeout=2)
                if urldefrag(source.geturl())[0] != key:
                    source.close()
                    self.cache[key] = (now, 'unknown')
                    return 'unknown'
            with source:
                tail = b''
                for _ in range(128):
                    chunk = source.read(65536)
                    sample = tail + chunk
                    if REVEAL_MARKER.search(sample):
                        context = 'revealjs'
                        break
                    if MARKER.search(sample):
                        context = 'xaringan'
                        break
                    if not chunk:
                        context = 'other'
                        break
                    tail = chunk[-256:]
        except (OSError, ValueError):
            pass
        # Unknown pages stay inert; failed/oversized reads never enable media keys.
        if len(self.cache) >= 64:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (now, context)
        return context


class Foreground(c.Structure):
    _fields_ = [('window', c.c_uint64), ('process', w.WCHAR * 260), ('url', w.WCHAR * 8192)]


class Windows:
    def __init__(self):
        self.dll = c.CDLL(str(ROOT / 'build/context/jx05_context.dll'))
        self.dll.JxForeground.argtypes = [c.POINTER(Foreground)]
        self.dll.JxForeground.restype = c.c_int32
        self.dll.JxVisibleWindow.argtypes = [w.HWND, c.POINTER(Foreground)]
        self.dll.JxVisibleWindow.restype = c.c_int32
        self.slide_callback = c.CFUNCTYPE(c.c_int)
        self.dll.JxWithSlideFocus.argtypes = [w.HWND, w.HWND, self.slide_callback]
        self.dll.JxWithSlideFocus.restype = c.c_int
        self.dll.JxMedia.argtypes = [c.c_int, c.c_uint64]
        self.dll.JxMedia.restype = c.c_int32
        self.dll.JxVolume.argtypes = [c.c_int]
        self.dll.JxVolume.restype = c.c_int32
        self.user = c.WinDLL('user32')
        self.user.GetForegroundWindow.argtypes = []
        self.user.GetForegroundWindow.restype = w.HWND
        self.user.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.user.GetAncestor.restype = w.HWND
        self.enum_callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.user.EnumWindows.argtypes = [self.enum_callback, w.LPARAM]
        self.user.EnumWindows.restype = w.BOOL

    def window(self):
        return self.user.GetAncestor(self.user.GetForegroundWindow(), 2)  # GA_ROOT

    def foreground(self):
        value = Foreground()
        result = self.dll.JxForeground(c.byref(value))
        if result < 0:
            raise RuntimeError(f'Foreground HRESULT={result & 0xffffffff:08x}')
        return value

    def visible_windows(self, exclude):
        handles = []
        def collect(hwnd, _):
            if hwnd != exclude:
                handles.append(hwnd)
            return True
        self.user.EnumWindows(self.enum_callback(collect), 0)
        for hwnd in handles:
            value = Foreground()
            if self.dll.JxVisibleWindow(hwnd, c.byref(value)) == 0:
                yield value

    def with_slide_focus(self, original, target, send):
        errors = []
        def dispatch():
            try:
                return int(send())
            except Exception as exc:
                errors.append(exc)
                return 0
        sent = self.dll.JxWithSlideFocus(original, target, self.slide_callback(dispatch))
        if errors:
            raise errors[0]
        return bool(sent)

    def media(self, command=0, window=0):
        result = self.dll.JxMedia(command, window)
        if result < 0:
            if command == 0:
                return 0  # An unavailable media broker must not disable presentation controls.
            raise RuntimeError(f'Media HRESULT={result & 0xffffffff:08x}')
        return result

    def volume(self, direction=0):
        result = self.dll.JxVolume(direction)
        if result < 0:
            raise RuntimeError(f'Volume HRESULT={result & 0xffffffff:08x}')
        return result


class Router:
    def __init__(self, send_key):
        self.send_key = send_key
        self.native = Windows()
        self.classifier = Classifier()
        self.requests = queue.Queue(maxsize=32)
        self.results = queue.Queue()
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.generation, self.enabled, self.mapping = 0, False, {}
        self.thread = threading.Thread(target=self.run, name='JX05 context', daemon=True)
        self.thread.start()

    def configure(self, enabled, mapping):
        with self.lock:
            self.generation += 1
            self.enabled, self.mapping = enabled, mapping.copy()

    def submit(self, button, held_seconds=0):
        with self.lock:
            request = (self.generation, time.monotonic(), self.native.window(), button, held_seconds)
        try:
            self.requests.put_nowait(request)
        except queue.Full:
            self.results.put(dict(kind='skipped', reason='queue-full'))

    def stop(self):
        self.closed.set()
        self.configure(False, {})
        self.thread.join(timeout=2)

    def run(self):
        last_context = None
        while not self.closed.is_set():
            try:
                request = self.requests.get(timeout=.5)
            except queue.Empty:
                request = None
            with self.lock:
                enabled = self.enabled
            if not enabled:
                continue
            try:
                try:
                    foreground = self.native.foreground()
                except RuntimeError as exc:
                    # Transient (80010108 RPC disconnected, 80070005 elevated window): skip, don't pause controls.
                    if request is not None:
                        self.results.put(dict(kind='skipped', reason=f'foreground-unavailable: {exc}'))
                    continue
                context = self.classifier.classify(foreground.process, foreground.url)
                target = foreground
                if foreground.window and context not in PRESENTATIONS:
                    for candidate in self.native.visible_windows(foreground.window):
                        candidate_context = self.classifier.classify(candidate.process, candidate.url)
                        if candidate_context in PRESENTATIONS:
                            context, target = candidate_context, candidate
                            break
                # Volume must not wait for a missing or slow media broker.
                volume_request = request is not None and request[3] in ('upper', 'lower')
                media = None if volume_request else self.native.media() in (4, 5) if context == 'other' else False
                current = (context, media)
                if current != last_context:
                    self.results.put(dict(kind='context', context=context, media_available=media))
                    last_context = current
                if request is None:
                    continue
                generation, started, window, button, held_seconds = request
                with self.lock:
                    enabled = self.enabled and generation == self.generation
                    mapping = self.mapping.copy()
                if not enabled or self.closed.is_set():
                    continue
                if time.monotonic() - started > 1 or window != foreground.window or window != self.native.window():
                    self.results.put(dict(kind='skipped', reason='stale-focus'))
                    continue
                action = choose_action(context, button, mapping, media)
                if action == 'none':
                    continue
                if foreground.url and target.window == window:
                    current_foreground = self.native.foreground()
                    if (current_foreground.window, current_foreground.url) != (foreground.window, foreground.url):
                        self.results.put(dict(kind='skipped', reason='changed-tab'))
                        continue
                with self.lock:
                    if not self.enabled or generation != self.generation or self.closed.is_set():
                        continue
                if time.monotonic() - started > 1 or window != self.native.window():
                    self.results.put(dict(kind='skipped', reason='stale-focus'))
                    continue
                commands = {'track-previous': 1, 'track-next': 2, 'play-pause': 3}
                details = {}
                if action in commands:
                    if not self.native.media(commands[action], window):
                        self.results.put(dict(kind='skipped', reason='media-control-unavailable'))
                        continue
                elif action in ('volume-up', 'volume-down'):
                    step = volume_step(held_seconds, self.native.volume(0))
                    sign, units = (1 if action == 'volume-up' else -1), step // 5
                    # El anillo repite cada 0.75 s: la mitad del salto se aplica al instante (respuesta) y el
                    # resto se reparte en ese intervalo (fluidez); mismo total, sin mas desbordamiento al soltar.
                    first = (units + 1) // 2
                    level = self.native.volume(sign * first)  # JxVolume admite como maximo +-2 unidades por llamada
                    for _ in range(units - first):
                        if self.closed.wait(0.75 / (units - first + 1)):
                            break
                        with self.lock:
                            if not self.enabled or generation != self.generation:
                                break
                        level = self.native.volume(sign)
                    details = dict(volume_step=step, volume_percent=level, held_seconds=round(held_seconds, 3))
                elif target.window != window:
                    def send_to_slide():
                        try:
                            active = self.native.foreground()
                        except RuntimeError:
                            return False
                        if (active.window, active.process, active.url) != (target.window, target.process, target.url):
                            return False
                        with self.lock:
                            if not self.enabled or generation != self.generation or self.closed.is_set():
                                return False
                        if time.monotonic() - started > 1 or self.native.window() != target.window:
                            return False
                        self.send_key(action)
                        return True
                    if not self.native.with_slide_focus(window, target.window, send_to_slide):
                        self.results.put(dict(kind='skipped', reason='slide-window-unavailable'))
                        continue
                    details = dict(visible_window=True)
                else:
                    self.send_key(action)
                self.results.put(dict(kind='action', button=button, action=action, context=context, **details))
            except Exception as exc:
                # Disable immediately, before another queued button can emit anything.
                self.configure(False, {})
                self.results.put(dict(kind='error', detail=str(exc)))
                self.closed.wait(.5)
