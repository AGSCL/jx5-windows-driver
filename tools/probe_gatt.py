"""Prueba experimental de acceso GATT al JX-05 en Windows.

Requiere: python -m pip install "bleak>=1,<3"
No traduce botones ni instala un controlador. Windows puede iniciar su propio
controlador HID al conectar, aunque este programa no lea Report Map.
"""
import argparse
import asyncio
import sys

HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"
REPORT = "00002a4d-0000-1000-8000-00805f9b34fb"


async def probe(scanner, client_factory, *, name="JX-05", address=None,
                scan_seconds=15, listen_seconds=60, emit=print):
    emit("BUSCANDO: enciende el anillo y desconectalo del telefono.")
    found = await scanner.discover(timeout=scan_seconds, return_adv=True)
    candidates = []
    for device, advertisement in found.values():
        if address:
            matches = device.address.casefold() == address.casefold()
        else:
            names = (device.name or "", advertisement.local_name or "")
            matches = any(value.casefold() == name.casefold() for value in names)
        if matches:
            candidates.append(device)
    if not candidates:
        emit("NO_DETECTADO: el escaneo no encontro el anillo. No demuestra un fallo HID.")
        return 2
    if len(candidates) > 1:
        emit("VARIOS_DISPOSITIVOS: usa --address con la direccion del anillo deseado.")
        for device in candidates:
            emit(f"Candidato: {device.name} {device.address}")
        return 2
    disconnected = asyncio.Event()
    loop = asyncio.get_running_loop()
    count = 0

    def on_disconnect(_):
        loop.call_soon_threadsafe(disconnected.set)

    def on_report(characteristic, data):
        nonlocal count
        count += 1
        emit(f"INFORME handle=0x{characteristic.handle:04x} bytes={bytes(data).hex(' ')}")

    emit("CONECTANDO: Windows enumerara los servicios del dispositivo.")
    async with client_factory(candidates[0], timeout=25,
                              disconnected_callback=on_disconnect) as client:
        services = list(client.services)
        hid_services = [s for s in services if s.uuid.lower() == HID_SERVICE]
        if not hid_services:
            emit("HID_NO_VISIBLE: Windows no expuso el servicio 1812 a esta aplicacion.")
            emit("Esto puede indicar una restriccion del sistema; no confirma por si solo la causa.")
            return 3
        reports = [c for s in hid_services for c in s.characteristics
                   if c.uuid.lower() == REPORT
                   and any(p in c.properties for p in ("notify", "indicate"))]
        if not reports:
            emit("SIN_REPORTES: no hay caracteristicas Report con notificaciones accesibles.")
            return 3
        subscribed = 0
        for characteristic in reports:
            try:
                await client.start_notify(characteristic, on_report)
                subscribed += 1
            except Exception as exc:
                emit(f"ERROR_SUSCRIPCION handle=0x{characteristic.handle:04x}: {exc}")
        if not subscribed:
            return 4
        emit("ESCUCHANDO: pulsa cada boton por separado.")
        try:
            await asyncio.wait_for(disconnected.wait(), timeout=listen_seconds)
        except asyncio.TimeoutError:
            pass
        if disconnected.is_set() or not client.is_connected:
            emit(f"DESCONECTADO: informes={count}")
            return 4
        emit(f"FINALIZADO: informes={count}")
        return 0 if count else 5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="direccion del anillo")
    args = parser.parse_args()
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print('FALTA_BLEAK: instala con python -m pip install "bleak>=1,<3"')
        return 1
    try:
        return asyncio.run(probe(BleakScanner, BleakClient, address=args.address))
    except Exception as exc:
        print(f"ERROR_GATT: {exc}")
        return 4


if __name__ == "__main__":
    sys.exit(main())
