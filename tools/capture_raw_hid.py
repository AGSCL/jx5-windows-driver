"""Capture JX-05 Raw Input reports in a hidden window, without emitting keys."""
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import traceback

STOP = Path(__file__).resolve().parents[1] / '.jx05-monitor/raw-stop'


def reports(data):
    if len(data) < 8:
        raise ValueError('Truncated RAWHID')
    size, count = struct.unpack_from('<II', data)
    if not size or not count or size * count > len(data) - 8:
        raise ValueError('Invalid RAWHID sizes')
    return [data[8 + i * size:8 + (i + 1) * size] for i in range(count)]


def emit(event, **fields):
    print(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(), event=event, **fields)), flush=True)


def run(on_event=emit, on_tick=None, stopped=None, *, vendor_only=False):
    emit = on_event
    u, k = c.WinDLL('user32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    pointer = c.c_ssize_t
    proc_type = c.WINFUNCTYPE(pointer, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

    class WindowClass(c.Structure):
        _fields_ = [('size', w.UINT), ('style', w.UINT), ('proc', proc_type),
                    ('class_extra', c.c_int), ('window_extra', c.c_int), ('instance', w.HINSTANCE),
                    ('icon', w.HANDLE), ('cursor', w.HANDLE), ('background', w.HANDLE),
                    ('menu', w.LPCWSTR), ('name', w.LPCWSTR), ('small_icon', w.HANDLE)]

    class Device(c.Structure):
        _fields_ = [('page', w.USHORT), ('usage', w.USHORT), ('flags', w.DWORD), ('target', w.HWND)]

    class Header(c.Structure):
        _fields_ = [('kind', w.DWORD), ('size', w.DWORD), ('device', w.HANDLE), ('param', w.WPARAM)]

    def api(dll, name, result, args):
        fn = getattr(dll, name); fn.restype = result; fn.argtypes = args
        return fn

    api(k, 'CreateMutexW', w.HANDLE, [c.c_void_p, w.BOOL, w.LPCWSTR])
    api(k, 'CloseHandle', w.BOOL, [w.HANDLE])
    api(k, 'GetModuleHandleW', w.HMODULE, [w.LPCWSTR])
    api(u, 'DefWindowProcW', pointer, [w.HWND, w.UINT, w.WPARAM, w.LPARAM])
    api(u, 'RegisterClassExW', w.ATOM, [c.POINTER(WindowClass)])
    api(u, 'CreateWindowExW', w.HWND, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
        c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p])
    api(u, 'GetRawInputData', w.UINT, [w.HANDLE, w.UINT, c.c_void_p, c.POINTER(w.UINT), w.UINT])
    api(u, 'GetRawInputDeviceInfoW', w.UINT, [w.HANDLE, w.UINT, c.c_void_p, c.POINTER(w.UINT)])
    api(u, 'RegisterRawInputDevices', w.BOOL, [c.POINTER(Device), w.UINT, w.UINT])
    api(u, 'SetTimer', c.c_size_t, [w.HWND, c.c_size_t, w.UINT, c.c_void_p])
    api(u, 'GetMessageW', w.BOOL, [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT])
    api(u, 'DispatchMessageW', pointer, [c.POINTER(w.MSG)])
    api(u, 'DestroyWindow', w.BOOL, [w.HWND])
    api(u, 'UnregisterClassW', w.BOOL, [w.LPCWSTR, w.HINSTANCE])
    names = {}
    failed = False

    @proc_type
    def callback(hwnd, msg, wp, lp):
        nonlocal failed
        try:
            if msg == 0x00ff:
                size = w.UINT()
                if u.GetRawInputData(lp, 0x10000003, None, c.byref(size), c.sizeof(Header)) == 0xffffffff:
                    raise c.WinError(c.get_last_error())
                if not c.sizeof(Header) <= size.value <= 65536:
                    raise ValueError('Invalid RAWINPUT size')
                buf = c.create_string_buffer(size.value)
                got = u.GetRawInputData(lp, 0x10000003, buf, c.byref(size), c.sizeof(Header))
                if got == 0xffffffff or got < c.sizeof(Header):
                    raise c.WinError(c.get_last_error())
                head = Header.from_buffer(buf)
                if head.kind == 2:
                    if head.device not in names:
                        length = w.UINT()
                        if u.GetRawInputDeviceInfoW(head.device, 0x20000007, None, c.byref(length)) == 0xffffffff:
                            return u.DefWindowProcW(hwnd, msg, wp, lp)
                        name = c.create_unicode_buffer(length.value + 1)
                        if u.GetRawInputDeviceInfoW(head.device, 0x20000007, name, c.byref(length)) == 0xffffffff:
                            return u.DefWindowProcW(hwnd, msg, wp, lp)
                        names[head.device] = name.value
                    name = names[head.device]
                    if 'b7fc01c6f37e' in name.lower():
                        for report in reports(buf.raw[c.sizeof(Header):got]):
                            emit('report', device=name, hex=report.hex())
            elif msg == 0x00fe:
                names.clear()
                emit('device_change')
            elif msg == 0x0113:
                if on_tick: on_tick()
                if stopped() if stopped else STOP.exists():
                    u.PostQuitMessage(0)
        except Exception:
            failed = True
            emit('error', detail=traceback.format_exc())
            u.PostQuitMessage(1)
        return u.DefWindowProcW(hwnd, msg, wp, lp)

    mutex = k.CreateMutexW(None, False, 'Local\\JX05RawCapture')
    if not mutex:
        raise c.WinError(c.get_last_error())
    if c.get_last_error() == 183:
        k.CloseHandle(mutex)
        raise RuntimeError('Raw capture already running')
    hwnd = None
    registered = False
    instance = k.GetModuleHandleW(None)
    class_name = 'JX05RawCapture'
    try:
        STOP.unlink(missing_ok=True)
        wc = WindowClass(size=c.sizeof(WindowClass), proc=callback, instance=instance, name=class_name)
        if not u.RegisterClassExW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        registered = True
        hwnd = u.CreateWindowExW(0, class_name, '', 0, 0, 0, 0, 0, w.HWND(-3), None, instance, None)
        if not hwnd:
            raise c.WinError(c.get_last_error())
        usages = [(0xff00, 1)] if vendor_only else [(12, 1), (13, 4), (0xff00, 1)]
        devices = (Device * len(usages))(*(Device(page, usage, 0x2100, hwnd) for page, usage in usages))
        if not u.RegisterRawInputDevices(devices, len(devices), c.sizeof(Device)):
            raise c.WinError(c.get_last_error())
        if not u.SetTimer(hwnd, 1, 500, None):
            raise c.WinError(c.get_last_error())
        emit('ready', pid=os.getpid(), vendor_only=vendor_only)
        msg = w.MSG()
        while True:
            result = u.GetMessageW(c.byref(msg), None, 0, 0)
            if result == -1:
                raise c.WinError(c.get_last_error())
            if not result:
                break
            u.DispatchMessageW(c.byref(msg))
        emit('stopped', failed=failed)
        return int(failed)
    finally:
        if hwnd: u.DestroyWindow(hwnd)
        if registered: u.UnregisterClassW(class_name, instance)
        k.CloseHandle(mutex)


if __name__ == '__main__':
    raise SystemExit(run())
