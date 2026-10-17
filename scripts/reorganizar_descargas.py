#!/usr/bin/env python3
"""
Reorganiza lo YA descargado según el cruce actual (sin abrir WhatsApp ni descargar nada): usa el índice (ruta de cada
mensaje descargado) y el Excel para mover/renombrar cada archivo a su carpeta de incidencia/aviso y reescribe los
manifiestos. Úsalo cuando cambie el Excel, las reglas de cruce o la forma de nombrar carpetas.

Uso:  python scripts/reorganizar_descargas.py [--desde 2026-10-01] [--simular]
"""
import argparse
import logging
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import eventos  # noqa: E402
from src.config import load_config, provincias_de_grupo  # noqa: E402
from src.cruce import cruzar  # noqa: E402
from src.descargas import RAIZ_EVIDENCIAS, plan_descargas  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402
from src.historico import RUTA_INDICE  # noqa: E402
from src.indice import Indice  # noqa: E402
from src.logger import setup_logger  # noqa: E402
from src.matcher import asociar_mensajes  # noqa: E402
from src.vigilante import carpeta_sin_cruce, escribir_manifiestos, reubicar_identificadas  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--desde", default="2026-10-01", help="AAAA-MM-DD (default 2026-10-01)")
ap.add_argument("--simular", action="store_true", help="solo contar qué se movería, sin tocar archivos")
args = ap.parse_args()

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
eventos.configurar(cfg.logging.carpeta_logs)
desde = datetime.fromisoformat(args.desde)
copia = Path(tempfile.mkdtemp()) / "copia.xlsx"
shutil.copy(cfg.excel.ruta_archivo, copia)
excel = ExcelManager.desde_config(str(copia), cfg.excel)
excel.abrir()
m = cfg.matching

with Indice(RUTA_INDICE) as indice:
    _n = indice.rebasar_rutas(RAIZ_EVIDENCIAS)
    if _n:
        logger.info("El índice venía de otro PC: se reapuntaron %d rutas de descarga.", _n)
    for grupo in indice.grupos():
        descargas = indice.estado_descarga(grupo)
        ok = {i: r for i, (e, r) in descargas.items() if e == "ok" and r}
        archivos = [Path(x) for r in ok.values() for x in r.split(";") if x]
        faltan = [a for a in archivos if not a.exists()]
        logger.info("[%s] descargados según el índice: %d mensajes, %d archivos (%d NO están en disco)", grupo[:30], len(ok), len(archivos), len(faltan))
        if not ok:
            continue
        mensajes = indice.mensajes(grupo)
        res = [r for r in asociar_mensajes(mensajes, m.patron_codigo_regex, m.ventana_minutos_mensaje_separado, m.patron_elemento_regex)
               if r.mensaje.timestamp >= desde and r.mensaje.n_adjuntos > 0]
        cruces = cruzar(res, excel, m.margen_horas_evidencia, provincias_de_grupo(cfg, grupo))
        destinos = plan_descargas(cruces, RAIZ_EVIDENCIAS, grupo, set(), todo=True, sin_cruce_dir=carpeta_sin_cruce)
        por_destino = Counter(("incidencia del Excel" if "_otras_incidencias" not in d.carpeta.parts and "_sin_numero" not in d.carpeta.parts
                               else "otras (no está en el Excel)" if "_otras_incidencias" in d.carpeta.parts else "sin número")
                              for i, d in destinos.items() if i in ok)
        logger.info("[%s] destino de lo descargado: %s", grupo[:30], dict(por_destino))
        if args.simular:
            continue
        n = reubicar_identificadas(indice, grupo, destinos)
        escribir_manifiestos(indice, grupo, cruces, RAIZ_EVIDENCIAS, desde)
        logger.info("[%s] reorganizados: %d mensajes", grupo[:30], n)

# huérfanos en disco: archivos de imagen/video que ya no están en ninguna ruta del índice
with Indice(RUTA_INDICE) as indice:
    registrados = {str(Path(x)) for g in indice.grupos() for _, (_, r) in indice.estado_descarga(g).items() if r for x in r.split(";") if x}
sueltos = [f for f in RAIZ_EVIDENCIAS.rglob("*") if f.is_file() and f.suffix.lower() in (".jpg", ".png", ".mp4", ".mov") and str(f) not in registrados]
logger.info("Archivos en disco que el índice no conoce: %d", len(sueltos))
for f in sueltos[:10]:
    logger.info("  %s", f)
