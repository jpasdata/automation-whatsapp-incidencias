#!/usr/bin/env python3
"""
Genera el reporte en Excel (con formato): resumen, por incidencia, por día, descargas y lo que no cruzó.
Solo lee el índice y el Excel de incidencias; escribe un archivo nuevo en data/Reportes/.

Uso:
    python scripts/generar_reporte.py --desde 2026-10-01
    python scripts/generar_reporte.py --dias 4 --todos
"""
import argparse
import shutil
import sys
import tempfile
from datetime import datetime, time as hora, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, resolver_cargar_desde  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402
from src.historico import RUTA_INDICE  # noqa: E402
from src.indice import Indice  # noqa: E402
from src.reporte_excel import generar_reporte  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--desde", help="AAAA-MM-DD")
ap.add_argument("--dias", type=int, help="hoy y N días antes")
ap.add_argument("--grupo", help="fragmento del título del grupo")
ap.add_argument("--todos", action="store_true", help="todos los grupos indexados")
ap.add_argument("--salida", help="ruta del .xlsx (por defecto data/Reportes/Reporte_<fecha>.xlsx)")
args = ap.parse_args()

cfg = load_config()
if args.desde:
    desde = datetime.fromisoformat(args.desde)
elif args.dias is not None:
    desde = datetime.combine(datetime.now().date() - timedelta(days=args.dias), hora.min)
else:
    desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde) or datetime.now().replace(day=1, hour=0, minute=0)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, Indice(RUTA_INDICE) as indice:
    copia = Path(tmp) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)
    e = cfg.excel
    excel = ExcelManager(str(copia), e.nombre_hoja, e.columna_codigo_largo, e.columna_codigo_corto, e.columna_evidencia_manual,
                         e.columna_estado_automatico, e.columna_ruta_foto, e.columna_observaciones, e.columna_numero_aviso,
                         e.columna_fecha_deteccion, e.columna_fecha_sr, e.columna_provincia)
    excel.abrir()
    indexados = indice.grupos()
    if args.todos:
        grupos = indexados
    elif args.grupo:
        grupos = [g for g in indexados if args.grupo.lower() in g.lower()]
    else:
        grupos = [g for g in indexados if cfg.whatsapp.grupos[0].lower() in g.lower() or g.lower() in cfg.whatsapp.grupos[0].lower()]
    if not grupos:
        sys.exit("No hay grupos indexados que coincidan. Corre primero scripts/cargar_historico.py")
    salida = Path(args.salida) if args.salida else Path("data/Reportes") / f"Reporte_{datetime.now():%Y%m%d_%H%M}.xlsx"
    print("Reporte:", generar_reporte(cfg, excel, indice, grupos, desde, salida))
