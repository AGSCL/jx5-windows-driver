"""Monitor HID del JX-05; modo presentador optativo, desactivado al iniciar."""
import argparse
import asyncio
import contextlib
import ctypes
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.jx05-monitor'
ADDRESS = 'B7:FC:01:C6:F3:7E'
TARGETS = {f'0000{uuid}-0000-1000-8000-00805f9b34fb' for uuid in ('ae02', 'ae42')}


async def capture(client_factory, status, emit):
    """Redescubrir objetos por conexion; conservar todos los bytes sin interpretarlos."""
    disconnected = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_disconnect(_):
        loop.call_soon_threadsafe(disconnected.set)

    def on_packet(characteristic, data):
        status['packets'] += 1
        status['last_packet'] = {
            'time': datetime.now(timezone.utc).isoformat(),
            'uuid': characteristic.uuid, 'handle': characteristic.handle,
            'bytes': bytes(data).hex(' ')}
        emit('PAQUETE ' + json.dumps(status['last_packet']))

    status.update(connection='CONNECTING', capture='SIN_SUSCRIPCION', subscriptions=[])
    async with client_factory(ADDRESS, timeout=30, disconnected_callback=on_disconnect,
                              winrt={'address_type': 'public', 'use_cached_services': False}) as client:
        status['connection'] = 'CONNECTED'
        for service in client.services:
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() not in TARGETS:
                    continue
                details = {'service': service.uuid, 'uuid': characteristic.uuid,
                           'handle': characteristic.handle, 'properties': list(characteristic.properties)}
                emit('CARACTERISTICA ' + json.dumps(details))
                if not any(p in characteristic.properties for p in ('notify', 'indicate')):
                    emit('SIN_NOTIFY ' + json.dumps(details))
                    continue
                try:
                    await asyncio.wait_for(client.start_notify(characteristic, on_packet), timeout=15)
                except Exception as exc:
                    emit(f'ERROR_SUSCRIPCION {json.dumps(details)} {type(exc).__name__}: {exc}')
                else:
                    status['subscriptions'].append(details)
                    emit('SUSCRITO ' + json.dumps(details))
        if disconnected.is_set() or not client.is_connected:
            raise ConnectionError('Desconectado durante la suscripcion')
        status['capture'] = 'ESCUCHANDO' if status['subscriptions'] else 'BLOQUEADO'
        status['error'] = None
        emit(status['capture'] + ': no se ha identificado ningun boton; emision de teclas desactivada')
        await disconnected.wait()
        raise ConnectionError('El anillo se desconecto')


async def monitor(client_factory, status, emit, save, stopped, *, tick=1, retry_base=2, retry_max=60):
    delay = retry_base
    while not stopped():
        started = time.monotonic()
        task = asyncio.create_task(capture(client_factory, status, emit))
        try:
            while not task.done() and not stopped():
                save()
                await asyncio.sleep(tick)
            if stopped():
                return
            await task
        except Exception as exc:
            status['error'] = f'{type(exc).__name__}: {exc}'
            emit('ERROR ' + status['error'])
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            status.update(connection='DISCONNECTED', capture='SIN_SUSCRIPCION', subscriptions=[])
            save()
        if time.monotonic() - started >= 60:
            delay = retry_base
        status['retry_seconds'] = delay
        emit(f'REINTENTO en {delay} s')
        until = time.monotonic() + delay
        while not stopped() and time.monotonic() < until:
            save()
            await asyncio.sleep(min(tick, max(0, until - time.monotonic())))
        status['retry_seconds'] = 0
        delay = min(delay * 2, retry_max)


def foreground_class():
    from ctypes import wintypes as w
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = w.HWND
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    name = ctypes.create_unicode_buffer(256)
    if not user.GetClassNameW(user.GetForegroundWindow(), name, len(name)):
        raise ctypes.WinError(ctypes.get_last_error())
    return name.value


def foreground_fullscreen():
    from ctypes import wintypes as w
    c = ctypes
    class Monitor(c.Structure):
        _fields_ = [('size', w.DWORD), ('screen', w.RECT), ('work', w.RECT), ('flags', w.DWORD)]
    user, dwm = c.WinDLL('user32', use_last_error=True), c.WinDLL('dwmapi')
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowLongW.argtypes = [w.HWND, c.c_int]
    user.GetWindowLongW.restype = w.LONG
    user.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    user.MonitorFromWindow.restype = w.HANDLE
    user.GetMonitorInfoW.argtypes = [w.HANDLE, c.POINTER(Monitor)]
    user.GetMonitorInfoW.restype = w.BOOL
    dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, c.c_void_p, w.DWORD]
    dwm.DwmGetWindowAttribute.restype = c.c_int32
    hwnd = user.GetForegroundWindow()
    if user.GetWindowLongW(hwnd, -16) & 0x00c00000:
        return False
    rect, monitor = w.RECT(), Monitor(size=c.sizeof(Monitor))
    hr = dwm.DwmGetWindowAttribute(hwnd, 9, c.byref(rect), c.sizeof(rect))
    if hr != 0:
        raise RuntimeError(f'No se pudo consultar la pantalla completa: HRESULT={hr & 0xffffffff:08x}')
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), c.byref(monitor)):
        raise c.WinError(c.get_last_error())
    # shortcut: Google Slides en pantalla completa; el modo en ventana requiere otra detección.
    return all(getattr(rect, edge) == getattr(monitor.screen, edge) for edge in ('left', 'top', 'right', 'bottom'))


def send_key(action):
    from ctypes import wintypes as w
    c = ctypes
    class Keyboard(c.Structure):
        _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                    ('time', w.DWORD), ('extra', c.c_size_t)]
    class Mouse(c.Structure):
        _fields_ = [('x', w.LONG), ('y', w.LONG), ('data', w.DWORD),
                    ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]
    class Payload(c.Union):
        _fields_ = [('keyboard', Keyboard), ('mouse', Mouse)]
    class Input(c.Structure):
        _fields_ = [('kind', w.DWORD), ('payload', Payload)]
    send = c.WinDLL('user32', use_last_error=True).SendInput
    send.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
    send.restype = w.UINT
    keys = {'next': (0x27,), 'previous': (0x25,), 'powerpoint': (0x10, 0x74),
            'google': (0x11, 0x74), 'xaringan': (0x46,)}[action]
    if action == 'powerpoint' and foreground_class() in ('screenClass', 'PodiumParent'):
        keys = (0x1b,)
    if action == 'google' and foreground_fullscreen():
        keys = (0x1b,)
    events = [(key, 0) for key in keys] + [(key, 2) for key in reversed(keys)]
    batch = (Input * len(events))()
    for index, (key, flags) in enumerate(events):
        batch[index].kind = 1
        batch[index].payload.keyboard = Keyboard(key, 0, flags, 0, 0)
    sent = send(len(batch), batch, c.sizeof(Input))
    if sent != len(batch):
        held = []
        for key, flags in events[:sent]:
            if flags == 0: held.append(key)
            else: held.remove(key)
        if held:
            release = (Input * len(held))()
            for index, key in enumerate(reversed(held)):
                release[index].kind = 1
                release[index].payload.keyboard = Keyboard(key, 0, 2, 0, 0)
            send(len(release), release, c.sizeof(Input))
        raise RuntimeError(f'SendInput aceptó {sent}/{len(batch)} eventos; revisar permisos de la aplicación en primer plano')


def run():
    try:
        from .capture_raw_hid import run as capture_raw
        from .jx05_gestures import Gestures
        from .map_jx05 import load as load_mapping
    except ImportError:
        from capture_raw_hid import run as capture_raw
        from jx05_gestures import Gestures
        from map_jx05 import load as load_mapping

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, 'Local\\JX05DiagnosticMonitor')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        raise RuntimeError('Ya existe un monitor activo.')
    handler = None
    try:
        STATE.mkdir(exist_ok=True)
        (STATE / 'stop').unlink(missing_ok=True)
        (STATE / 'presenter-command.json').unlink(missing_ok=True)
        logger = logging.getLogger('jx05')
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(STATE / 'events.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        logger.addHandler(handler)
        status = {'pid': os.getpid(), 'running': True, 'connection': 'DISCONNECTED',
                  'capture': 'SIN_SUSCRIPCION', 'subscriptions': [], 'packets': 0,
                  'last_packet': None, 'presenter_enabled': False, 'retry_seconds': 0, 'error': None,
                  'actions': 0, 'last_action': None, 'backend': 'raw-input'}
        decoder = Gestures()
        mapping = load_mapping()
        status['mapping'] = mapping

        def save():
            status['updated'] = datetime.now(timezone.utc).isoformat()
            pending = STATE / 'status.tmp'
            pending.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
            pending.replace(STATE / 'status.json')

        def on_event(event, **fields):
            logger.info('%s %s', event, json.dumps(fields))
            if event == 'ready':
                status.update(capture='ESCUCHANDO_HID', connection='ESPERANDO_INFORMES')
            elif event == 'device_change':
                decoder.reset()
                status['connection'] = 'CAMBIO_DE_DISPOSITIVO'
            elif event == 'report':
                status['packets'] += 1
                status['last_packet'] = dict(time=datetime.now(timezone.utc).isoformat(), **fields)
                status['connection'] = 'INFORMES_RECIBIDOS'
                button = decoder.feed(bytes.fromhex(fields['hex']), time.monotonic())
                if button:
                    action = mapping[button]
                    status['last_button'] = button
                    logger.info('GESTO %s action=%s presenter=%s', button, action, status['presenter_enabled'])
                    if status['presenter_enabled'] and action != 'none':
                        try:
                            send_key(action)
                        except Exception as exc:
                            status.update(presenter_enabled=False, error=str(exc))
                            logger.exception('EMISION_DESACTIVADA')
                        else:
                            status['actions'] += 1
                            status['last_action'] = dict(action=action, time=datetime.now(timezone.utc).isoformat())
            elif event == 'error':
                status.update(error=fields['detail'], presenter_enabled=False)
            save()

        def tick():
            nonlocal mapping
            command = STATE / 'presenter-command.json'
            if command.exists():
                request = json.loads(command.read_text(encoding='utf-8'))
                command.unlink()
                if request.get('pid') == os.getpid() and type(request.get('enabled')) is bool:
                    decoder.reset()
                    status['presenter_enabled'] = False
                    if request['enabled']:
                        mapping = load_mapping()
                        status['mapping'] = mapping
                    status['presenter_enabled'] = request['enabled']
                    logger.info('PRESENTADOR %s', request['enabled'])
            save()

        logger.info('INICIO: Raw Input; modo presentador desactivado; sin cambios de controlador')
        try:
            capture_raw(on_event=on_event, on_tick=tick, stopped=lambda: (STATE / 'stop').exists())
        finally:
            status['running'] = False
            status['presenter_enabled'] = False
            save()
            logger.info('FIN: lectura HID detenida')
    finally:
        if handler:
            logger.removeHandler(handler)
            handler.close()
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--status', action='store_true')
    modes.add_argument('--stop', action='store_true')
    modes.add_argument('--presenter-on', action='store_true')
    modes.add_argument('--presenter-off', action='store_true')
    args = parser.parse_args()
    if args.status:
        path = STATE / 'status.json'
        print(path.read_text(encoding='utf-8') if path.exists() else 'Sin estado registrado.')
        print('Comprueba updated: un estado antiguo no garantiza que el proceso siga vivo.')
    elif args.stop:
        STATE.mkdir(exist_ok=True)
        (STATE / 'stop').touch()
        print('Parada solicitada. Esperar running=false.')
    elif args.presenter_on or args.presenter_off:
        state = json.loads((STATE / 'status.json').read_text(encoding='utf-8'))
        if not state.get('running') or state.get('backend') != 'raw-input':
            raise SystemExit('El monitor HID no está activo.')
        pending = STATE / 'presenter-command.tmp'
        pending.write_text(json.dumps({'pid': state['pid'], 'enabled': args.presenter_on}), encoding='utf-8')
        pending.replace(STATE / 'presenter-command.json')
        print('Orden enviada; comprobar presenter_enabled en --status.')
    else:
        run()
