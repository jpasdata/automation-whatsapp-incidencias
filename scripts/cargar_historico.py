#!/usr/bin/env python3
"""
Carga el histórico de UN grupo al índice local (data/indice/indice.sqlite3).
Se puede dejar corriendo y repetir: lo ya indexado no se vuelve a leer.

Uso:
    python scripts/cargar_historico.py                  # primer grupo de config.yaml, hasta cargar_desde
    python scripts/cargar_historico.py --minutos 30     # esperar hasta 30 min a que WhatsApp sincronice
    python scripts/cargar_historico.py --grupo "Oeste"  # otro grupo (fragmento del título)
    python scripts/cargar_historico.py --descargar      # además baja (al vuelo) las fotos que cruzan con el Excel
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, resolver_cargar_desde  # noqa: E402
from src.historico import RUTA_INDICE, cargar_historico, verificar_historico  # noqa: E402
from src.indice import Indice  # noqa: E402
from src.logger import setup_logger  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título del grupo (por defecto, el primero de config.yaml)")
ap.add_argument("--minutos", type=int, default=10, help="Tiempo máximo esperando el histórico (default 10)")
ap.add_argument("--descargar", action="store_true", help="Descargar las fotos que cruzan con una incidencia de Henry (carpetas por día)")
args = ap.parse_args()

from src.verificador import hay_errores, informe, verificar  # noqa: E402

_pre = verificar()
print(informe(_pre), flush=True)
if hay_errores(_pre):
    sys.exit("No se inicia: arregla lo marcado como ERROR (ver 'QUÉ HACER') y vuelve a correr.")

if sys.platform == "win32":  # que el PC no se duerma durante la corrida (no cambia la configuración de Windows)
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
grupo = args.grupo or cfg.whatsapp.grupos[0]
desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
if desde is None:
    sys.exit("whatsapp.cargar_desde está vacío en config.yaml: pon 'mes_actual' o una fecha AAAA-MM-DD.")

logger.info("=== Carga de histórico: '%s' desde %s ===", grupo, desde.date())
fabrica = None
if args.descargar:
    import shutil
    import tempfile

    from src.config import provincias_de_grupo
    from src.descargas import Descargador
    from src.excel_manager import ExcelManager

    tmp = tempfile.mkdtemp()
    copia = Path(tmp) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)  # el original no se toca
    e = cfg.excel
    excel = ExcelManager(
        str(copia), e.nombre_hoja, e.columna_codigo_largo, e.columna_codigo_corto, e.columna_evidencia_manual,
        e.columna_estado_automatico, e.columna_ruta_foto, e.columna_observaciones, e.columna_numero_aviso,
        e.columna_fecha_deteccion, e.columna_fecha_sr, e.columna_provincia,
    )
    excel.abrir()
    provincias = provincias_de_grupo(cfg, grupo)
    fabrica = lambda indice: Descargador(cfg, excel, indice, grupo, provincias, desde)  # noqa: E731

cargar_historico(cfg, grupo, desde, args.minutos, logger, fabrica_descargador=fabrica)

with Indice(RUTA_INDICE) as indice:
    print()
    print(verificar_historico(indice, grupo, desde))
