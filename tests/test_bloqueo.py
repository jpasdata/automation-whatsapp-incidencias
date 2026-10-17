from __future__ import annotations

import os

import pytest

from src.nucleo.bloqueo import SesionOcupada, candado_sesion


def test_candado_se_crea_y_se_limpia(tmp_path):
    ruta = tmp_path / "s.lock"
    with candado_sesion(ruta):
        assert ruta.read_text() == str(os.getpid())
    assert not ruta.exists()


def test_candado_ignora_pid_muerto_y_bloquea_si_esta_vivo(tmp_path):
    ruta = tmp_path / "s.lock"
    ruta.write_text("999999")  # pid inexistente
    with candado_sesion(ruta):
        pass
    import subprocess, sys
    hijo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        ruta.write_text(str(hijo.pid))
        with pytest.raises(SesionOcupada):
            with candado_sesion(ruta):
                pass
    finally:
        hijo.kill()
