"""Monitor continuo del JX-05. --run requiere administrador; --status y --stop no cambian drivers."""
import argparse
import asyncio
import contextlib
import ctypes
from datetime import datetime, timezone
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import time

from select_ring_driver import select, validate_instance
from probe_native_gatt import probe

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.jx05-monitor'
ADDRESS = int('B7FC01C6F37E', 16)
QUERY = r"""
$ErrorActionPreference = 'Stop'
$items = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '00001812.*B7FC01C6F37E' } | ForEach-Object {
    $inf = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_DriverInfPath
    [pscustomobject]@{instance=$_.InstanceId; driver=$inf.Data; problem=[string]$_.Problem}
})
ConvertTo-Json -InputObject $items -Compress
"""


def devices():
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', QUERY],
        capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip())
    return json.loads(result.stdout.decode('utf-8-sig', errors='replace'))


def needs_generic(device, attempted):
    validate_instance(device['instance'])
    return device['driver'].lower() == 'hidbthle.inf' and device['instance'].lower() not in attempted


async def run():
    from winrt.windows.devices.bluetooth import BluetoothLEDevice, BluetoothAddressType
    from winrt.windows.devices.bluetooth.advertisement import BluetoothLEAdvertisementWatcher, BluetoothLEScanningMode
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

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
    STATE.mkdir(exist_ok=True)
    (STATE / 'stop').unlink(missing_ok=True)
    logger = logging.getLogger('jx05')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(STATE / 'events.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    def emit(message):
        logger.info(message)
    loop = asyncio.get_running_loop()
    status = {'pid': os.getpid(), 'running': True, 'driver': None, 'session': 'NONE',
              'native_result': None, 'capture': 'SIN_SUSCRIPCION', 'advertisements': 0}
    attempted = set()
    last_devices = None
    current_instance = None
    last_probe = 0
    last_adv = 0
    device = session = None
    session_token = None
    watcher = BluetoothLEAdvertisementWatcher()
    watcher.scanning_mode = BluetoothLEScanningMode.ACTIVE

    def advertisement(sender, args):
        if args.bluetooth_address == ADDRESS:
            rssi = args.raw_signal_strength_in_dbm
            name = args.advertisement.local_name
            def update():
                nonlocal last_adv
                status['advertisements'] += 1
                if time.monotonic() - last_adv >= 5:
                    emit(f'ANUNCIO nombre={name!r} rssi={rssi}; no es un informe HID')
                    last_adv = time.monotonic()
            loop.call_soon_threadsafe(update)

    def changed(sender, args):
        name, error = args.status.name, str(args.error)
        def update():
            status['session'] = name
            emit(f'SESION {name} error={error}')
        loop.call_soon_threadsafe(update)

    def close_session():
        nonlocal device, session, session_token
        if session:
            try:
                if session_token is not None:
                    session.remove_session_status_changed(session_token)
                session.maintain_connection = False
            finally:
                session.close()
                session = None
                session_token = None
        if device:
            device.close()
            device = None
        status['session'] = 'NONE'
        status['connection'] = 'UNKNOWN'
        status['capture'] = 'SIN_SUSCRIPCION'
        status['native_result'] = None

    def save():
        status['updated'] = datetime.now(timezone.utc).isoformat()
        pending = STATE / 'status.tmp'
        pending.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        pending.replace(STATE / 'status.json')

    token = watcher.add_received(advertisement)
    emit('INICIO: GATT continuo; generico por instancia; prueba de registro cada 60 s; aun sin suscripcion habilitada')
    try:
        watcher.start()
        while not (STATE / 'stop').exists():
            try:
                found = await asyncio.to_thread(devices)
                if found != last_devices:
                    emit('PNP ' + json.dumps(found))
                    last_devices = found
                if len(found) > 1:
                    raise RuntimeError('Mas de una instancia presente: no se seleccionara controlador.')
                item = found[0] if found else None
                instance = item['instance'] if item else None
                status['instance'] = instance
                status['driver'] = item['driver'] if item else None
                if instance != current_instance:
                    close_session()
                    current_instance = instance
                    last_probe = 0
                if item and needs_generic(item, attempted):
                    attempted.add(instance.lower())
                    close_session()
                    emit(f'APLICAR_GENERICO instancia={instance}')
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        await asyncio.to_thread(select, instance, 'generic')
                    emit(output.getvalue().strip())
                    # Comprobar el resultado PnP en el siguiente ciclo.
                    last_probe = 0
                elif item and item['driver'].lower() != 'bthleenum.inf':
                    emit('CONTROLADOR_NO_GENERICO: sin reinstalar repetidamente la misma instancia')
                else:
                    if device is None:
                        device = await BluetoothLEDevice.from_bluetooth_address_async(ADDRESS, BluetoothAddressType.PUBLIC)
                        if device:
                            session = await GattSession.from_device_id_async(device.bluetooth_device_id)
                            if not session or not session.can_maintain_connection:
                                close_session()
                                raise RuntimeError('Sesion no disponible o sin MaintainConnection')
                            session_token = session.add_session_status_changed(changed)
                            session.maintain_connection = True
                    if session:
                        status['session'] = session.session_status.name
                        status['connection'] = device.connection_status.name
                        if status['session'] == 'ACTIVE' and item and time.monotonic() - last_probe >= 60:
                            last_probe = time.monotonic()
                            status['native_result'] = await asyncio.to_thread(probe, ADDRESS, emit, True)
                            status['capture'] = 'REGISTRO_POSIBLE_CCCD_PENDIENTE' if status['native_result'] == 0 else 'REGISTRO_BLOQUEADO'
                    status['error'] = None
            except Exception as exc:
                status['error'] = f'{type(exc).__name__}: {exc}'
                emit('ERROR ' + status['error'])
                close_session()
            save()
            await asyncio.sleep(5)
    finally:
        close_session()
        watcher.stop()
        watcher.remove_received(token)
        status['running'] = False
        save()
        emit('FIN: sesion liberada; asociacion del controlador conservada')
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
        print('Parada solicitada. Esperar running=false; conserva el controlador asociado.')
    else:
        asyncio.run(run())
