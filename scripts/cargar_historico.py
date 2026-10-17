#!/usr/bin/env python3
"""
Sube por el chat de uno o varios grupos, indexa lo que va llegando, lo CRUZA en vivo contra el Excel y, al terminar
de subir, descarga (organizado por día e incidencia) las fotos y videos que cruzaron.

Uso:
    python scripts/cargar_historico.py --dias 4 --descargar          # hoy y 4 días antes, primer grupo
    python scripts/cargar_historico.py --dias 4 --descargar --todos   # lo mismo en TODOS los grupos de config.yaml
    python scripts/cargar_historico.py --grupo "Oeste" --desde 2026-10-01 --descargar
    python scripts/cargar_historico.py --minutos 60                   # solo indexar (sin descargar), hasta cargar_desde
Opciones: --minutos (tope por grupo), --todo (bajar también lo que no cruza), --descarga-durante (bajar mientras sube).
"""
import argparse
import shutil
import sys
import tempfile
import time
from datetime import datetime, time as hora, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nucleo import eventos  # noqa: E402
from src.nucleo.rutas import R  # noqa: E402
from src.nucleo.config import load_config, provincias_de_grupo, resolver_cargar_desde  # noqa: E402
from src.excel.en_vivo import ExcelEnVivo  # noqa: E402
from src.datos.historico import RUTA_INDICE, cargar_historico, verificar_historico  # noqa: E402
from src.datos.indice import Indice  # noqa: E402
from src.nucleo.logger import setup_logger  # noqa: E402
from src.nucleo.verificador import hay_errores, informe, verificar  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--grupo", help="Fragmento del título del grupo (por defecto, el primero de config.yaml)")
ap.add_argument("--todos", action="store_true", help="Pasar por TODOS los grupos de config.yaml, uno tras otro")
ap.add_argument("--dias", type=int, help="Hoy y N días antes (p. ej. 4 = desde hace 4 días a las 00:00)")
ap.add_argument("--desde", help="Fecha de inicio AAAA-MM-DD (si no se da, --dias o whatsapp.cargar_desde)")
ap.add_argument("--minutos", type=int, default=100, help="Tiempo máximo por grupo (default 100)")
ap.add_argument("--intentos", type=int, default=6, help="Intentos seguidos sin mensajes nuevos antes de darlo por terminado (default 6; cada intento son 8 ciclos de subir)")
ap.add_argument("--descargar", action="store_true", help="Descargar fotos y videos que cruzan con una incidencia (carpetas por día e incidencia)")
ap.add_argument("--todo", action="store_true", help="Con --descargar: bajar TODO lo del chat, crucen o no (más lento y más riesgo de bloqueo)")
ap.add_argument("--descarga-durante", action="store_true", help="Con --descargar: bajar mientras sube, no solo al terminar")
args = ap.parse_args()

pre = verificar()
print(informe(pre), flush=True)
if hay_errores(pre):
    sys.exit("No se inicia: arregla lo marcado como ERROR (ver 'QUÉ HACER') y vuelve a correr.")

if sys.platform == "win32":  # que el PC no se duerma durante la corrida (no cambia la configuración de Windows)
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)

cfg = load_config()
logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)

# --- rango de tiempo ---------------------------------------------------------------------------------
if args.desde:
    desde = datetime.fromisoformat(args.desde)
elif args.dias is not None:
    desde = datetime.combine(datetime.now().date() - timedelta(days=args.dias), hora.min)
else:
    desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
if desde is None:
    sys.exit("Indica el tiempo: --dias N, --desde AAAA-MM-DD, o pon whatsapp.cargar_desde en config.yaml.")

# --- grupos ------------------------------------------------------------------------------------------
grupos_cfg = [g for g in cfg.whatsapp.grupos if g]
if args.todos:
    grupos = grupos_cfg
elif args.grupo:
    grupos = [g for g in grupos_cfg if args.grupo.lower() in g.lower()] or [args.grupo]
else:
    grupos = grupos_cfg[:1]

logger.info("=== CORRIDA: %d grupo(s) %s | desde %s (hoy y %d día(s) antes) | descargar=%s todo=%s | tope %d min por grupo ===",
            len(grupos), grupos, desde.date(), (datetime.now().date() - desde.date()).days, args.descargar, args.todo, args.minutos)
eventos.evento("-", "corrida", "inicio", "ok", f"grupos={grupos} desde={desde.date()} descargar={args.descargar} todo={args.todo}")

excel = None
if args.descargar:
    from src.excel.incidencias import carpeta_de, incorporar_nuevas
    from src.excel.manager import ExcelManager

    tmp = tempfile.mkdtemp()
    copia = Path(tmp) / "copia.xlsx"
    incorporar_nuevas(carpeta_de(cfg))  # lo que se haya dejado en data/Incidencias/nuevas/ entra a la base antes de leerla
    shutil.copy(cfg.excel.ruta_archivo, copia)  # el original no se toca
    e = cfg.excel
    excel = ExcelManager.desde_config(str(copia), e)
    excel.abrir()
    logger.info("Excel cargado (copia de trabajo): %s", cfg.excel.ruta_archivo)

vivo = ExcelEnVivo(cfg, desde, grupos_cfg) if excel is not None else None
resultados = []
for n, grupo in enumerate(grupos, 1):
    logger.info("##### Grupo %d/%d: %s #####", n, len(grupos), grupo)
    t0 = time.time()
    fabrica = None
    if excel is not None:
        from src.bot.descargas import Descargador

        provincias = provincias_de_grupo(cfg, grupo)
        logger.info("Provincias del Excel para este grupo: %s", sorted(provincias) if provincias else "(sin filtro: cruza contra todo)")
        fabrica = lambda indice, g=grupo, p=provincias: Descargador(  # noqa: E731
            cfg, excel, indice, g, p, desde, todo=args.todo, descarga_durante=args.descarga_durante, excel_vivo=vivo)
    try:
        cargar_historico(cfg, grupo, desde, args.minutos, logger, fabrica_descargador=fabrica, intentos=args.intentos)
        resultados.append((grupo, "ok", time.time() - t0))
    except Exception:  # noqa: BLE001 - un grupo que falla no tumba a los demás
        logger.exception("FALLÓ el grupo '%s' (se sigue con el siguiente).", grupo)
        eventos.evento(grupo, "corrida", "grupo_fallo", "error", "ver detalle.log")
        resultados.append((grupo, "ERROR", time.time() - t0))

logger.info("=== FIN DE LA CORRIDA ===")
for grupo, estado, seg in resultados:
    logger.info("  %-55s %-6s %5.1f min", grupo[:55], estado, seg / 60)
eventos.evento("-", "corrida", "fin", "ok", "; ".join(f"{g}={e}" for g, e, _ in resultados))

if excel is not None:  # reporte Excel con formato (resumen, por incidencia, por día, descargas, sin cruce)
    try:
        from src.excel.reporte import generar_reporte

        with Indice(RUTA_INDICE) as indice:
            salida = R.reportes_historial / f"Reporte_{datetime.now():%Y%m%d_%H%M}.xlsx"
            generar_reporte(cfg, excel, indice, grupos, desde, salida)
        logger.info("REPORTE EXCEL generado: %s", salida.resolve())
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo generar el reporte Excel (el resto de la corrida sí terminó).")

with Indice(RUTA_INDICE) as indice:
    for grupo in grupos:
        print()
        print(verificar_historico(indice, grupo, desde))
print(f"\nLogs de esta corrida: {eventos.CARPETA} (detalle_001.log, descargas_detalle.csv). Resumen: python scripts/estado_descargas.py")
