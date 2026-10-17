#!/usr/bin/env python3
"""Analiza cómo reportan evidencias las personas de un grupo (desde el índice local). Uso: python scripts/analizar_comportamiento.py [--grupo X]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nucleo.rutas import R  # noqa: E402
from src.cruce.comportamiento import analizar, informe  # noqa: E402
from src.datos.historico import RUTA_INDICE  # noqa: E402
from src.datos.indice import Indice  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--grupo", help="fragmento del título; por defecto todos los indexados")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
with Indice(RUTA_INDICE) as ix:
    for g in ix.grupos():
        if args.grupo and args.grupo.lower() not in g.lower():
            continue
        texto = informe(analizar(ix.mensajes(g)), g)
        salida = R.reportes_analisis / f"comportamiento_{''.join(c if c.isalnum() else '_' for c in g)[:40]}.md"
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(texto, encoding="utf-8")
        print(texto)
        print(f"\n(guardado en {salida})")
