#!/usr/bin/env python3
"""
Base de incidencias en una sola hoja (data/Incidencias/).

  python scripts/incidencias.py crear [--origen RUTA.xlsx]   Crea la base a partir del Excel original de varias hojas (una sola vez).
                                                             Deja el original intacto en data/Incidencias/original/.
  python scripts/incidencias.py incorporar                   Mezcla en la base lo que hayas puesto en data/Incidencias/nuevas/.
  python scripts/incidencias.py abrir                        Abre la carpeta data/Incidencias/.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.nucleo.config import load_config  # noqa: E402
from src.nucleo.rutas import R  # noqa: E402
from src.excel.incidencias import NOMBRE_BASE, incorporar_nuevas, preparar_carpeta  # noqa: E402
from src.excel.unificar import unificar  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="accion", required=True)
c = sub.add_parser("crear")
c.add_argument("--origen", help="Excel original de varias hojas (por defecto data/Incidencias/original/RESULTADO_CREACION_INCIDENCIAS.xlsx)")
c.add_argument("--hoja", default="Asignacion- SEP", help="hoja principal del original")
sub.add_parser("incorporar")
sub.add_parser("abrir")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
carpeta = preparar_carpeta(R.incidencias)

if args.accion == "crear":
    origen = Path(args.origen) if args.origen else R.incidencias / "original" / "RESULTADO_CREACION_INCIDENCIAS.xlsx"
    if not origen.exists():
        sys.exit(f"No existe el Excel original: {origen}")
    base = carpeta / NOMBRE_BASE
    if base.exists():
        sys.exit(f"Ya existe {base}. Para agregar incidencias nuevas ponlas en {carpeta / 'nuevas'} y corre 'incorporar'.")
    cfg = load_config()
    r = unificar(origen, base, args.hoja, tuple(cfg.excel.hojas_extra) or ("OCTUBRE", "c ya entregados sin correo"))
    shutil.copy2(origen, carpeta / "original" / origen.name)
    print(f"Base creada: {r['incidencias']} incidencias, {r['columnas']} columnas -> {base}")
    print(f"El Excel original quedó copiado en {carpeta / 'original'}. Nuevas incidencias: ponlas en {carpeta / 'nuevas'}.")
elif args.accion == "incorporar":
    r = incorporar_nuevas(carpeta)
    print("No hay archivos nuevos en data/Incidencias/nuevas/." if not r else
          f"Incorporado: {r['archivos']} archivo(s) -> {r['agregadas']} incidencias agregadas, {r['actualizadas']} actualizadas, "
          f"{r['sin_cambios']} ya estaban." + (f" Omitidos (revisar): {r['omitidos']}" if r["omitidos"] else "") +
          (f" Ya incorporados pero abiertos en Excel (ciérralos para moverlos a procesadas/): {r['sin_mover']}" if r.get("sin_mover") else ""))
else:
    os.startfile(carpeta)
