#!/usr/bin/env python3
"""
Fases 1-2 — Automatización (descarga, cruce con Excel). Sin notificación: Henry avisa por correo.

Pensado para dispararse como tarea programada. Requiere que
config/config.yaml ya esté completo (ver README, sección "Pendientes").

Uso:
    python scripts/run_automatizacion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bot.main import ejecutar_automatizacion  # noqa: E402

if __name__ == "__main__":
    ejecutar_automatizacion()
