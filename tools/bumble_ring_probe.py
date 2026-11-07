"""Prueba SIN TESTSIGNING: habla con el JX-05 desde modo usuario con Bumble (HCI por USB).

Requiere que el adaptador USB indicado este asignado a WinUSB (Windows ya no lo
usara). NO ejecutar sobre el adaptador principal si necesitas Bluetooth.
Uso: venv-bumble\\Scripts\\python tools\\bumble_ring_probe.py usb:0 B7:FC:01:C6:F3:7E [segundos]
Solo lee el Report Map y escucha notificaciones; no escribe en el anillo salvo el CCCD.
"""
import asyncio
import os
import sys
from pathlib import Path

# Bumble carga el firmware Realtek desde aqui (ver tools/get_rtk_firmware.py).
os.environ.setdefault("BUMBLE_RTK_FIRMWARE_DIR", str(Path(__file__).resolve().parents[1] / ".jx05-monitor" / "rtk-firmware"))

from bumble.core import ProtocolError
from bumble.device import Device, Peer
from bumble.hci import HCI_REMOTE_USER_TERMINATED_CONNECTION_ERROR
from bumble.transport import open_transport

HID, REPORT, REPORT_MAP = "1812", "2A4D", "2A4B"


async def main(transport, address, seconds):
    async with await open_transport(transport) as (source, sink):
        device = Device.with_hci("probe", "F0:F1:F2:F3:F4:F5", source, sink)
        await device.power_on()
        for attempt in range(3):  # shortcut: el descubrimiento GATT a veces no responde; reintento simple.
            connection = await device.connect(f"{address}/P")
            print("CONECTADO", connection, flush=True)  # MTU ATT queda en 23: no se solicita otro.
            peer = Peer(connection)
            try:
                await asyncio.wait_for(peer.discover_all(), 15)
                break
            except (asyncio.TimeoutError, asyncio.CancelledError):
                print(f"SIN_RESPUESTA_GATT intento {attempt + 1}/3; reconectando", flush=True)
                await connection.disconnect(HCI_REMOTE_USER_TERMINATED_CONNECTION_ERROR)
                await asyncio.sleep(2)
        else:
            print("GATT_NO_RESPONDE tras 3 intentos"); return 4
        maps = [c for s in peer.services if str(s.uuid).upper().endswith(HID) or s.uuid.to_hex_str() == HID
                for c in s.characteristics if c.uuid.to_hex_str() == REPORT_MAP]
        if not maps:
            print("SIN_REPORT_MAP: el servicio HID no se enumero"); return 2
        try:
            data = await peer.read_value(maps[0])
        except ProtocolError as error:  # shortcut: sin SMP automatico; si pide cifrado, ejecutar connection.pair() y reintentar.
            print("LECTURA_RECHAZADA", error); return 3
        print(f"REPORT_MAP bytes={len(data)} hex={data.hex()}", flush=True)
        for service in peer.services:
            for char in service.characteristics:
                if char.uuid.to_hex_str() == REPORT:
                    await peer.discover_descriptors(char)  # sin esto no hay CCCD y subscribe() no activa notificaciones
                    await peer.subscribe(char, lambda v, h=char.handle: print(f"REPORT handle=0x{h:04x} hex={v.hex()}", flush=True))
        print(f"ESCUCHANDO {seconds}s: pulsa botones", flush=True)
        await asyncio.sleep(seconds)
        await connection.disconnect(HCI_REMOTE_USER_TERMINATED_CONNECTION_ERROR)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)))
