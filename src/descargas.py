"""
Descarga selectiva de evidencias: solo las fotos/videos que el cruce asocia a una incidencia del Excel
(de las provincias del grupo), organizadas por día e incidencia:

    <raiz>/<Grupo>/<AAAA-MM-DD>/<fila>_<codigo>/<HHMM>_<remitente>_<id>_<n>.jpg

Web solo mantiene pintados ~100 mensajes, así que la descarga se hace "al vuelo": justo después de cada
tanda cargada, se recorre lo pintado y se baja lo pendiente que ya cruza con una incidencia.
"""
from __future__ import annotations

import logging
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page

from .cruce import ResultadoCruce, cruzar
from .excel_manager import ExcelManager
from .indice import Indice
from .matcher import asociar_mensajes
from .whatsapp_reader import _JS_BAJAR_TRAMO, _JS_IR_ARRIBA, descargar_adjunto

logger = logging.getLogger(__name__)

RAIZ_EVIDENCIAS = Path(__file__).resolve().parent.parent / "data" / "Evidencias_WhatsApp"


def _slug(texto: str | None, largo: int = 24) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return (re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-") or "sin-nombre")[:largo]


@dataclass
class TareaDescarga:
    id_mensaje: str
    carpeta: Path
    base: str          # nombre sin extensión; se le añade _<n> por cada foto del mensaje
    n_esperadas: int
    estado: str        # estado del cruce ('ok' | 'revisar_horario')


def plan_descargas(cruces: list[ResultadoCruce], raiz: Path, grupo: str, ya_hechas: set[str]) -> dict[str, TareaDescarga]:
    """Qué bajar: paquetes con adjunto que cruzan con una fila del Excel y aún no descargados."""
    plan: dict[str, TareaDescarga] = {}
    for c in cruces:
        m = c.match.mensaje
        if c.fila is None or not m.id_mensaje or m.n_adjuntos <= 0 or m.id_mensaje in ya_hechas:
            continue
        codigo = c.fila.codigo_largo or c.fila.codigo_corto or c.fila.numero_aviso or "sin-codigo"
        carpeta = raiz / _slug(grupo, 40) / f"{m.timestamp:%Y-%m-%d}" / f"{c.fila.fila_excel}_{_slug(codigo, 30)}"
        base = f"{m.timestamp:%H%M}_{_slug(m.remitente, 14)}_{_slug(m.id_mensaje[-8:], 8)}"
        plan[m.id_mensaje] = TareaDescarga(m.id_mensaje, carpeta, base, m.n_adjuntos, c.estado)
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


def descargar_visibles(
    pagina: Page, plan: dict[str, TareaDescarga], indice: Indice, grupo: str, max_pasos: int = 80,
) -> tuple[int, int]:
    """
    Recorre lo pintado de arriba abajo y descarga las tareas del plan cuyas burbujas aparezcan.
    Marca cada mensaje en el índice ('ok'/'error'). Devuelve (descargadas, fallidas).
    """
    pendientes = dict(plan)
    ok = mal = 0
    pagina.evaluate(_JS_IR_ARRIBA)
    pagina.wait_for_timeout(700)
    for _ in range(max_pasos):
        if not pendientes:
            break
        for id_msg in pagina.evaluate(_JS_IDS_VISIBLES):
            tarea = pendientes.pop(id_msg, None)
            if tarea is None:
                continue
            miniaturas = pagina.locator(f'[data-id="{id_msg}"]').locator('[data-testid="image-thumb"], [data-testid="video-content"]')
            hay_album = pagina.locator(f'[data-id="{id_msg}"]').locator('[data-testid="media-album"]').count() > 0
            rutas: list[str] = []
            if hay_album or miniaturas.count() > 1:
                # Álbum: se abre el primero y se recorren TODOS con "Siguiente" (el chat solo muestra 4 miniaturas).
                rutas = [str(r) for r in descargar_adjunto(pagina, miniaturas.first, tarea.carpeta, tarea.base, todo_el_album=True)]
            else:
                rutas = [str(r) for r in descargar_adjunto(pagina, miniaturas.first, tarea.carpeta, f"{tarea.base}_1")]
            pagina.wait_for_timeout(random.randint(900, 2600))  # ritmo humano entre mensajes
            if rutas:
                indice.marcar_descarga(grupo, id_msg, "ok", ";".join(rutas))
                ok += 1
            else:
                indice.marcar_descarga(grupo, id_msg, "error")
                mal += 1
        if pagina.evaluate(_JS_BAJAR_TRAMO):
            break
        pagina.wait_for_timeout(random.randint(350, 700))
    return ok, mal


class Descargador:
    """Se invoca después de cada tanda: cruza lo indexado y baja lo pendiente que ya cruza."""

    def __init__(self, cfg, excel: ExcelManager, indice: Indice, grupo: str, provincias: set[str] | None,
                 desde: datetime, raiz: Path = RAIZ_EVIDENCIAS):
        self.cfg, self.excel, self.indice, self.grupo = cfg, excel, indice, grupo
        self.provincias, self.desde, self.raiz = provincias, desde, raiz
        self.total_ok = self.total_mal = 0

    def calcular_plan(self) -> dict[str, TareaDescarga]:
        m = self.cfg.matching
        mensajes = self.indice.mensajes(self.grupo)
        resultados = [r for r in asociar_mensajes(mensajes, m.patron_codigo_regex, m.ventana_minutos_mensaje_separado, m.patron_elemento_regex)
                      if r.mensaje.timestamp >= self.desde]
        cruces = cruzar(resultados, self.excel, m.margen_horas_evidencia, self.provincias)
        hechas = {i for i, (est, _) in self.indice.estado_descarga(self.grupo).items() if est is not None}
        return plan_descargas(cruces, self.raiz, self.grupo, hechas)

    def procesar(self, pagina: Page) -> None:
        plan = self.calcular_plan()
        if not plan:
            return
        ok, mal = descargar_visibles(pagina, plan, self.indice, self.grupo)
        self.total_ok += ok
        self.total_mal += mal
        logger.info("  descargas: %d mensajes bajados, %d fallidos (acumulado %d/%d; pendientes sin burbuja pintada: %d)",
                    ok, mal, self.total_ok, self.total_mal, len(plan) - ok - mal)

    def escribir_pendientes(self, ruta: Path) -> int:
        """CSV con lo que cruza con una incidencia pero no se alcanzó a bajar (su burbuja no estuvo pintada)."""
        import csv

        plan = self.calcular_plan()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id_mensaje", "carpeta_destino", "estado_cruce", "adjuntos_esperados"])
            for t in plan.values():
                w.writerow([t.id_mensaje, t.carpeta, t.estado, t.n_esperadas])
        return len(plan)
