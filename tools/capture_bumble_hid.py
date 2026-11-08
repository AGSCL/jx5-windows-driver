"""ESCENARIO B (sin driver propio): informes del JX-05 por Bumble sobre un dongle en WinUSB.

Misma interfaz que capture_raw_hid.run, para reutilizar monitor_jx05. Emite 'report' con el
ID de informe delante (como Raw Input), para que Gestures los decodifique igual.
Requiere el dongle (UB500) en WinUSB y el anillo libre; ver INVESTIGACION.md.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[1]
PACKAGED_FIRMWARE = ROOT / 'rtk-firmware'  # paquete portatil (build_app.ps1 -Bumble)
os.environ.setdefault('BUMBLE_RTK_FIRMWARE_DIR', str(
    PACKAGED_FIRMWARE if PACKAGED_FIRMWARE.is_dir() else ROOT / '.jx05-monitor' / 'rtk-firmware'))
TRANSPORT = os.environ.get('JX05_BUMBLE_TRANSPORT', 'usb:2357:0604')
ADDRESS = os.environ.get('JX05_RING_ADDRESS', 'B7:FC:01:C6:F3:7E')
HID, REPORT, REPORT_REFERENCE = '1812', '2A4D', '2908'
INPUT_REPORT = 1  # Report Reference: [id, tipo]; solo tipo 1 (Input) llega por notificacion.
DECODED_IDS = (1, 3)  # los unicos Input del Report Map; Raw Input nunca entrega 2, 4, 5 ni 6 a Gestures


def emit(event, **fields):
    print(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), event=event, **fields)), flush=True)


class NoInputReports(RuntimeError):
    """Descubrimiento GATT incompleto: se reintenta como un fallo de enlace."""


def with_report_id(reference, value):
    """Antepone el ID de informe; None si no es un Input Report que Gestures decodifique."""
    if len(reference) != 2 or reference[1] != INPUT_REPORT or reference[0] not in DECODED_IDS:
        return None
    return bytes([reference[0]]) + bytes(value)


async def relax_link(connection, on_event):
    """Enlace relajado (menos escuchas del anillo, menos bateria). Medido: el modo rapido tardaba 1.7 s
    en activarse y solo ganaba ~30 ms, asi que no se usa. Si el anillo lo rechaza, queda como esta."""
    try:  # intervalo 30-60 ms, latencia del periferico 4, timeout 2000 ms (> 2 * 5 * 60 ms)
        await asyncio.wait_for(connection.update_parameters(30, 60, 4, 2000), 5)
        on_event('link_mode', mode='relaxed')
    except Exception as exc:  # shortcut: sin reintento ni reversion
        on_event('link_mode_unavailable', detail=type(exc).__name__)


async def _session(device, on_event, stop, retry=5):
    # BaseBumbleError cubre BaseError, TimeoutError, CommandTimeoutError, InvalidStateError...
    from bumble.core import BaseBumbleError
    from bumble.device import Peer
    from bumble.transport.common import TransportLostError
    from bumble.hci import HCI_REMOTE_USER_TERMINATED_CONNECTION_ERROR

    while not stop.is_set():
        connection = None
        try:
            connection = await device.connect(f'{ADDRESS}/P', timeout=15)
            peer = Peer(connection)
            await asyncio.wait_for(peer.discover_all(), 15)  # a veces no responde: se reintenta abajo
            dropped = asyncio.Event()
            connection.on('disconnection', lambda *_: dropped.set())
            count = 0
            for service in peer.services:
                if service.uuid.to_hex_str() != HID:
                    continue
                for char in service.characteristics:
                    if char.uuid.to_hex_str() != REPORT:
                        continue
                    await peer.discover_descriptors(char)
                    ref = next((d for d in char.descriptors if d.type.to_hex_str() == REPORT_REFERENCE), None)
                    if ref is None:
                        continue
                    reference = bytes(await peer.read_value(ref))
                    if with_report_id(reference, b'') is None:
                        continue
                    await peer.subscribe(char, lambda value, r=reference: on_event(
                        'report', device=f'bumble:{ADDRESS}', hex=with_report_id(r, value).hex()))
                    count += 1
            if not count:
                raise NoInputReports('El servicio HID no ofrecio Input Reports')
            on_event('ready', backend='bumble', subscriptions=count)
            await relax_link(connection, on_event)
            stopping = asyncio.ensure_future(stop.wait())
            await asyncio.wait([stopping, asyncio.ensure_future(dropped.wait())], return_when=asyncio.FIRST_COMPLETED)
            stopping.cancel()
            if not stop.is_set():
                on_event('device_change')  # reinicia el decodificador de gestos
        except TransportLostError:
            raise  # dongle desenchufado: reintentar sobre un transporte muerto no sirve
        except (asyncio.TimeoutError, BaseBumbleError, NoInputReports, ConnectionError, OSError) as exc:
            # CancelledError no se captura: Ctrl+C y la cancelacion externa deben detener el bucle.
            if stop.is_set():
                break
            on_event('retry', detail=f'{type(exc).__name__}: {exc}')
        finally:
            if connection is not None:
                try:
                    await asyncio.wait_for(connection.disconnect(HCI_REMOTE_USER_TERMINATED_CONNECTION_ERROR), 2)
                except Exception:  # ya desconectado
                    pass
        try:
            await asyncio.wait_for(stop.wait(), retry)
        except asyncio.TimeoutError:
            pass


async def _run(on_event, on_tick, stopped):
    from bumble.device import Device
    from bumble.transport import open_transport
    from bumble.transport.common import TransportInitError, TransportLostError
    from usb1 import USBError

    stop = asyncio.Event()
    tick_failed = []

    async def ticker():
        try:
            while not stop.is_set():
                if on_tick:
                    on_tick()
                if stopped and stopped():
                    stop.set()
                await asyncio.sleep(0.5)
        except Exception:  # sin esto, una excepcion aqui deja de vigilar el archivo de parada
            tick_failed.append(True)
            on_event('error', detail=traceback.format_exc())
            stop.set()

    async def transport_session():
        # OSError al abrir USB es recuperable; el firmware ausente durante power_on no lo es.
        try:
            transport = await open_transport(TRANSPORT)
        except OSError as exc:
            raise TransportInitError(str(exc)) from exc
        async with transport as (source, sink):
            device = Device.with_hci('jx05', 'F0:F1:F2:F3:F4:F5', source, sink)
            await device.power_on()
            session = asyncio.create_task(_session(device, on_event, stop))
            try:
                done, _ = await asyncio.wait([session, source.terminated], return_when=asyncio.FIRST_COMPLETED)
                if session in done:
                    await session
                else:
                    raise TransportLostError('transporte USB terminado')
            finally:
                session.cancel()
                await asyncio.gather(session, return_exceptions=True)

    tick = asyncio.ensure_future(ticker())
    try:
        while not stop.is_set():
            task = asyncio.create_task(transport_session())
            stopping = asyncio.create_task(stop.wait())
            try:
                done, _ = await asyncio.wait([task, stopping], return_when=asyncio.FIRST_COMPLETED)
                if task in done:
                    await task
            except (TransportInitError, TransportLostError, USBError) as exc:
                if not stop.is_set():
                    on_event('device_change')
                    on_event('retry', detail=f'{type(exc).__name__}: {exc}')
                    try:
                        await asyncio.wait_for(stop.wait(), 5)
                    except asyncio.TimeoutError:
                        pass
            finally:
                task.cancel()
                stopping.cancel()
                await asyncio.gather(task, stopping, return_exceptions=True)
        on_event('stopped', failed=bool(tick_failed))
        return int(bool(tick_failed))
    except Exception:
        on_event('error', detail=traceback.format_exc())
        on_event('stopped', failed=True)
        raise  # como Raw Input: monitor_jx05 escribe startup-error.txt y sale con codigo distinto de 0
    finally:
        stop.set()
        tick.cancel()


def run(on_event=emit, on_tick=None, stopped=None, *, vendor_only=False):
    """vendor_only se acepta por compatibilidad con Raw Input y no tiene efecto aqui."""
    return asyncio.run(_run(on_event, on_tick, stopped))


if __name__ == '__main__':
    raise SystemExit(run())
