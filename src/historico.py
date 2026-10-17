"""
Carga del histórico de un grupo al índice local y verificador de qué tanto
se ha cargado (mensajes y fotos por día, huecos hasta la fecha objetivo).

Flujo pensado para trabajar "día por día" sin abrumarse:
  1. cargar_historico()  -> sube por el chat guardando en el índice; se puede
     dejar corriendo y repetir: lo ya indexado no se vuelve a leer.
  2. verificar_historico() -> tabla por día; muestra desde cuándo hay datos y
     qué días faltan para llegar a la fecha objetivo (p. ej. 1 de octubre).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import AppConfig
from .indice import Indice, ResumenDia
from .whatsapp_reader import (
    cargar_hacia_arriba,
    construir_mensajes,
    cosechar,
    fusionar_orden,
    leer_instantanea,
    leer_mensajes_recientes,
)
from .whatsapp_session import SesionWhatsApp

RUTA_INDICE = Path(__file__).resolve().parent.parent / "data" / "indice" / "indice.sqlite3"


def tabla_por_dia(resumen: list[ResumenDia], desde: date, hasta: date) -> str:
    """Una fila por día entre `desde` y `hasta`; los días sin datos se marcan para ver los huecos."""
    por_dia = {r.dia: r for r in resumen}
    maximo = max((r.mensajes for r in resumen), default=1) or 1
    lineas = ["Día         Mensajes  ConAdjunto  Fotos/Videos"]
    dia = desde
    while dia <= hasta:
        r = por_dia.get(dia)
        if r:
            barra = "#" * max(1, round(20 * r.mensajes / maximo))
            lineas.append(f"{dia}  {r.mensajes:8d}  {r.con_adjunto:10d}  {r.fotos_videos:12d}  {barra}")
        else:
            lineas.append(f"{dia}  {'-':>8}  {'-':>10}  {'-':>12}  (sin datos cargados)")
        dia += timedelta(days=1)
    return "\n".join(lineas)


def verificar_historico(indice: Indice, grupo: str, desde: datetime, hoy: date | None = None) -> str:
    hoy = hoy or datetime.now().date()
    primero, ultimo = indice.rango(grupo)
    total = indice.contar(grupo)
    if primero is None:
        return f"[{grupo}] Índice vacío: todavía no se ha cargado nada.\nObjetivo: desde {desde.date()}."

    resumen = indice.resumen_por_dia(grupo)
    faltan = (primero.date() - desde.date()).days
    estado = (
        f"COMPLETO: el índice llega hasta {primero.date()} (objetivo {desde.date()})."
        if faltan <= 0
        else f"INCOMPLETO: faltan {faltan} día(s) de histórico (hay datos desde {primero.date()}, objetivo {desde.date()})."
    )
    fotos = sum(r.fotos_videos for r in resumen)
    return "\n".join([
        f"[{grupo}]",
        f"Mensajes indexados: {total}   Fotos/videos: {fotos}",
        f"Primero: {primero}   Último: {ultimo}",
        estado,
        "",
        tabla_por_dia(resumen, min(desde.date(), primero.date()), hoy),
    ])


def cargar_historico(
    cfg: AppConfig,
    grupo: str,
    desde: datetime,
    minutos: int,
    logger: logging.Logger,
    ruta_indice: Path = RUTA_INDICE,
    reintento_seg: int = 30,
    fabrica_descargador=None,
) -> None:
    """
    Abre el grupo y trae el histórico hasta `desde` guardando en el índice, en DOS fases:
      1. cargar_hacia_arriba: sube sin leer, empujando la rueda (real) como una persona hasta que
         dejan de llegar tandas o se llega a `desde`;
      2. cosechar: recorre lo cargado una vez, de arriba abajo, y lo guarda (se detiene al
         llegar a mensajes ya indexados).
    Si no se llegó a `desde`, repite hasta agotar `minutos`.
    """
    limite = time.time() + minutos * 60
    with Indice(ruta_indice) as indice, SesionWhatsApp(
        cfg.whatsapp.carpeta_sesion, headless=cfg.whatsapp.headless, logger=logger
    ) as sesion:
        sesion.abrir_chat(grupo)
        descargador = fabrica_descargador(indice) if fabrica_descargador else None
        ronda = 0
        try:
            _rondas(cfg, grupo, desde, limite, minutos, logger, indice, sesion, descargador, reintento_seg)
            if descargador is not None:
                descargador.barrido_final(sesion.pagina)
        finally:
            if descargador is not None:
                n = descargador.escribir_pendientes(Path(cfg.logging.carpeta_logs) / "descargas_pendientes.csv")
                logger.info("Descargas: %d mensajes bajados, %d fallidos, %d pendientes (logs/descargas_pendientes.csv).",
                            descargador.total_ok, descargador.total_mal, n)


def _rondas(cfg, grupo, desde, limite, minutos, logger, indice, sesion, descargador, reintento_seg) -> None:
    ronda = 0
    sin_avance = 0
    if True:
        while True:
            ronda += 1
            restante = max(30, limite - time.time())
            logger.info("Ronda %d - fase 1: cargando hacia arriba (hasta %d s)...", ronda, int(restante))
            conocidos = indice.ids(grupo)

            def guardar_tanda() -> None:
                ms = cosechar(sesion.pagina, ids_conocidos=conocidos or None, espera_paso_ms=350)
                n = indice.guardar(grupo, [m for m in ms if m.timestamp >= desde])
                conocidos.update(m.id_mensaje for m in ms if m.id_mensaje)
                if n:
                    logger.info("  tanda guardada: %d mensajes nuevos (índice %d, más antiguo %s)", n, indice.contar(grupo), indice.rango(grupo)[0])
                if descargador is not None:
                    descargador.procesar(sesion.pagina)

            stats = cargar_hacia_arriba(
                sesion.pagina, desde=desde, max_seg=restante, al_tanda=guardar_tanda,
                al_ciclo=(lambda: descargador.en_ciclo(sesion.pagina)) if descargador is not None else None,
                al_progreso=lambda i: logger.info(
                    "  tandas: %d | burbujas: %d | ciclos: %d | intentos sin tanda: %d | %ds", i["tandas"], i["burbujas"], i["ciclos"], i["sin_tanda"], i["segundos"]),
            )
            logger.info("Fase 1 lista: %s", stats)

            logger.info("Ronda %d - fase 2: cosechando lo cargado...", ronda)
            mensajes = cosechar(
                sesion.pagina, ids_conocidos=indice.ids(grupo) or None,
                al_progreso=lambda i: logger.info("  cosecha: paso %d, %d mensajes", i["paso"], i["leidos"]),
            )
            nuevos = indice.guardar(grupo, [m for m in mensajes if m.timestamp >= desde])
            primero = indice.rango(grupo)[0]
            logger.info("Ronda %d: %d mensajes nuevos en el índice (total %d, más antiguo %s).", ronda, nuevos, indice.contar(grupo), primero)

            if primero is not None and primero.date() <= desde.date():
                logger.info("Histórico completo hasta %s.", desde.date())
                break
            if time.time() >= limite:
                logger.warning("Se agotó el tiempo (%d min) sin llegar a %s.", minutos, desde.date())
                break
            if stats["tandas"] == 0:
                sin_avance += 1
                if sin_avance >= 3:
                    logger.warning("El celular ya no entrega mensajes más antiguos: 3 rondas seguidas sin tandas nuevas. "
                                   "El histórico de '%s' llega hasta %s (se pedía desde %s). Se da por terminado en vez de gastar el tiempo restante.",
                                   grupo, primero, desde.date())
                    break
            else:
                sin_avance = 0
            if stats["tandas"] == 0:
                logger.info("Sin tandas nuevas; reintento en %ds (quedan ~%d min)...", reintento_seg, int((limite - time.time()) / 60))
                sesion.pagina.wait_for_timeout(reintento_seg * 1000)


def capturar_mientras_scrollea(
    cfg: AppConfig,
    grupo: str,
    desde: datetime,
    minutos: int,
    logger: logging.Logger,
    ruta_indice: Path = RUTA_INDICE,
    cada_seg: float = 0.7,
    guardar_cada_seg: float = 5,
    grabar_eventos: bool = False,
) -> None:
    """
    Modo manual: abre el grupo y SOLO MIRA mientras la persona hace scroll con el mouse
    (lo que sí dispara la carga de mensajes antiguos). Cada ~0,7 s lee lo que hay pintado,
    lo fusiona en orden cronológico y lo guarda en el índice cada pocos segundos.
    Termina al cerrar la ventana, al llegar a `desde` o al agotar `minutos`.
    """
    limite = time.time() + minutos * 60
    acumulado: dict[str, dict] = {}
    orden: list[str] = []
    ultimo_guardado = 0.0
    ultimo_aviso = 0.0

    with Indice(ruta_indice) as indice, SesionWhatsApp(
        cfg.whatsapp.carpeta_sesion, headless=cfg.whatsapp.headless, logger=logger
    ) as sesion:
        sesion.abrir_chat(grupo)
        logger.info("LISTO: haz scroll con el mouse en el chat (bajar y subir); yo solo guardo lo que aparezca.")
        if grabar_eventos:
            from . import grabacion

            sesion.pagina.evaluate(grabacion.JS_GRABAR)
            eventos_cache: list[dict] = []
            ultimo_volcado = 0.0
            logger.info("Grabando también los eventos de tu mouse (para copiar tu patrón de scroll).")
            llegadas: list[tuple[float, int]] = []  # (segundo, mensajes vistos) cada vez que llegan mensajes nuevos
            t_ini = time.time()

        def guardar() -> int:
            # Se excluyen los primeros sin fecha conocida: su día se confirma al aparecer su separador.
            ids = list(orden)
            primero = next((k for k, i in enumerate(ids) if acumulado[i].get("fecha")), None)
            if primero is None:
                return 0
            mensajes = construir_mensajes([acumulado[i] for i in ids[primero:]])
            return indice.guardar(grupo, [m for m in mensajes if m.timestamp >= desde])

        try:
            while time.time() < limite:
                try:
                    items = leer_instantanea(sesion.pagina)
                except Exception:  # noqa: BLE001 - ventana cerrada o cambiando de página
                    break
                for it in items:
                    previo = acumulado.get(it["id"])
                    if previo is None:
                        acumulado[it["id"]] = it
                    elif not previo.get("fecha") and it.get("fecha"):
                        previo["fecha"] = it["fecha"]
                antes_n = len(orden)
                orden = fusionar_orden(orden, [it["id"] for it in items])
                if grabar_eventos and len(orden) > antes_n:
                    llegadas.append((round(time.time() - t_ini, 1), len(orden)))

                ahora = time.time()
                if ahora - ultimo_guardado >= guardar_cada_seg:
                    nuevos = guardar()
                    ultimo_guardado = ahora
                    primero_idx, _ = indice.rango(grupo)
                    if nuevos or ahora - ultimo_aviso > 30:
                        logger.info("  vistos %d mensajes | índice: %d (más antiguo %s)", len(orden), indice.contar(grupo), primero_idx or "-")
                        ultimo_aviso = ahora
                    if primero_idx is not None and primero_idx.date() <= desde.date():
                        logger.info("Se llegó al %s: listo.", desde.date())
                        break
                if grabar_eventos and ahora - ultimo_volcado >= 5:
                    ultimo_volcado = ahora
                    try:
                        eventos_cache = sesion.pagina.evaluate(grabacion.JS_LEER)
                    except Exception:  # noqa: BLE001
                        pass
                sesion.pagina.wait_for_timeout(int(cada_seg * 1000))
        except Exception as e:  # noqa: BLE001 - cerrar la ventana a mano es la forma normal de terminar
            if "closed" not in str(e).lower():
                raise
            logger.info("Ventana cerrada: se guarda lo capturado.")
        finally:
            try:
                guardar()
            except Exception:  # noqa: BLE001
                pass
            if grabar_eventos:
                try:
                    from . import grabacion

                    try:
                        eventos = sesion.pagina.evaluate(grabacion.JS_LEER)
                    except Exception:  # noqa: BLE001 - la ventana ya se cerró: se usa el último volcado
                        eventos = eventos_cache
                    resumen = grabacion.resumir(eventos)
                    resumen["llegadas_de_mensajes"] = llegadas
                    ruta = Path(cfg.logging.carpeta_logs) / "scroll_manual.json"
                    ruta.write_text(json.dumps({"resumen": resumen, "eventos": eventos[:3000]}, ensure_ascii=False), encoding="utf-8")
                    logger.info("Patrón de tu scroll guardado en %s: %s", ruta, json.dumps(resumen, ensure_ascii=False)[:900])
                except Exception as e:  # noqa: BLE001
                    logger.warning("No se pudo guardar la grabación de eventos: %s", e)


def actualizar_incremental(
    cfg: AppConfig,
    grupos: list[str],
    logger: logging.Logger,
    ruta_indice: Path = RUTA_INDICE,
    max_pasos: int = 80,
) -> dict[str, int]:
    """
    Corrida de todos los días (apta para la tarea cada hora): NO vuelve a subir el histórico.
    Abre cada grupo, lee desde lo más nuevo hacia arriba y se detiene apenas ve una pantalla
    completa de mensajes que ya están en el índice. Devuelve {grupo: mensajes_nuevos}.

    El histórico viejo se baja una sola vez (cargar_historico) y queda en el índice; Web no lo
    conserva entre sesiones, por eso el índice es la fuente de verdad.
    """
    nuevos: dict[str, int] = {}
    with Indice(ruta_indice) as indice, SesionWhatsApp(
        cfg.whatsapp.carpeta_sesion, headless=cfg.whatsapp.headless, logger=logger
    ) as sesion:
        for grupo in grupos:
            try:
                sesion.abrir_chat(grupo)
                conocidos = indice.ids(grupo)
                mensajes = leer_mensajes_recientes(
                    sesion.pagina, max_pasos=max_pasos, intentos_tope=0,
                    ids_conocidos=conocidos or None,
                )
                nuevos[grupo] = indice.guardar(grupo, mensajes)
                logger.info("'%s': %d mensajes nuevos (índice: %d).", grupo, nuevos[grupo], indice.contar(grupo))
            except Exception as e:  # noqa: BLE001 - un grupo que falla no tumba a los demás
                logger.error("No se pudo actualizar '%s': %s", grupo, e)
    return nuevos
