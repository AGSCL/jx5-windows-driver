"""Observador AE02/AE42 del JX-05: no cambia controladores ni emite teclas."""
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


async def run():
    from bleak import BleakClient

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
        logger = logging.getLogger('jx05')
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(STATE / 'events.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        logger.addHandler(handler)
        status = {'pid': os.getpid(), 'running': True, 'connection': 'DISCONNECTED',
                  'capture': 'SIN_SUSCRIPCION', 'subscriptions': [], 'packets': 0,
                  'last_packet': None, 'presenter_enabled': False, 'retry_seconds': 0, 'error': None}

        def save():
            status['updated'] = datetime.now(timezone.utc).isoformat()
            pending = STATE / 'status.tmp'
            pending.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
            pending.replace(STATE / 'status.json')

        logger.info('INICIO: observacion AE02/AE42; sin cambios de controlador; sin emision de teclas')
        try:
            await monitor(BleakClient, status, logger.info, save, lambda: (STATE / 'stop').exists())
        finally:
            status['running'] = False
            save()
            logger.info('FIN: suscripciones y conexion liberadas')
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
    args = parser.parse_args()
    if args.status:
        path = STATE / 'status.json'
        print(path.read_text(encoding='utf-8') if path.exists() else 'Sin estado registrado.')
        print('Comprueba updated: un estado antiguo no garantiza que el proceso siga vivo.')
    elif args.stop:
        STATE.mkdir(exist_ok=True)
        (STATE / 'stop').touch()
        print('Parada solicitada. Esperar running=false.')
    else:
        asyncio.run(run())
