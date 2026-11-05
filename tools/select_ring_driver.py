"""Inspecciona o selecciona un controlador instalado para una instancia HID del JX-05.

Por defecto solo inspecciona. --apply generic o --apply restore cambian la
asociacion de esa instancia mediante DiInstallDevice y requieren administrador.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import ntpath
import re
from probe_native_gatt import Guid


class DeviceInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("guid", Guid), ("devinst", w.DWORD), ("reserved", c.c_size_t)]


class DriverInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("type", w.DWORD), ("reserved", c.c_size_t),
                ("description", c.c_wchar * 256), ("manufacturer", c.c_wchar * 256),
                ("provider", c.c_wchar * 256), ("date", w.FILETIME), ("version", c.c_uint64)]


class DriverDetail(c.Structure):
    _fields_ = [("size", w.DWORD), ("date", w.FILETIME), ("offset", w.DWORD),
                ("length", w.DWORD), ("reserved", c.c_size_t),
                ("section", c.c_wchar * 256), ("inf", c.c_wchar * 260),
                ("description", c.c_wchar * 256), ("hardware", c.c_wchar * 1)]


def validate_instance(instance):
    prefix = (r"BTHLEDEVICE\{00001812-0000-1000-8000-00805F9B34FB}"
              "_DEV_VID&0105AC_PID&0220_REV&0110_B7FC01C6F37E\\")
    if not re.fullmatch(re.escape(prefix) + r"[^\\]+", instance, re.IGNORECASE):
        raise ValueError("La instancia no corresponde al servicio HID de este JX-05.")


def check(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


def select(instance, action=None):
    validate_instance(instance)
    setup = c.WinDLL("setupapi", use_last_error=True)
    setup.SetupDiCreateDeviceInfoList.argtypes = [c.POINTER(Guid), w.HWND]
    setup.SetupDiCreateDeviceInfoList.restype = w.HANDLE
    setup.SetupDiOpenDeviceInfoW.argtypes = [w.HANDLE, w.LPCWSTR, w.HWND, w.DWORD, c.POINTER(DeviceInfo)]
    setup.SetupDiOpenDeviceInfoW.restype = w.BOOL
    setup.SetupDiBuildDriverInfoList.argtypes = [w.HANDLE, c.POINTER(DeviceInfo), w.DWORD]
    setup.SetupDiBuildDriverInfoList.restype = w.BOOL
    setup.SetupDiEnumDriverInfoW.argtypes = [w.HANDLE, c.POINTER(DeviceInfo), w.DWORD, w.DWORD, c.POINTER(DriverInfo)]
    setup.SetupDiEnumDriverInfoW.restype = w.BOOL
    setup.SetupDiGetDriverInfoDetailW.argtypes = [w.HANDLE, c.POINTER(DeviceInfo), c.POINTER(DriverInfo), c.POINTER(DriverDetail), w.DWORD, c.POINTER(w.DWORD)]
    setup.SetupDiGetDriverInfoDetailW.restype = w.BOOL
    setup.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]
    setup.SetupDiDestroyDeviceInfoList.restype = w.BOOL
    devices = setup.SetupDiCreateDeviceInfoList(None, None)
    if devices == c.c_void_p(-1).value:
        check(False)
    try:
        device = DeviceInfo()
        device.size = c.sizeof(device)
        check(setup.SetupDiOpenDeviceInfoW(devices, instance, None, 0, c.byref(device)))
        check(setup.SetupDiBuildDriverInfoList(devices, c.byref(device), 2))
        candidates = {}
        index = 0
        while True:
            driver = DriverInfo()
            driver.size = c.sizeof(driver)
            if not setup.SetupDiEnumDriverInfoW(devices, c.byref(device), 2, index, c.byref(driver)):
                if c.get_last_error() == 259:
                    break
                check(False)
            detail = DriverDetail()
            detail.size = c.sizeof(detail)
            required = w.DWORD()
            ok = setup.SetupDiGetDriverInfoDetailW(devices, c.byref(device), c.byref(driver),
                                                  c.byref(detail), c.sizeof(detail), c.byref(required))
            # ERROR_INSUFFICIENT_BUFFER deja validos los campos fijos (documentado).
            if not ok and c.get_last_error() != 122:
                check(False)
            name = ntpath.basename(detail.inf).lower()
            print(f"CANDIDATO: {name} seccion={detail.section} proveedor={driver.provider}", flush=True)
            if (name, detail.section.lower()) in (("hidbthle.inf", "hidbthle"),
                                                  ("bthleenum.inf", "attgenericservice")):
                if name in candidates:
                    raise RuntimeError("Candidatos ambiguos; no se cambiara el controlador.")
                candidates[name] = driver
            index += 1
        if set(candidates) != {"hidbthle.inf", "bthleenum.inf"}:
            raise RuntimeError("No estan disponibles ambos candidatos: cambio y restauracion no preparados.")
        print(f"INSTANCIA_VERIFICADA: {instance}", flush=True)
        if action is None:
            print("PREPARADO: generic=bthleenum.inf; restore=hidbthle.inf. Sin cambios.")
            return
        native = c.WinDLL("newdev", use_last_error=True)
        native.DiInstallDevice.argtypes = [w.HWND, w.HANDLE, c.POINTER(DeviceInfo), c.POINTER(DriverInfo), w.DWORD, c.POINTER(w.BOOL)]
        native.DiInstallDevice.restype = w.BOOL
        target = "bthleenum.inf" if action == "generic" else "hidbthle.inf"
        reboot = w.BOOL()
        print(f"SELECCIONANDO: {target}", flush=True)
        check(native.DiInstallDevice(None, devices, c.byref(device), c.byref(candidates[target]), 0, c.byref(reboot)))
        print(f"INSTALACION_ACEPTADA: {target} requiere_reinicio={bool(reboot.value)}. Verificar estado PnP.")
    finally:
        setup.SetupDiDestroyDeviceInfoList(devices)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--apply", choices=("generic", "restore"))
    args = parser.parse_args()
    try:
        select(args.instance, args.apply)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
