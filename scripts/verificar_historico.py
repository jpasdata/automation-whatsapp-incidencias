#!/usr/bin/env python3
"""
Muestra, sin abrir WhatsApp, qué histórico hay cargado en el índice local:
mensajes y fotos por día, desde cuándo hay datos y qué días faltan.

Uso:
    python scripts/verificar_historico.py             # todos los grupos indexados
    python scripts/verificar_historico.py --grupo Veraguas
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, resolver_cargar_desde  # noqa: E402
from src.historico import RUTA_INDICE, verificar_historico  # noqa: E402
from src.indice import Indice  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título del grupo")
args = ap.parse_args()

cfg = load_config()
desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
if desde is None:
    sys.exit("whatsapp.cargar_desde está vacío en config.yaml.")

with Indice(RUTA_INDICE) as indice:
    grupos = [g for g in indice.grupos() if not args.grupo or args.grupo.lower() in g.lower()]
    if not grupos:
        print("El índice está vacío. Corre primero: python scripts/cargar_historico.py")
    for g in grupos:
        print(verificar_historico(indice, g, desde))
        print()
