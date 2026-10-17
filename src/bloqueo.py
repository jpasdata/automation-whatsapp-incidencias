"""
Candado de proceso para la sesión de WhatsApp Web.

Dos procesos no pueden usar a la vez el mismo perfil de Chromium (el segundo falla o,
peor, corrompe la sesión: ya pasó una vez al cerrar a la fuerza). Este candado deja
pasar a un solo script a la vez y se limpia solo si el proceso anterior ya murió.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


class SesionOcupada(RuntimeError):
    pass


def _vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def candado_sesion(ruta: str | Path = "./sesion_whatsapp.lock"):
    """Uso: `with candado_sesion(): ...`. Lanza SesionOcupada si otro proceso vivo ya la está usando."""
    ruta = Path(ruta)
    if ruta.exists():
        try:
            pid = int(ruta.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and pid != os.getpid() and _vivo(pid):
            raise SesionOcupada(f"La sesión de WhatsApp ya la usa el proceso {pid}. Espera a que termine o ciérralo.")
    ruta.write_text(str(os.getpid()))
    try:
        yield
    finally:
        try:
            if ruta.read_text().strip() == str(os.getpid()):
                ruta.unlink()
        except OSError:
            pass
