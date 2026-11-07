"""Descarga y verifica el firmware Realtek RTL8761BU (p. ej. TP-Link UB500) para Bumble.

Los binarios NO se guardan en Git (carpeta .jx05-monitor/ ignorada). Origen:
linux-firmware (kernel.org). Verifica SHA-256 fijos y la firma 'Realtech'.
Uso: python tools/get_rtk_firmware.py [carpeta_destino]
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/rtl_bt/"
FILES = {  # shortcut: hashes de la versión de 2026-11-06; si linux-firmware cambia, revisar y actualizar.
    "rtl8761bu_fw.bin": "1d7a9597349ad89344fa16c1913d3e39e9a12e966e417ca16871bc79bbe59edb",
    "rtl8761bu_config.bin": "6c28a3f07c6a30ed208c4b64862a23f02b7d93543ea980edd24df16bab45095f",
}


def main(dest):
    dest.mkdir(parents=True, exist_ok=True)
    for name, digest in FILES.items():
        # kernel.org devuelve 403 al User-Agent por defecto de Python.
        request = urllib.request.Request(BASE + name, headers={"User-Agent": "curl/8"})
        data = urllib.request.urlopen(request, timeout=30).read()
        if hashlib.sha256(data).hexdigest() != digest:
            sys.exit(f"HASH_DISTINTO: {name}; no se guarda. Revisar linux-firmware.")
        if name.endswith("_fw.bin") and not data.startswith(b"Realtech"):
            sys.exit(f"FIRMA_INVALIDA: {name}")
        (dest / name).write_bytes(data)
        print(f"OK {name} {len(data)} bytes")
    print(f"Listo. Usa: set BUMBLE_RTK_FIRMWARE_DIR={dest}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / ".jx05-monitor" / "rtk-firmware")
