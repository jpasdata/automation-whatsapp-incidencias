#!/usr/bin/env python3
"""
Fase 0 — Exploración.

Entra al grupo, lista participantes y revisa los últimos mensajes con
foto/video, SIN descargar nada ni tocar el Excel. Genera un reporte en
logs/ para decidir con datos reales el formato del código y a quién
notificar.

Uso:
    python scripts/run_exploracion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.exploracion import ejecutar_exploracion  # noqa: E402

if __name__ == "__main__":
    ejecutar_exploracion()
