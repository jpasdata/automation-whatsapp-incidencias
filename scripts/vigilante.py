#!/usr/bin/env python3
"""
Bot vigilante: deja WhatsApp Web abierto todo el día, baja lo que llega (con su identificación) y reubica las fotos
cuando un comentario las identifica horas después. Ver src/vigilante.py.

Uso:
    python scripts/vigilante.py --todos                  # todos los grupos de config.yaml
    python scripts/vigilante.py --grupo "Coclé"          # un grupo
Opciones: --solo-cruzadas (no bajar lo que no cruza), --ventana-horas 48, --espera-huerfana-horas 6, --intervalo 150-300
Se detiene con Ctrl+C (o con el botón DETENER de la interfaz).
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import eventos  # noqa: E402
from src.bloqueo import SesionOcupada, candado_sesion  # noqa: E402
from src.config import load_config  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402
from src.logger import setup_logger  # noqa: E402
from src.verificador import hay_errores, informe, verificar  # noqa: E402
from src.vigilante import Vigilante  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="fragmento del título del grupo")
ap.add_argument("--todos", action="store_true", help="todos los grupos de config.yaml")
ap.add_argument("--ponerse-al-dia", action="store_true", help="al iniciar, subir con el mouse (una vez por grupo) para bajar lo de las últimas horas que ya no está en pantalla; NO tocar el mouse mientras tanto")
ap.add_argument("--solo-cruzadas", action="store_true", help="no bajar lo que no cruza con el Excel")
ap.add_argument("--ventana-horas", type=float, default=48, help="cuántas horas atrás se vuelve a cruzar (default 48)")
ap.add_argument("--espera-huerfana-horas", type=float, default=6, help="horas de espera de un comentario antes de dar por huérfana una foto sin número (default 6)")
ap.add_argument("--intervalo", default="150-300", help="segundos entre vueltas, 'min-max' (default 150-300)")
args = ap.parse_args()

pre = verificar()
print(informe(pre), flush=True)
if hay_errores(pre):
    sys.exit("No se inicia: arregla lo marcado como ERROR (ver 'QUÉ HACER') y vuelve a correr.")
if sys.platform == "win32":  # que el PC no se duerma
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
eventos.configurar(cfg.logging.carpeta_logs)
grupos_cfg = [g for g in cfg.whatsapp.grupos if g]
grupos = grupos_cfg if args.todos else ([g for g in grupos_cfg if args.grupo.lower() in g.lower()] or [args.grupo]) if args.grupo else grupos_cfg[:1]
lo, hi = (int(x) for x in args.intervalo.split("-"))


def crear_excel() -> ExcelManager:
    copia = Path(tempfile.mkdtemp()) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)  # el original no se toca
    e = cfg.excel
    x = ExcelManager.desde_config(str(copia), e)
    x.abrir()
    return x


try:
    with candado_sesion():
        Vigilante(cfg, grupos, crear_excel, ventana_horas=args.ventana_horas, espera_huerfana_h=args.espera_huerfana_horas,
                  intervalo_seg=(lo, hi), todo=not args.solo_cruzadas, ponerse_al_dia=args.ponerse_al_dia).correr()
except SesionOcupada as e:
    sys.exit(str(e))
except KeyboardInterrupt:
    logger.info("Vigilante detenido por el usuario (Ctrl+C).")
