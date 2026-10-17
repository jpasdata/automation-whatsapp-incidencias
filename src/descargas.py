"""
Descarga de evidencias: solo las fotos/videos que cruzan con una incidencia del Excel (o TODAS si todo=True),
organizadas por día e incidencia:

    <raiz>/<Grupo>/<AAAA-MM-DD>/<fila>_<codigo>/<HHMM>_<remitente>_<id>_<n>.jpg|mp4
    <raiz>/<Grupo>/<AAAA-MM-DD>/_sin_incidencia/...   (solo con todo=True)

Flujo pensado (ver README): mientras el bot sube por el chat, lo leído se indexa y se CRUZA en vivo (el log dice cuánto
se bajará y cuánto se descarta); cuando termina de subir, `barrido_final` recorre el chat de arriba abajo y baja lo
que cruza, con el contexto completo (el texto que identifica una foto puede venir antes, después o como respuesta).
Cada intento queda en logs/descargas_detalle.csv (resultado, motivo del fallo, tiempos) y en logs/detalle.log.
"""
from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from . import eventos
from .cruce import ResultadoCruce, cruzar
from .excel_manager import ExcelManager
from .indice import Indice
from .matcher import asociar_mensajes
from .whatsapp_reader import _JS_IR_ARRIBA, descargar_adjunto

logger = logging.getLogger("incidencias_wa")

RAIZ_EVIDENCIAS = Path(__file__).resolve().parent.parent / "data" / "Evidencias_WhatsApp"
MAX_RUTA = 235  # Windows falla con rutas de ~260 caracteres o más: se deja margen


def slug_grupo(grupo: str) -> str:
    """Nombre corto de carpeta del grupo (sin el sufijo '-Reporte-de-videos...')."""
    s = _slug(grupo, 60)
    s = re.sub(r"-Reporte-de-vid.*$", "", s)
    return s[:32].strip("-") or "grupo"


def _slug(texto: str | None, largo: int = 24) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return (re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-") or "sin-nombre")[:largo]


@dataclass
class TareaDescarga:
    id_mensaje: str
    carpeta: Path
    base: str          # nombre sin extensión; se le añade _<n> por cada foto del mensaje
    n_esperadas: int
    estado: str        # estado del cruce ('ok' | 'revisar_horario' | 'sin_cruce')
    meta: dict = field(default_factory=dict)   # dia, hora, remitente, fila, codigo, criterio, origen (para el CSV)


_RX_AVISO = re.compile(r"^5\d{2}-?\d{4}$")
_RX_INCID = re.compile(r"^11\d{5}$")
_RX_LARGO = re.compile(r"^0?\d{11,12}$")
_RX_ELEM = re.compile(r"^F[\s:\-#]?\d{3,6}$", re.I)


def etiqueta_identificador(c: ResultadoCruce) -> str:
    """
    Texto que identifica de dónde es una foto, para la carpeta y el nombre del archivo:
      con incidencia del Excel -> "Inc-1168222_Aviso-5620125_f230"   (f = fila del Excel)
      número del chat, no está en el Excel -> "Aviso-5633273" / "Inc-1170118" / "Elem-F02210"
      sin número -> "" (va a _sin_numero)
    """
    if c.fila is not None:
        f = c.fila
        partes = [f"Inc-{f.codigo_corto or (f.codigo_largo or '')[1:8]}"]
        if f.numero_aviso:
            partes.append(f"Aviso-{f.numero_aviso}")
        partes.append(f"f{f.fila_excel}" + (f"-{_slug(f.hoja, 10)}" if f.hoja else ""))
        return "_".join(_slug(x, 30) for x in partes)
    partes = []
    for cand in c.match.candidatos:
        n = str(cand).strip().upper().replace(" ", "")
        if _RX_AVISO.match(n):
            partes.append(f"Aviso-{n.replace('-', '')}")
        elif _RX_INCID.match(n):
            partes.append(f"Inc-{n}")
        elif _RX_LARGO.match(n):
            partes.append(f"Inc-{n.lstrip('0')[:7]}")
        elif _RX_ELEM.match(n):
            partes.append(f"Elem-{re.sub(r'[^A-Z0-9]', '', n)}")
        else:
            partes.append(f"Num-{re.sub(r'[^A-Z0-9]', '', n)}")
    vistos: list[str] = []
    for p_ in partes:
        if p_ not in vistos:
            vistos.append(p_)
    return "_".join(vistos[:3])[:60]


def plan_descargas(
    cruces: list[ResultadoCruce], raiz: Path, grupo: str, ya_hechas: set[str], todo: bool = False,
    sin_cruce_dir="_sin_incidencia",
) -> dict[str, TareaDescarga]:
    """
    Qué bajar: los paquetes con adjunto aún no descargados que cruzan con una fila del Excel (lo normal, para
    no exceder el ritmo de descargas) o todos (`todo=True`). Organización:
        <Grupo>/<día>/<Inc-..._Aviso-..._fNN>/                    cruza con el Excel
        <Grupo>/<día>/<sin_cruce_dir>/<Aviso-.../Inc-...>/        el chat trae número pero no está en el Excel
        <Grupo>/<día>/_sin_numero/                                 el chat no trae ningún número (aún)
    y cada archivo se llama <HHMM>_<identificador>_<remitente>_<id>_<n>.<ext>.
    """
    plan: dict[str, TareaDescarga] = {}
    for c in cruces:
        m = c.match.mensaje
        if not m.id_mensaje or m.n_adjuntos <= 0 or m.id_mensaje in ya_hechas or (c.fila is None and not todo):
            continue
        etiqueta = etiqueta_identificador(c)
        dia = raiz / slug_grupo(grupo) / f"{m.timestamp:%Y-%m-%d}"
        if c.fila is not None:
            codigo = c.fila.codigo_largo or c.fila.codigo_corto or c.fila.numero_aviso or "sin-codigo"
            carpeta = dia / etiqueta
        else:
            codigo = ""
            base_dir = sin_cruce_dir(c) if callable(sin_cruce_dir) else sin_cruce_dir
            carpeta = dia / base_dir / etiqueta if etiqueta else dia / ("_sin_numero" if not callable(sin_cruce_dir) or base_dir == "_otras_incidencias" else base_dir)
        remit, ident = _slug(m.remitente, 14)[-9:].strip("-"), _slug(m.id_mensaje[-6:], 6)
        for n_etiq in (24, 16, 8, 0):  # acorta el nombre del archivo si la ruta se pasa del límite de Windows
            base = "_".join(x for x in (f"{m.timestamp:%H%M}", etiqueta[:n_etiq].strip("_-"), remit, ident) if x)
            if len(str(carpeta / f"{base}_99.jpg")) <= MAX_RUTA:
                break
        meta = {
            "dia": f"{m.timestamp:%Y-%m-%d}", "hora": f"{m.timestamp:%H:%M}", "remitente": m.remitente or "",
            "fila": c.fila.fila_excel if c.fila else "", "codigo": codigo, "numero": c.numero or "", "identificador": etiqueta,
            "hoja": (c.fila.hoja or "Asignacion") if c.fila else "", "leyenda": (m.texto or "").replace("\n", " ")[:120],
            "criterio": c.criterio.value if c.criterio else "", "origen": c.match.origen.value,
        }
        plan[m.id_mensaje] = TareaDescarga(m.id_mensaje, carpeta, base, m.n_adjuntos,
                                           c.estado if c.fila is not None else "sin_cruce", meta)
    return plan


_JS_IDS_VISIBLES = """() => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return [];
  const alto = innerHeight;
  return [...panel.querySelectorAll('[data-testid^="conv-msg-"]')].filter(el => {
    if (el.querySelector('[data-virtualized="true"]')) return false;
    const r = el.getBoundingClientRect();
    return r.bottom > 0 && r.top < alto && el.querySelector('[data-testid="image-thumb"], [data-testid="video-content"]');
  }).map(el => el.dataset.id);
}"""

_JS_IDS_PINTADOS = """() => [...document.querySelectorAll('[data-testid^="conv-msg-"]')]
  .filter(el => !el.querySelector('[data-virtualized="true"]')).map(el => el.dataset.id)"""

# Baja una fracción de pantalla; "movio" es false cuando ya no se puede bajar más (se llegó al final).
_JS_PASO_ABAJO = """(f) => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return {movio: false};
  const cands = [panel, ...panel.querySelectorAll('div')];
  const el = cands.filter(e => e.scrollHeight > e.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(e).overflowY))
                  .sort((a, b) => b.clientHeight - a.clientHeight)[0];
  if (!el) return {movio: false};
  const antes = el.scrollTop; el.scrollTop += el.clientHeight * f;
  return {movio: el.scrollTop > antes};
}"""


def descargar_visibles(
    pagina: Page, plan: dict[str, TareaDescarga], indice: Indice, grupo: str, max_pasos: int = 80,
    desde_arriba: bool = True, factor: float = 0.4,
) -> tuple[int, int]:
    """
    Recorre lo pintado de arriba abajo (pasos de `factor` pantallas: más cortos que 1 para que Web alcance a
    pintar todo) y descarga las tareas del plan cuyas burbujas aparezcan. Marca cada mensaje en el índice
    ('ok'/'error') y escribe una fila en logs/descargas_detalle.csv. Devuelve (descargadas, fallidas).
    """
    pendientes = dict(plan)
    ok = mal = 0
    quieto = 0
    if desde_arriba:
        pagina.evaluate(_JS_IR_ARRIBA)
        pagina.wait_for_timeout(900)
    for paso in range(1, max_pasos + 1):
        if not pendientes:
            break
        for id_msg in pagina.evaluate(_JS_IDS_VISIBLES):
            tarea = pendientes.pop(id_msg, None)
            if tarea is None:
                continue
            bub = pagina.locator(f'[data-id="{id_msg}"]')
            miniaturas = bub.locator('[data-testid="image-thumb"], [data-testid="video-content"]')
            hay_album = bub.locator('[data-testid="media-album"]').count() > 0
            errores: list[str] = []
            nota = ""
            t0 = time.time()
            logger.info("  Bajando %s %s de %s -> %s/%s (cruce: %s, fila %s)", tarea.meta.get("dia"), tarea.meta.get("hora"),
                        tarea.meta.get("remitente"), tarea.carpeta.parent.name, tarea.carpeta.name, tarea.meta.get("origen"), tarea.meta.get("fila"))
            if hay_album or miniaturas.count() > 1:
                # Álbum: se abre el primero y se recorren TODOS con "Siguiente" (el chat solo muestra 4 miniaturas).
                rutas = descargar_adjunto(pagina, miniaturas.first, tarea.carpeta, tarea.base, todo_el_album=True, errores=errores)
            else:
                rutas = descargar_adjunto(pagina, miniaturas.first, tarea.carpeta, f"{tarea.base}_1", errores=errores)
            segundos = round(time.time() - t0, 1)
            tam = sum(r.stat().st_size for r in rutas)
            resultado = "ok" if rutas else "error"
            if rutas:
                indice.marcar_descarga(grupo, id_msg, "ok", ";".join(str(r) for r in rutas))
                ok += 1
                if any("no terminó de cargar" in e or "Error" in e for e in errores):
                    resultado = "parcial"  # alguna foto del álbum sí falló
                nota = (f"el chat mostraba {tarea.n_esperadas} miniaturas y el visor tenía {len(rutas)}"
                        if tarea.n_esperadas and len(rutas) != tarea.n_esperadas else "")
            else:
                indice.marcar_descarga(grupo, id_msg, "error")
                mal += 1
            logger.log(logging.INFO if rutas else logging.WARNING, "    -> %s: %d archivo(s), %.1f MB, %.1fs%s", resultado, len(rutas),
                       tam / 1e6, segundos, f" | {'; '.join(errores)}" if errores else "")
            eventos.registrar_csv("descargas_detalle.csv", {
                "grupo": grupo, **tarea.meta, "id_mensaje": id_msg, "estado_cruce": tarea.estado, "esperados": tarea.n_esperadas,
                "bajados": len(rutas), "bytes": tam, "segundos": segundos, "resultado": resultado,
                "error": " | ".join(errores), "nota": nota, "carpeta": str(tarea.carpeta),
            })
            pagina.wait_for_timeout(random.randint(900, 2600))  # ritmo humano entre mensajes
        r = pagina.evaluate(_JS_PASO_ABAJO, factor)
        quieto = 0 if r.get("movio") else quieto + 1
        if quieto >= 2:
            logger.debug("Fin del recorrido de descarga en el paso %d (no se puede bajar más).", paso)
            break
        pagina.wait_for_timeout(random.randint(380, 650))
    return ok, mal


class Descargador:
    """
    Cruza lo indexado contra el Excel y baja lo que cruza. `procesar` (tras cada tanda) solo CRUZA y avisa en el log;
    `barrido_final` (al terminar de subir) es el que descarga, con el contexto completo.
    `en_ciclo` permite descargar mientras se sube (opcional: `descarga_durante`).
    """

    def __init__(self, cfg, excel: ExcelManager, indice: Indice, grupo: str, provincias: set[str] | None,
                 desde: datetime, raiz: Path = RAIZ_EVIDENCIAS, todo: bool = False, descarga_durante: bool = False, excel_vivo=None):
        self.cfg, self.excel, self.indice, self.grupo = cfg, excel, indice, grupo
        self.provincias, self.desde, self.raiz, self.todo = provincias, desde, raiz, todo
        self.descarga_durante = descarga_durante
        self.excel_vivo = excel_vivo
        self.total_ok = self.total_mal = 0
        self._plan: dict[str, TareaDescarga] | None = None
        self._cruces: list[ResultadoCruce] = []
        self.estados: Counter = Counter()

    # --- cruce -----------------------------------------------------------------------------------
    def calcular_plan(self) -> dict[str, TareaDescarga]:
        m = self.cfg.matching
        mensajes = self.indice.mensajes(self.grupo)
        resultados = [r for r in asociar_mensajes(mensajes, m.patron_codigo_regex, m.ventana_minutos_mensaje_separado, m.patron_elemento_regex)
                      if r.mensaje.timestamp >= self.desde and r.mensaje.n_adjuntos > 0]
        cruces = cruzar(resultados, self.excel, m.margen_horas_evidencia, self.provincias)
        self.estados = Counter(c.estado for c in cruces)
        self._cruces = cruces
        hechas = {i for i, (est, _) in self.indice.estado_descarga(self.grupo).items() if est is not None}
        return plan_descargas(cruces, self.raiz, self.grupo, hechas, self.todo)

    def resumen_cruce(self) -> str:
        """Una línea para el log: cuánto se bajará y cuánto se descarta (y por qué)."""
        cruces = self._cruces
        con_fila = [c for c in cruces if c.fila is not None]
        incid = {c.fila.fila_excel for c in con_fila}
        desc = Counter(c.estado for c in cruces if c.fila is None)
        por_dia = Counter(f"{c.match.mensaje.timestamp:%m-%d}" for c in con_fila)
        return (f"CRUCE EN VIVO: {len(cruces)} paquetes con adjunto desde {self.desde:%Y-%m-%d} -> {len(con_fila)} cruzan con "
                f"{len(incid)} incidencias (se bajarán); {len(cruces) - len(con_fila)} se descartan "
                f"({', '.join(f'{k}: {v}' for k, v in desc.items()) or 'ninguno'}). Por día: "
                f"{', '.join(f'{d}={n}' for d, n in sorted(por_dia.items())) or '-'}")

    def procesar(self, pagina: Page) -> None:
        """Tras cada tanda (hay mensajes nuevos): se recalcula el cruce y se informa en el log."""
        t0 = time.time()
        self._plan = self.calcular_plan()
        resumen = self.resumen_cruce()
        logger.info("%s [cruce %.1fs; por bajar: %d]", resumen, time.time() - t0, len(self._plan))
        eventos.evento(self.grupo, "subida", "cruce_en_vivo", "ok", resumen)
        if self.excel_vivo is not None:
            self.excel_vivo.actualizar(self.indice, self.excel)  # throttled: no más de una vez cada ~90 s
        if self.descarga_durante:
            self.en_ciclo(pagina)

    def en_ciclo(self, pagina: Page) -> None:
        """Opcional (descarga_durante): en cada ciclo de subida baja lo pendiente que esté entre lo pintado."""
        if self._plan is None:
            self._plan = self.calcular_plan()
        if not self._plan:
            return
        pintados = set(pagina.evaluate(_JS_IDS_PINTADOS))
        mios = {i: t for i, t in self._plan.items() if i in pintados}
        if not mios:
            return
        ok, mal = descargar_visibles(pagina, mios, self.indice, self.grupo, max_pasos=60)
        for i in mios:
            self._plan.pop(i, None)
        self.total_ok += ok
        self.total_mal += mal
        logger.info("  descargas: %d bajados, %d fallidos (acumulado %d/%d; quedan %d por bajar)",
                    ok, mal, self.total_ok, self.total_mal, len(self._plan))

    # --- descarga --------------------------------------------------------------------------------
    def barrido_final(self, pagina: Page, max_pasos: int = 2500, pasadas: int = 3) -> None:
        """
        Recorre TODO el chat de arriba abajo y baja lo pendiente que cruza. Se repite (hasta `pasadas`) con pasos
        más cortos mientras queden mensajes cuya burbuja no se alcanzó a pintar.
        """
        for n in range(1, pasadas + 1):
            plan = self.calcular_plan()
            logger.info("DESCARGA (pasada %d/%d): %s", n, pasadas, self.resumen_cruce())
            logger.info("DESCARGA (pasada %d/%d): %d mensajes por bajar; recorriendo el chat de arriba abajo...", n, pasadas, len(plan))
            if not plan:
                break
            t0 = time.time()
            ok, mal = descargar_visibles(pagina, plan, self.indice, self.grupo, max_pasos=max_pasos, factor=0.4 / n)
            self.total_ok += ok
            self.total_mal += mal
            sin = len(plan) - ok - mal
            logger.info("DESCARGA (pasada %d/%d): %d bajados, %d fallidos, %d sin encontrar su burbuja (%.0fs).", n, pasadas, ok, mal, sin, time.time() - t0)
            eventos.evento(self.grupo, "descarga", f"pasada_{n}", "ok" if not (mal or sin) else "con_pendientes",
                           f"bajados={ok} fallidos={mal} sin_burbuja={sin}")
            if self.excel_vivo is not None:
                self.excel_vivo.actualizar(self.indice, self.excel, forzar=True)
            if not sin:
                break

    def escribir_pendientes(self, ruta: Path) -> int:
        """CSV con lo que cruza con una incidencia pero no se alcanzó a bajar."""
        import csv

        plan = self.calcular_plan()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id_mensaje", "dia", "hora", "remitente", "fila", "codigo", "carpeta_destino", "estado_cruce", "adjuntos_esperados"])
            for t in plan.values():
                w.writerow([t.id_mensaje, t.meta.get("dia"), t.meta.get("hora"), t.meta.get("remitente"), t.meta.get("fila"),
                            t.meta.get("codigo"), t.carpeta, t.estado, t.n_esperadas])
        return len(plan)
