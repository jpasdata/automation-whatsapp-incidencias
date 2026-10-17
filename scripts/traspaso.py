#!/usr/bin/env python3
"""
Pasar el trabajo adelantado de un PC a otro (índice + evidencias + estado), sin perder nada ni repetir descargas.

  Exportar (en el PC que tiene el avance):   python scripts/traspaso.py exportar
        -> crea data/Traspasos/Traspaso_<fecha>.zip  (copia ese .zip al otro PC, por USB o la nube)
  Importar (en el PC que va a continuar):    python scripts/traspaso.py importar RUTA\\Traspaso_xxx.zip
        -> mezcla índice y evidencias, reapunta las rutas a este PC y respalda lo que había. Con --excel también reemplaza el Excel
           de incidencias (deja copia del anterior).
No se traspasa la sesión de WhatsApp (en el otro PC se escanea el QR) ni config.yaml. No correr el bot en los dos PCs a la vez.
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.datos.traspaso import ajustar_config, exportar, importar  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="accion", required=True)
e = sub.add_parser("exportar")
e.add_argument("--salida", help="ruta del .zip (por defecto data/Traspasos/Traspaso_<fecha>.zip)")
e.add_argument("--sin-excel", action="store_true", help="no incluir el Excel de incidencias")
i = sub.add_parser("importar")
i.add_argument("zip", help="ruta del .zip de traspaso")
i.add_argument("--excel", action="store_true", help="reemplazar también el Excel de incidencias (deja copia del anterior)")
sub.add_parser("ajustar-config", help="deja config.yaml apuntando a la base de dos hojas (útil tras un git pull)")
args = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if args.accion == "ajustar-config":
    c = ajustar_config(RAIZ)
    print("config.yaml ajustado: " + ", ".join(c) if c else "config.yaml ya estaba bien (o no existe).")
elif args.accion == "exportar":
    ruta = exportar(RAIZ, Path(args.salida) if args.salida else None, con_excel=not args.sin_excel)
    print(f"Traspaso creado: {ruta}  ({ruta.stat().st_size / 1e6:.0f} MB)\nCópialo al otro PC e impórtalo allá con:\n  python scripts/traspaso.py importar \"{ruta.name}\"")
else:
    r = importar(RAIZ, Path(args.zip), con_excel=args.excel)
    print("Traspaso importado:")
    for k, v in r.items():
        print(f"  {k}: {v}")
    print("Listo. Ahora puedes iniciar el vigilante: seguirá desde donde quedó el otro PC.")
