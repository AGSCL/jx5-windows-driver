"""Consulta GATT nativo; references lee solo Report Reference desde la cache de Windows."""
import ctypes as c
from ctypes import wintypes as w
from uuid import UUID


class Guid(c.Structure):
    _fields_ = [("a", c.c_uint32), ("b", c.c_uint16), ("d", c.c_uint16), ("tail", c.c_ubyte * 8)]


class UuidValue(c.Union):
    _fields_ = [("short", c.c_uint16), ("long", Guid)]


class LeUuid(c.Structure):
    _fields_ = [("is_short", c.c_ubyte), ("value", UuidValue)]

    def text(self):
        if self.is_short:
            return f"0000{self.value.short:04x}-0000-1000-8000-00805f9b34fb"
        return str(UUID(bytes_le=bytes(self.value.long)))


class Service(c.Structure):
    _fields_ = [("uuid", LeUuid), ("handle", c.c_uint16)]


class Characteristic(c.Structure):
    _fields_ = [("service", c.c_uint16), ("uuid", LeUuid),
                ("handle", c.c_uint16), ("value_handle", c.c_uint16)] + [
        (name, c.c_ubyte) for name in ("broadcast", "read", "write", "write_no_response",
                                      "signed_write", "notify", "indicate", "extended")]


class Registration(c.Structure):
    _fields_ = [("count", c.c_uint16), ("chars", Characteristic * 1)]


class Descriptor(c.Structure):
    _fields_ = [("service", c.c_uint16), ("characteristic", c.c_uint16),
                ("kind", c.c_int32), ("uuid", LeUuid), ("handle", c.c_uint16)]


class CharacteristicFormat(c.Structure):
    _fields_ = [("format", c.c_ubyte), ("exponent", c.c_ubyte), ("unit", LeUuid),
                ("namespace", c.c_ubyte), ("description", LeUuid)]


class DescriptorValue(c.Structure):
    # CharacteristicFormat is the largest member of the native anonymous union.
    _fields_ = [("kind", c.c_int32), ("uuid", LeUuid), ("union", CharacteristicFormat),
                ("data_size", c.c_uint32), ("data", c.c_ubyte * 1)]


def parse_report_reference(raw):
    end = DescriptorValue.data.offset
    if len(raw) < end + 2:
        raise ValueError("Truncated descriptor value")
    value = DescriptorValue.from_buffer_copy(raw.ljust(c.sizeof(DescriptorValue), b"\0"))
    if (value.kind != 6 or value.uuid.text() != "00002908-0000-1000-8000-00805f9b34fb"
            or value.data_size != 2):
        raise ValueError("Not a two-byte Report Reference")
    report_id, report_type = raw[end:end + 2]
    if report_type not in (1, 2, 3):
        raise ValueError("Invalid Report Reference type")
    return report_id, report_type


def read_report_references(api, handle, chars, emit):
    api.BluetoothGATTGetDescriptors.argtypes = [w.HANDLE, c.POINTER(Characteristic), c.c_uint16,
                                               c.POINTER(Descriptor), c.POINTER(c.c_uint16), w.ULONG]
    api.BluetoothGATTGetDescriptors.restype = c.c_int32
    api.BluetoothGATTGetDescriptorValue.argtypes = [w.HANDLE, c.POINTER(Descriptor), w.ULONG,
                                                   c.c_void_p, c.POINTER(c.c_uint16), w.ULONG]
    api.BluetoothGATTGetDescriptorValue.restype = c.c_int32
    results = []
    for char in chars:
        if char.uuid.text() != "00002a4d-0000-1000-8000-00805f9b34fb":
            continue
        descriptors = query_array(api.BluetoothGATTGetDescriptors, (handle, c.byref(char)),
                                  Descriptor, emit, f"DESCRIPTORES_0x{char.value_handle:04x}")
        refs = [d for d in descriptors or [] if d.uuid.text() == "00002908-0000-1000-8000-00805f9b34fb"]
        if len(refs) != 1:
            emit(f"REFERENCIA_NO_UNICA: report=0x{char.value_handle:04x} cantidad={len(refs)}")
            continue
        descriptor = refs[0]
        required = c.c_uint16()
        # FORCE_READ_FROM_CACHE: no device read and no CCCD writes.
        hr = api.BluetoothGATTGetDescriptorValue(handle, c.byref(descriptor), 0, None,
                                                c.byref(required), 8) & 0xFFFFFFFF
        emit(f"REFERENCIA_CACHE: report=0x{char.value_handle:04x} descriptor=0x{descriptor.handle:04x} HRESULT=0x{hr:08x}")
        if hr not in (0, 0x800700EA) or required.value < DescriptorValue.data.offset + 2:
            continue
        buf = c.create_string_buffer(required.value)
        hr = api.BluetoothGATTGetDescriptorValue(handle, c.byref(descriptor), len(buf), buf,
                                                c.byref(required), 8) & 0xFFFFFFFF
        if hr or required.value > len(buf):
            emit(f"REFERENCIA_ERROR: HRESULT=0x{hr:08x}")
            continue
        report_id, report_type = parse_report_reference(buf.raw)
        emit(f"REPORT_REFERENCE: report=0x{char.value_handle:04x} descriptor=0x{descriptor.handle:04x} id={report_id} tipo={report_type} fuente=cache")
        results.append((char.value_handle, report_id, report_type))
    return results


CALLBACK = c.WINFUNCTYPE(None, c.c_int, c.c_void_p, c.c_void_p)
_pending_callbacks = []


def try_register(api, handle, chars, emit):
    """Prueba la precondicion de suscripcion; aun no escribe el CCCD."""
    api.BluetoothGATTRegisterEvent.argtypes = [w.HANDLE, c.c_int, c.POINTER(Registration), CALLBACK,
                                              c.c_void_p, c.POINTER(w.HANDLE), w.ULONG]
    api.BluetoothGATTRegisterEvent.restype = c.c_int32
    api.BluetoothGATTUnregisterEvent.argtypes = [w.HANDLE, w.ULONG]
    api.BluetoothGATTUnregisterEvent.restype = c.c_int32
    callback = CALLBACK(lambda *_: emit("EVENTO_NATIVO: callback recibido durante registro."))
    accepted = 0
    for char in chars:
        if char.uuid.text() != "00002a4d-0000-1000-8000-00805f9b34fb" or not (char.notify or char.indicate):
            continue
        registration = Registration(1, (Characteristic * 1)(char))
        event = w.HANDLE()
        hr = api.BluetoothGATTRegisterEvent(handle, 0, c.byref(registration), callback,
                                           None, c.byref(event), 0) & 0xFFFFFFFF
        emit(f"REGISTRO_REPORT: handle=0x{char.value_handle:04x} HRESULT=0x{hr:08x}")
        if hr == 0:
            accepted += 1
            cleanup = api.BluetoothGATTUnregisterEvent(event, 0) & 0xFFFFFFFF
            emit(f"LIBERAR_REGISTRO: HRESULT=0x{cleanup:08x}")
            if cleanup:
                # Mantener vivo el callback mientras Windows pueda invocarlo.
                _pending_callbacks.append((callback, registration))
    emit(f"REGISTROS_ACEPTADOS: {accepted}; CCCD aun no modificado.")
    return accepted


def interfaces(cfg, guid):
    raw = Guid.from_buffer_copy(UUID(guid).bytes_le)
    for _ in range(3):
        count = w.ULONG()
        status = cfg.CM_Get_Device_Interface_List_SizeW(c.byref(count), c.byref(raw), None, 0)
        if status:
            raise RuntimeError(f"CM_Get_Device_Interface_List_SizeW: CONFIGRET=0x{status:08x}")
        buf = c.create_unicode_buffer(count.value)
        status = cfg.CM_Get_Device_Interface_ListW(c.byref(raw), None, buf, count.value, 0)
        if status == 0:
            return [path for path in buf[:].split("\0") if path]
        if status != 0x1A:  # CR_BUFFER_SMALL: la lista cambio durante la consulta.
            raise RuntimeError(f"CM_Get_Device_Interface_ListW: CONFIGRET=0x{status:08x}")
    raise RuntimeError("La lista de interfaces cambio tres veces.")


def query_array(func, args, item_type, emit, label):
    count = c.c_uint16()
    hr = func(*args, 0, None, c.byref(count), 0) & 0xFFFFFFFF
    emit(f"{label}_TAMANO: HRESULT=0x{hr:08x} elementos={count.value}")
    if hr == 0 and count.value == 0:
        return []
    if hr not in (0, 0x800700EA) or not count.value:
        return None
    capacity = count.value
    buf = (item_type * capacity)()
    hr = func(*args, capacity, buf, c.byref(count), 0) & 0xFFFFFFFF
    emit(f"{label}: HRESULT=0x{hr:08x} elementos={count.value}")
    if hr or count.value > capacity:
        return None
    return list(buf[:count.value])


def probe(address, emit=print, register=False, references=False):
    if register and references:
        raise ValueError("Registro y lectura de referencias son pruebas separadas")
    cfg = c.WinDLL("cfgmgr32")
    cfg.CM_Get_Device_Interface_List_SizeW.argtypes = [c.POINTER(w.ULONG), c.POINTER(Guid), w.LPCWSTR, w.ULONG]
    cfg.CM_Get_Device_Interface_ListW.argtypes = [c.POINTER(Guid), w.LPCWSTR, w.LPWSTR, w.ULONG, w.ULONG]
    cfg.CM_Get_Device_Interface_List_SizeW.restype = w.ULONG
    cfg.CM_Get_Device_Interface_ListW.restype = w.ULONG
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    api = c.WinDLL("BluetoothApis")
    api.BluetoothGATTGetServices.argtypes = [w.HANDLE, c.c_uint16, c.POINTER(Service), c.POINTER(c.c_uint16), w.ULONG]
    api.BluetoothGATTGetServices.restype = c.c_int32
    api.BluetoothGATTGetCharacteristics.argtypes = [w.HANDLE, c.POINTER(Service), c.c_uint16, c.POINTER(Characteristic), c.POINTER(c.c_uint16), w.ULONG]
    api.BluetoothGATTGetCharacteristics.restype = c.c_int32
    target = f"{address:012x}"
    success = False
    accepted = 0
    expected_refs, received_refs = set(), set()
    for label, guid in (("DISPOSITIVO", "781aee18-7733-4ce4-add0-91f41c67b592"),
                        ("SERVICIO", "6e3bb679-4372-40c8-9eaa-4509df260cd8"),
                        ("HID", "00001812-0000-1000-8000-00805f9b34fb")):
        if references and label != "HID":
            continue
        paths = [path for path in interfaces(cfg, guid) if target in path.lower()]
        if label == "SERVICIO":
            paths = [path for path in paths if "00001812-0000-1000-8000-00805f9b34fb" in path.lower()]
        emit(f"INTERFACES_{label}: {len(paths)}")
        for path in paths:
            emit(f"INTERFAZ: {path}")
            # El registro se prueba con lectura/escritura; enumerar solo requiere lectura.
            access = 0 if references else (0xC0000000 if register else 0x80000000)
            handle = kernel.CreateFileW(path, access, 3, None, 3, 0, None)
            if handle == c.c_void_p(-1).value:
                error = c.get_last_error()
                emit(f"APERTURA_{label}: WIN32={error} {c.FormatError(error).strip()}")
                continue
            try:
                emit(f"APERTURA_{label}: OK")
                if label == "DISPOSITIVO":
                    services = query_array(api.BluetoothGATTGetServices, (handle,), Service, emit, "SERVICIOS")
                    if services is None:
                        continue
                    parents = [c.byref(service) for service in services
                               if service.uuid.text() == "00001812-0000-1000-8000-00805f9b34fb"]
                    emit(f"SERVICIOS_HID: {len(parents)}")
                else:
                    parents = [None]
                for parent in parents:
                    chars = query_array(api.BluetoothGATTGetCharacteristics, (handle, parent), Characteristic, emit, "CARACTERISTICAS_HID")
                    if chars:
                        success = True
                        for char in chars:
                            emit(f"CARACTERISTICA: uuid={char.uuid.text()} handle=0x{char.value_handle:04x} notify={char.notify} indicate={char.indicate}")
                        if register:
                            emit(f"PRUEBA_REGISTRO: handle de {label}; la API documenta handle de servicio.")
                            accepted += try_register(api, handle, chars, emit)
                        if references:
                            expected_refs.update(char.value_handle for char in chars
                                                 if char.uuid.text() == "00002a4d-0000-1000-8000-00805f9b34fb")
                            received_refs.update(row[0] for row in read_report_references(api, handle, chars, emit))
            finally:
                kernel.CloseHandle(handle)
    if references:
        emit(f"REFERENCIAS_LEIDAS: {len(received_refs)}/{len(expected_refs)} fuente=cache; no es captura ATT")
        return 0 if expected_refs and received_refs == expected_refs else 4
    if register:
        emit("REGISTRO_POSIBLE_CCCD_PENDIENTE" if accepted else "REGISTRO_NO_DISPONIBLE: no se habilitaron notificaciones.")
        return 0 if accepted else 4
    emit("HID_NATIVO_ENUMERADO" if success else "HID_NATIVO_NO_ENUMERADO: revisar la etapa anterior; no implica una causa unica.")
    return 0 if success else 3
