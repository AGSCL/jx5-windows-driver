"""Prueba experimental de acceso GATT al JX-05 en Windows.

Requiere: python -m pip install "bleak>=1,<3"
No traduce botones ni instala un controlador. El sistema operativo puede iniciar
su propio controlador HID al conectar, aunque este programa no lea Report Map.
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
                # Passing the characteristic object disambiguates repeated UUIDs.
                await client.start_notify(characteristic, on_report)
                subscribed += 1
                emit(f"SUSCRITO handle=0x{characteristic.handle:04x}")
            except Exception as error:
                emit(f"SUSCRIPCION_FALLIDA handle=0x{characteristic.handle:04x}: "
                     f"{type(error).__name__}: {error}")
        if not subscribed:
            emit("ACCESO_FALLIDO: ninguna suscripcion funciono.")
            return 3
        emit(f"ESCUCHANDO {listen_seconds:g} segundos: pulsa cada boton por separado.")
        try:
            await asyncio.wait_for(disconnected.wait(), timeout=listen_seconds)
        except asyncio.TimeoutError:
            pass
        dropped = disconnected.is_set() or not client.is_connected
        emit(f"RESULTADO informes={count} desconexion_anticipada={dropped}")
        if dropped:
            emit("CONEXION_INTERRUMPIDA: el acceso no se mantuvo durante toda la prueba.")
            return 4
        if not count:
            emit("SIN_DATOS: la suscripcion funciono, pero no llegaron informes.")
            return 5
        emit("INFORMES_RECIBIDOS: hay datos para investigar el mapeo de botones.")
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="JX-05")
    parser.add_argument("--address")
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds debe ser mayor que cero")
    if sys.platform != "win32":
        parser.exit(2, "Esta prueba esta destinada a Windows 10/11.\n")
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        parser.exit(2, 'Instala la dependencia: python -m pip install "bleak>=1,<3"\n')
    try:
        return asyncio.run(probe(BleakScanner, BleakClient, name=args.name,
                                 address=args.address, listen_seconds=args.seconds))
    except KeyboardInterrupt:
        print("Prueba interrumpida.")
        return 130
    except Exception as error:
        print(f"PRUEBA_FALLIDA: {type(error).__name__}: {error}")
        print("Este error no basta para distinguir restricciones de Windows de un fallo del dispositivo.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
