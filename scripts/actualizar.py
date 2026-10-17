#!/usr/bin/env python3
"""
Actualización incremental (para la tarea programada cada hora): trae solo lo NUEVO de los
grupos de config.yaml al índice local, sin volver a subir el histórico.

Uso:
    python scripts/actualizar.py
    python scripts/actualizar.py --grupo Veraguas
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nucleo.bloqueo import SesionOcupada, candado_sesion  # noqa: E402
from src.nucleo.config import load_config  # noqa: E402
from src.datos.historico import actualizar_incremental  # noqa: E402
from src.nucleo.logger import setup_logger  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título de un solo grupo")
args = ap.parse_args()

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
grupos = [g for g in cfg.whatsapp.grupos if not args.grupo or args.grupo.lower() in g.lower()]

try:
    with candado_sesion():
        logger.info("=== Actualización incremental: %d grupo(s) ===", len(grupos))
        actualizar_incremental(cfg, grupos, logger)
except SesionOcupada as e:
    sys.exit(str(e))
