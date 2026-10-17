#!/usr/bin/env python3
"""
Cruza, EN SECO (no escribe nada en el Excel), las evidencias de UN día del
índice local contra el Excel de incidencias. Sirve para ir revisando día por día.

Uso:
    python scripts/cruzar_dia.py --fecha 2026-10-15
    python scripts/cruzar_dia.py --fecha 2026-10-15 --grupo Veraguas --todo
"""
import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, provincias_de_grupo  # noqa: E402
from src.cruce import cruzar, resumen  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402
from src.historico import RUTA_INDICE  # noqa: E402
from src.indice import Indice  # noqa: E402
from src.matcher import asociar_mensajes  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--fecha", required=True, help="Día a revisar, AAAA-MM-DD")
ap.add_argument("--grupo", help="Fragmento del título del grupo (default: el primero de config.yaml)")
ap.add_argument("--todo", action="store_true", help="Mostrar también las filas 'ok' (por defecto solo lo que requiere atención)")
args = ap.parse_args()

cfg = load_config()
dia = datetime.fromisoformat(args.fecha).date()
fragmento = (args.grupo or cfg.whatsapp.grupos[0]).lower()

with Indice(RUTA_INDICE) as indice:
    grupo = next((g for g in indice.grupos() if fragmento in g.lower()), None)
    if grupo is None:
        sys.exit(f"No hay nada indexado para '{fragmento}'. Corre primero scripts/cargar_historico.py")
    mensajes = indice.mensajes(grupo)  # todo el grupo: el texto de un día puede estar en el anterior o el siguiente

provincias = provincias_de_grupo(cfg, grupo)

# El Excel se abre sobre una COPIA temporal: este script nunca modifica el original.
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    copia = Path(tmp) / "copia.xlsx"
    shutil.copy(cfg.excel.ruta_archivo, copia)
    e = cfg.excel
    excel = ExcelManager(
        str(copia), e.nombre_hoja, e.columna_codigo_largo, e.columna_codigo_corto, e.columna_evidencia_manual,
        e.columna_estado_automatico, e.columna_ruta_foto, e.columna_observaciones, e.columna_numero_aviso,
        e.columna_fecha_deteccion, e.columna_fecha_sr, e.columna_provincia,
    )
    excel.abrir()
    esperadas = excel.resumen_por_provincia()

    resultados = [
        r for r in asociar_mensajes(
            mensajes, cfg.matching.patron_codigo_regex, cfg.matching.ventana_minutos_mensaje_separado,
            cfg.matching.patron_elemento_regex,
        ) if r.mensaje.timestamp.date() == dia
    ]
    cruces = cruzar(resultados, excel, cfg.matching.margen_horas_evidencia, provincias)

print(f"Grupo: {grupo}")
print(f"Provincias del Excel para este grupo: {sorted(provincias) if provincias else '(sin filtro)'}"
      f"  -> incidencias en el Excel: {sum(esperadas.get(p, 0) for p in provincias) if provincias else sum(esperadas.values())}")
print(f"Día: {dia}\n")
print(f"{'Hora':5}  {'Remitente':16} {'Fotos':>5}  {'Origen':17} {'Estado':15} {'Criterio':15} {'Fila':>4}  Números / motivo")
for c in cruces:
    if c.estado == "ok" and not args.todo:
        continue
    m = c.match.mensaje
    detalle = ", ".join(c.match.candidatos) or "-"
    if c.estado == "revisar_horario":
        detalle += f"  | {c.ventana.motivo[:70]}"
    print(f"{m.timestamp:%H:%M}  {m.remitente[:16]:16} {m.n_adjuntos:5d}  {c.match.origen.value:17} {c.estado:15} "
          f"{(c.criterio.value if c.criterio else '-'):15} {(c.fila.fila_excel if c.fila else '-')!s:>4}  {detalle}")

r = resumen(cruces)
print("\n=== RESUMEN ===")
print(f"Paquetes de evidencia: {r['paquetes']}   Fotos/videos: {r['fotos_videos']}")
print(f"Por estado:   {r['por_estado']}")
print(f"Por origen:   {r['por_origen']}")
print(f"Por criterio: {r['por_criterio']}")
print(f"Incidencias distintas del Excel con evidencia ese día: {r['incidencias_con_evidencia']}")
