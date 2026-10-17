#!/usr/bin/env python3
"""
Reporte de cobertura (en seco, no modifica el Excel): para cada incidencia del Excel de las
provincias del grupo, qué evidencia hay en el índice local. Genera un CSV listo para abrir en Excel.

Uso:
    python scripts/cobertura.py                                  # primer grupo de config.yaml
    python scripts/cobertura.py --grupo Veraguas --del 2026-10-10 --al 2026-10-12
"""
import argparse
import csv
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.datos.cobertura import COLUMNAS, cobertura, resumen_cobertura  # noqa: E402
from src.nucleo.rutas import R  # noqa: E402
from src.nucleo.config import load_config, provincias_de_grupo  # noqa: E402
from src.cruce.cruce import cruzar  # noqa: E402
from src.excel.manager import ExcelManager  # noqa: E402
from src.datos.historico import RUTA_INDICE  # noqa: E402
from src.datos.indice import Indice  # noqa: E402
from src.cruce.matcher import asociar_mensajes  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título del grupo (default: el primero de config.yaml)")
ap.add_argument("--del", dest="desde", help="Resumir solo incidencias detectadas desde AAAA-MM-DD")
ap.add_argument("--al", dest="hasta", help="...hasta AAAA-MM-DD")
args = ap.parse_args()

cfg = load_config()
fragmento = (args.grupo or cfg.whatsapp.grupos[0]).lower()
desde = datetime.fromisoformat(args.desde) if args.desde else None
hasta = datetime.fromisoformat(args.hasta) if args.hasta else None

with Indice(RUTA_INDICE) as indice:
    grupo = next((g for g in indice.grupos() if fragmento in g.lower()), None)
    if grupo is None:
        sys.exit(f"No hay nada indexado para '{fragmento}'. Corre primero scripts/cargar_historico.py")
    mensajes = indice.mensajes(grupo)
    primero, ultimo = indice.rango(grupo)

provincias = provincias_de_grupo(cfg, grupo)
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # el Excel se lee sobre una copia: el original no se toca
    copia = Path(tmp) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)
    e = cfg.excel
    excel = ExcelManager.desde_config(str(copia), e)
    excel.abrir()
    filas = [f for f in excel.leer_filas() if provincias is None or f.provincia in provincias or f.provincia in (None, "SIN DATOS")]
    resultados = asociar_mensajes(
        mensajes, cfg.matching.patron_codigo_regex, cfg.matching.ventana_minutos_mensaje_separado,
        cfg.matching.patron_elemento_regex,
    )
    cruces = cruzar(resultados, excel, cfg.matching.margen_horas_evidencia, provincias)

filas_cob = sorted(cobertura(filas, cruces), key=lambda r: (r["fecha_deteccion"] or datetime.min, r["fila_excel"]))

salida = R.reportes_analisis / f"cobertura_{''.join(c if c.isalnum() else '_' for c in grupo)[:40]}.csv"
salida.parent.mkdir(parents=True, exist_ok=True)
with open(salida, "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig: Excel abre bien las tildes
    w = csv.DictWriter(fh, fieldnames=COLUMNAS, delimiter=";")
    w.writeheader()
    w.writerows(filas_cob)

print(f"Grupo: {grupo}")
print(f"Histórico indexado: {primero} -> {ultimo}   ({len(mensajes)} mensajes)")
print(f"Provincias: {sorted(provincias) if provincias else '(sin filtro)'}")
t = resumen_cobertura(filas_cob)
print(f"\nTODAS las incidencias del grupo ({t['incidencias']}): con evidencia {t['con_evidencia']}, "
      f"revisar horario {t['revisar_horario']}, sin evidencia {t['sin_evidencia']}")
if desde or hasta:
    r = resumen_cobertura(filas_cob, desde, hasta)
    print(f"Detectadas del {desde.date() if desde else '...'} al {hasta.date() if hasta else '...'} ({r['incidencias']}): "
          f"con evidencia {r['con_evidencia']}, revisar horario {r['revisar_horario']}, sin evidencia {r['sin_evidencia']}")
print(f"\nCSV: {salida}")
