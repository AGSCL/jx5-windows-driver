"""Mide una sesion GATT en Windows sin leer Report Map ni suscribir informes.

Usa las dependencias WinRT instaladas por bleak>=1,<3.
"""
import argparse
import asyncio
import sys
import time
from uuid import UUID


async def monitor(session, *, seconds=60, connect_timeout=30, emit=print, on_active=None):
    loop = asyncio.get_running_loop()
    changes = asyncio.Queue()

    def changed(sender, args):
        loop.call_soon_threadsafe(changes.put_nowait,
                                 (time.monotonic(), int(sender.session_status), str(args.error)))

    token = session.add_session_status_changed(changed)
    started = None
    deadline = time.monotonic() + connect_timeout
    try:
        session.maintain_connection = True
        changes.put_nowait((time.monotonic(), int(session.session_status), "inicial"))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if started is not None and int(session.session_status) == 1:
                    emit(f"SESION_ESTABLE: activa durante {seconds:g} segundos.")
                    return 0
                emit("SESION_NO_ACTIVA: no se consiguio mantener la sesion.")
                return 4
            try:
                stamp, status, error = await asyncio.wait_for(changes.get(), remaining)
            except asyncio.TimeoutError:
                continue
            emit(f"ESTADO_SESION: {'ACTIVE' if status == 1 else 'CLOSED'} error={error}")
            if status == 1 and started is None:
                started = stamp
                if on_active is not None:
                    code = await asyncio.wait_for(on_active(), 30)
                    if int(session.session_status) != 1:
                        emit("SESION_PERDIDA: se cerro durante la consulta HID.")
                        return 4
                    return code
                deadline = started + seconds
                emit(f"MIDIENDO: {seconds:g} segundos desde la activacion.")
            elif status != 1 and started is not None:
                emit(f"SESION_PERDIDA: duracion={stamp - started:.3f} segundos.")
                return 4
    finally:
        session.remove_session_status_changed(token)
        session.maintain_connection = False


async def check_hid_access(device, cache_mode, emit=print):
    emit("CONSULTANDO_HID: servicio 1812, sin leer valores de caracteristicas.")
    result = await device.get_gatt_services_for_uuid_async(
        UUID("00001812-0000-1000-8000-00805f9b34fb"), cache_mode)
    services = list(result.services)
    try:
        emit(f"DESCUBRIMIENTO_HID: {result.status.name} protocolo={result.protocol_error}")
        if result.status.name != "SUCCESS":
            return 3
        if not services:
            emit("HID_NO_VISIBLE: Windows no entrego el servicio 1812.")
            return 3
        for service in services:
            access = await service.request_access_async()
            emit(f"ACCESO_HID: {access.name}")
            if access.name != "ALLOWED":
                return 3
            chars = await service.get_characteristics_async(cache_mode)
            emit(f"CARACTERISTICAS_HID: {chars.status.name} protocolo={chars.protocol_error}")
            if chars.status.name != "SUCCESS":
                return 3
            if not chars.characteristics:
                emit("HID_SIN_CARACTERISTICAS")
                return 3
            for char in chars.characteristics:
                emit(f"CARACTERISTICA: handle=0x{char.attribute_handle:04x} uuid={char.uuid} propiedades={char.characteristic_properties}")
        emit("HID_ENUMERADO: acceso y enumeracion permitidos; notificaciones aun no probadas.")
        return 0
    finally:
        for service in services:
            service.close()


async def run(address, check_hid=False):
    from winrt.windows.devices.bluetooth import BluetoothLEDevice, BluetoothCacheMode
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementWatcher, BluetoothLEScanningMode)
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

    loop = asyncio.get_running_loop()
    found = loop.create_future()
    watcher = BluetoothLEAdvertisementWatcher()
    watcher.scanning_mode = BluetoothLEScanningMode.ACTIVE

    def received(_, args):
        if address is not None:
            matches = args.bluetooth_address == address
        else:
            matches = args.advertisement.local_name.casefold() == "jx-05"
        if matches:
            def deliver():
                if not found.done():
                    found.set_result((args.bluetooth_address, args.bluetooth_address_type))
            loop.call_soon_threadsafe(deliver)

    token = watcher.add_received(received)
    try:
        print("BUSCANDO: enciende el anillo; esperando anuncio hasta 60 segundos.", flush=True)
        watcher.start()
        try:
            remote_address, address_type = await asyncio.wait_for(found, 60)
        except asyncio.TimeoutError:
            print("SIN_ANUNCIO: no se pudo iniciar la prueba de sesion.")
            return 2
    finally:
        watcher.stop()
        watcher.remove_received(token)

    print(f"ANUNCIO: direccion={remote_address:012X} tipo={address_type.name}", flush=True)
    device = await BluetoothLEDevice.from_bluetooth_address_with_bluetooth_address_type_async(
        remote_address, address_type)
    if device is None:
        print("SIN_OBJETO: Windows no entrego BluetoothLEDevice con el tipo anunciado.")
        return 3
    try:
        print(f"DISPOSITIVO: {device.name} enlace={device.connection_status.name}", flush=True)
        session = await GattSession.from_device_id_async(device.bluetooth_device_id)
        if session is None:
            print("SIN_SESION: Windows no entrego GattSession.")
            return 3
        try:
            if not session.can_maintain_connection:
                print("SIN_SOPORTE: CanMaintainConnection=false.")
                return 3
            emit = lambda message: print(message, flush=True)
            on_active = (lambda: check_hid_access(device, BluetoothCacheMode.UNCACHED, emit)) if check_hid else None
            return await monitor(session, emit=emit, on_active=on_active)
        finally:
            session.close()
    finally:
        device.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="direccion Bluetooth en formato AA:BB:CC:DD:EE:FF")
    parser.add_argument("--check-hid", action="store_true",
                        help="al activar GATT, comprobar acceso al servicio HID y enumerar caracteristicas")
    args = parser.parse_args()
    address = None
    if args.address:
        try:
            address = int(args.address.replace(":", ""), 16)
            if not 0 <= address < 2**48:
                raise ValueError()
        except ValueError:
            parser.error("direccion Bluetooth invalida")
    try:
        return asyncio.run(run(address, args.check_hid))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ERROR_SESION: {type(exc).__name__}: {exc}", flush=True)
        return 4


if __name__ == "__main__":
    sys.exit(main())
