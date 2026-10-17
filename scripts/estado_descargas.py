#!/usr/bin/env python3
"""Muestra qué se descargó y qué no (en disco, fallas con su motivo y pendientes). Uso: python scripts/estado_descargas.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datos.estado_descargas import resumen  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(resumen())
