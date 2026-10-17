#!/usr/bin/env python3
"""
Modo manual asistido: abre el grupo en Chromium y SOLO MIRA mientras tú haces
scroll con el mouse (bajar mucho y volver a subir hace que WhatsApp Web pida más
mensajes antiguos). Todo lo que aparece se guarda en el índice local.

Uso:
    python scripts/capturar_manual.py                 # primer grupo de config.yaml
    python scripts/capturar_manual.py --minutos 60
    python scripts/capturar_manual.py --grupo "Oeste"

Termina al cerrar la ventana de Chromium, al llegar a cargar_desde o al agotar el tiempo.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nucleo.config import load_config, resolver_cargar_desde  # noqa: E402
from src.datos.historico import RUTA_INDICE, capturar_mientras_scrollea, verificar_historico  # noqa: E402
from src.datos.indice import Indice  # noqa: E402
from src.nucleo.logger import setup_logger  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título del grupo (default: el primero de config.yaml)")
ap.add_argument("--minutos", type=int, default=60, help="Tiempo máximo (default 60)")
ap.add_argument("--grabar", action="store_true", help="Graba también los eventos de tu mouse (logs/scroll_manual.json)")
args = ap.parse_args()

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
grupo = args.grupo or cfg.whatsapp.grupos[0]
desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
if desde is None:
    sys.exit("whatsapp.cargar_desde está vacío en config.yaml.")

logger.info("=== Captura manual: '%s' desde %s (máx. %d min) ===", grupo, desde.date(), args.minutos)
capturar_mientras_scrollea(cfg, grupo, desde, args.minutos, logger, grabar_eventos=args.grabar)

with Indice(RUTA_INDICE) as indice:
    print()
    print(verificar_historico(indice, grupo, desde))
