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

from src.nucleo import eventos  # noqa: E402
from src.nucleo.bloqueo import SesionOcupada, candado_sesion  # noqa: E402
from src.nucleo.config import load_config, resolver_cargar_desde  # noqa: E402
from src.excel.incidencias import carpeta_de, incorporar_nuevas  # noqa: E402
from src.excel.manager import ExcelManager  # noqa: E402
from src.excel.en_vivo import ExcelEnVivo  # noqa: E402
from src.nucleo.logger import setup_logger  # noqa: E402
from src.nucleo.verificador import hay_errores, informe, verificar  # noqa: E402
from src.bot.vigilante import Vigilante  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="fragmento del título del grupo")
ap.add_argument("--todos", action="store_true", help="todos los grupos de config.yaml")
ap.add_argument("--sin-mouse", action="store_true", help="NO subir con el mouse para cerrar huecos (si el bot estuvo apagado y llegaron más mensajes de los que caben en pantalla, esos mensajes se perderían). Por defecto, si hay hueco, sube unos minutos con el mouse")
ap.add_argument("--ponerse-al-dia", action="store_true", help="(ya es el comportamiento por defecto; se deja por compatibilidad)")
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
grupos_cfg = [g for g in cfg.whatsapp.grupos if g]
grupos = grupos_cfg if args.todos else ([g for g in grupos_cfg if args.grupo.lower() in g.lower()] or [args.grupo]) if args.grupo else grupos_cfg[:1]
lo, hi = (int(x) for x in args.intervalo.split("-"))


def crear_excel() -> ExcelManager:
    incorporar_nuevas(carpeta_de(cfg))  # lo que se haya dejado en data/Incidencias/nuevas/ entra a la base antes de leerla
    copia = Path(tempfile.mkdtemp()) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)  # el original no se toca
    e = cfg.excel
    x = ExcelManager.desde_config(str(copia), e)
    x.abrir()
    return x


from datetime import datetime  # noqa: E402

_desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde) or datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
vivo = ExcelEnVivo(cfg, _desde, grupos_cfg)
logger.info("Excel en vivo: estado dentro de %s y tablero en %s (se actualizan solos cuando hay novedades).", vivo.ruta_base, vivo.ruta_reporte)

try:
    with candado_sesion():
        Vigilante(cfg, grupos, crear_excel, ventana_horas=args.ventana_horas, espera_huerfana_h=args.espera_huerfana_horas,
                  intervalo_seg=(lo, hi), todo=not args.solo_cruzadas, ponerse_al_dia=not args.sin_mouse, excel_vivo=vivo).correr()
except SesionOcupada as e:
    sys.exit(str(e))
except KeyboardInterrupt:
    logger.info("Vigilante detenido por el usuario (Ctrl+C).")
