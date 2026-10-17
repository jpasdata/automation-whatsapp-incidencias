"""
Bot vigilante: se queda con WhatsApp Web abierto TODO EL DÍA, siempre al final de los chats (donde llegan los mensajes
nuevos), así que no necesita volver a subir el histórico. En cada vuelta, por cada grupo:

  1. Lee lo nuevo y lo indexa.
  2. Cruza contra el Excel los últimos `ventana_horas` (48 h): así un comentario que llega HORAS después de las fotos
     (respuesta citando, texto del mismo u otro remitente) identifica fotos ya descargadas.
  3. Baja las fotos/videos nuevos (todos, para no perder nada que luego se identifique) a la carpeta de su día:
        <Grupo>/<día>/<fila>_<código>/        identificada con una incidencia del Excel
        <Grupo>/<día>/_sin_numero/            aún sin número (se espera el comentario; ver `espera_huerfana_h`)
        <Grupo>/<día>/_otras_incidencias/     trae un número que no está en el Excel (de otra persona/provincia)
  4. Si una foto ya descargada se identifica después, MUEVE sus archivos a la carpeta de la incidencia.
  5. Escribe el manifiesto del día (manifiesto_<día>.csv) con cada archivo y cómo se identificó.

Los plazos salen del análisis del comportamiento real del grupo (scripts/analizar_comportamiento.py): las respuestas
citando una foto llegan con mediana de 23 min y hasta ~4,5 h; los textos del mismo remitente, hasta ~40 min.
"""
from __future__ import annotations

import csv
import logging
import random
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import eventos
from .config import provincias_de_grupo
from .cruce import ResultadoCruce, cruzar
from .descargas import RAIZ_EVIDENCIAS, TareaDescarga, _slug, descargar_visibles, plan_descargas
from .excel_manager import ExcelManager
from .indice import Indice
from .matcher import asociar_mensajes
from .whatsapp_reader import _subir_rapido_al_tope, leer_mensajes_recientes
from .whatsapp_session import SesionWhatsApp

logger = logging.getLogger("incidencias_wa")


def carpeta_sin_cruce(c: ResultadoCruce) -> str:
    return "_sin_numero" if c.estado == "sin_numero" else "_otras_incidencias"


def reubicar_identificadas(indice: Indice, grupo: str, destinos: dict[str, TareaDescarga]) -> int:
    """Mueve a su carpeta definitiva los archivos ya descargados cuyo destino cambió (se identificaron tarde)."""
    movidos = 0
    for id_msg, (estado, ruta) in indice.estado_descarga(grupo).items():
        if estado != "ok" or not ruta or id_msg not in destinos:
            continue
        t = destinos[id_msg]
        nuevos, cambio = [], False
        for r in (x for x in ruta.split(";") if x):
            a = Path(r)
            if a.exists() and a.parent != t.carpeta:
                t.carpeta.mkdir(parents=True, exist_ok=True)
                dest = t.carpeta / a.name
                k = 1
                while dest.exists():
                    dest = t.carpeta / f"{a.stem}_{k}{a.suffix}"
                    k += 1
                antigua = a.parent
                shutil.move(str(a), str(dest))
                nuevos.append(dest)
                cambio = True
                try:
                    antigua.rmdir()  # si quedó vacía
                except OSError:
                    pass
            else:
                nuevos.append(a)
        if cambio:
            indice.marcar_descarga(grupo, id_msg, "ok", ";".join(str(n) for n in nuevos))
            movidos += 1
            logger.info("  IDENTIFICADA DESPUÉS: %s %s de %s -> %s (cruce: %s)", t.meta.get("dia"), t.meta.get("hora"),
                        t.meta.get("remitente"), t.carpeta.name, t.meta.get("origen"))
            eventos.evento(grupo, "vigilante", "reubicada", "ok", f"{t.meta.get('dia')} {t.meta.get('hora')} -> {t.carpeta.name} ({t.meta.get('origen')})")
    return movidos


def escribir_manifiestos(indice: Indice, grupo: str, cruces: list[ResultadoCruce], raiz: Path, desde: datetime) -> int:
    """Un manifiesto CSV por día con cada mensaje con adjunto, su resultado y cómo se identificó. Devuelve días escritos."""
    descargas = indice.estado_descarga(grupo)
    por_dia: dict[str, list[list]] = {}
    for c in cruces:
        m = c.match.mensaje
        if m.timestamp < desde:
            continue
        est, ruta = descargas.get(m.id_mensaje, (None, None))
        por_dia.setdefault(f"{m.timestamp:%Y-%m-%d}", []).append([
            m.timestamp.strftime("%H:%M"), m.remitente, m.n_adjuntos, (m.texto or "").replace("\n", " ")[:160],
            c.estado, c.fila.fila_excel if c.fila else "", (c.fila.codigo_largo or c.fila.codigo_corto) if c.fila else "",
            c.numero or "", c.criterio.value if c.criterio else "", c.match.origen.value, ", ".join(c.match.candidatos),
            est or "pendiente", ruta or "", m.id_mensaje,
        ])
    for dia, filas in por_dia.items():
        carpeta = raiz / _slug(grupo, 40) / dia
        carpeta.mkdir(parents=True, exist_ok=True)
        with open(carpeta / f"manifiesto_{dia}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["hora", "remitente", "adjuntos", "leyenda", "estado_cruce", "fila_excel", "codigo", "numero_que_cruzo", "criterio",
                        "como_se_identifico", "numeros_en_el_chat", "descarga", "archivos", "id_mensaje"])
            w.writerows(sorted(filas))
    return len(por_dia)


class Vigilante:
    def __init__(self, cfg, grupos: list[str], crear_excel: Callable[[], ExcelManager], ventana_horas: float = 48,
                 espera_huerfana_h: float = 6, intervalo_seg: tuple[int, int] = (150, 300), todo: bool = True,
                 raiz: Path = RAIZ_EVIDENCIAS, ruta_indice: Path | None = None):
        from .historico import RUTA_INDICE

        self.cfg, self.grupos, self.crear_excel = cfg, grupos, crear_excel
        self.ventana_horas, self.espera_huerfana_h, self.intervalo_seg = ventana_horas, espera_huerfana_h, intervalo_seg
        self.todo, self.raiz, self.ruta_indice = todo, raiz, ruta_indice or RUTA_INDICE
        self.excel: ExcelManager | None = None
        self._excel_mtime = 0.0
        self._excel_cargado_en = 0.0

    # --- Excel: se recarga si cambió el archivo o cada hora --------------------------------------
    def _excel_vigente(self) -> ExcelManager:
        ruta = Path(self.cfg.excel.ruta_archivo)
        mtime = ruta.stat().st_mtime if ruta.exists() else 0
        if self.excel is None or mtime != self._excel_mtime or time.time() - self._excel_cargado_en > 3600:
            if self.excel is not None:
                logger.info("Recargando el Excel (cambió el archivo o pasó 1 hora).")
            self.excel = self.crear_excel()
            self._excel_mtime, self._excel_cargado_en = mtime, time.time()
        return self.excel

    # --- una vuelta por un grupo ---------------------------------------------------------------
    def vuelta_grupo(self, sesion: SesionWhatsApp, indice: Indice, grupo: str, desde_cruce: datetime) -> dict:
        t0 = time.time()
        sesion.abrir_chat(grupo)
        pagina = sesion.pagina
        pagina.wait_for_timeout(random.randint(1500, 3500))
        conocidos = indice.ids(grupo)
        recientes = leer_mensajes_recientes(pagina, max_pasos=40, intentos_tope=0, ids_conocidos=conocidos or None)
        nuevos = indice.guardar(grupo, recientes)
        logger.info("[%s] leído: %d mensajes nuevos (índice %d)", grupo[:30], nuevos, indice.contar(grupo))

        m = self.cfg.matching
        excel = self._excel_vigente()
        provincias = provincias_de_grupo(self.cfg, grupo)
        mensajes = indice.mensajes(grupo)
        resultados = [r for r in asociar_mensajes(mensajes, m.patron_codigo_regex, m.ventana_minutos_mensaje_separado, m.patron_elemento_regex)
                      if r.mensaje.timestamp >= desde_cruce and r.mensaje.n_adjuntos > 0]
        cruces = cruzar(resultados, excel, m.margen_horas_evidencia, provincias)
        destinos = plan_descargas(cruces, self.raiz, grupo, set(), todo=self.todo, sin_cruce_dir=carpeta_sin_cruce)

        movidos = reubicar_identificadas(indice, grupo, destinos)
        hechas = {i for i, (est, _) in indice.estado_descarga(grupo).items() if est is not None}
        pendientes = {i: t for i, t in destinos.items() if i not in hechas}
        bajados = fallidos = 0
        if pendientes:
            logger.info("[%s] por bajar: %d mensajes (cruzan: %d, sin número: %d, otras incidencias: %d)", grupo[:30], len(pendientes),
                        sum(1 for t in pendientes.values() if t.estado != "sin_cruce" or t.meta.get("fila")),
                        sum(1 for t in pendientes.values() if t.carpeta.name == "_sin_numero"),
                        sum(1 for t in pendientes.values() if t.carpeta.name == "_otras_incidencias"))
            ok, mal = descargar_visibles(pagina, pendientes, indice, grupo, max_pasos=120)
            bajados, fallidos = ok, mal
            for _ in range(4):  # lo que no estaba pintado: subir un poco (local, sin pedir al celular) y reintentar
                hechas = {i for i, (est, _) in indice.estado_descarga(grupo).items() if est is not None}
                pendientes = {i: t for i, t in pendientes.items() if i not in hechas}
                if not pendientes:
                    break
                _subir_rapido_al_tope(pagina, max_pasos=6)
                ok, mal = descargar_visibles(pagina, pendientes, indice, grupo, max_pasos=120, desde_arriba=False)
                bajados += ok
                fallidos += mal
        # el manifiesto y el conteo de huérfanas se recalculan con el cruce final
        escribir_manifiestos(indice, grupo, cruces, self.raiz, desde_cruce)
        limite = datetime.now() - timedelta(hours=self.espera_huerfana_h)
        huerfanas = sum(1 for c in cruces if c.estado == "sin_numero" and c.match.mensaje.timestamp < limite)
        esperando = sum(1 for c in cruces if c.estado == "sin_numero" and c.match.mensaje.timestamp >= limite)
        resumen = (f"nuevos={nuevos} bajados={bajados} fallidos={fallidos} reubicados={movidos} "
                   f"esperando_comentario={esperando} huerfanas(>{self.espera_huerfana_h:g}h)={huerfanas} ({time.time() - t0:.0f}s)")
        logger.info("[%s] VUELTA: %s", grupo[:30], resumen)
        eventos.evento(grupo, "vigilante", "vuelta", "ok", resumen)
        return {"nuevos": nuevos, "bajados": bajados, "fallidos": fallidos, "movidos": movidos, "huerfanas": huerfanas}

    # --- bucle principal ---------------------------------------------------------------------------
    def correr(self, detener: Callable[[], bool] = lambda: False, max_vueltas: int | None = None) -> None:
        """La sesión del navegador se abre UNA vez y se mantiene todo el día; solo se recrea si se cae."""
        vuelta = 0
        logger.info("VIGILANTE iniciado: grupos=%s, cruza las últimas %g h, espera %g h antes de dar por huérfana una foto sin número.",
                    self.grupos, self.ventana_horas, self.espera_huerfana_h)
        eventos.evento("-", "vigilante", "inicio", "ok", f"grupos={self.grupos}")
        while not detener() and (max_vueltas is None or vuelta < max_vueltas):
            try:
                with Indice(self.ruta_indice) as indice, SesionWhatsApp(
                    self.cfg.whatsapp.carpeta_sesion, headless=self.cfg.whatsapp.headless, logger=logger
                ) as sesion:
                    while not detener() and (max_vueltas is None or vuelta < max_vueltas):
                        vuelta += 1
                        for grupo in self.grupos:
                            if detener():
                                break
                            try:
                                self.vuelta_grupo(sesion, indice, grupo, datetime.now() - timedelta(hours=self.ventana_horas))
                            except Exception as e:  # noqa: BLE001 - un grupo que falla no detiene a los demás
                                if "closed" in str(e).lower():
                                    raise
                                logger.exception("[%s] falló la vuelta %d (se sigue con el siguiente grupo).", grupo[:30], vuelta)
                                eventos.evento(grupo, "vigilante", "vuelta_fallo", "error", str(e)[:200])
                            time.sleep(random.uniform(8, 25))  # pausa humana entre grupos
                        pausa = random.uniform(*self.intervalo_seg)
                        logger.info("VIGILANTE: vuelta %d completa. Próxima en %.0f s.", vuelta, pausa)
                        fin = time.time() + pausa
                        while time.time() < fin and not detener():
                            time.sleep(1)
            except Exception as e:  # noqa: BLE001 - ventana cerrada / sesión caída: se espera y se reintenta
                logger.exception("Vigilante: se perdió la sesión del navegador (vuelta %d). Reintento en 60 s.", vuelta)
                eventos.evento("-", "vigilante", "sesion_caida", "error", str(e)[:200])
                for _ in range(60):
                    if detener():
                        break
                    time.sleep(1)
        logger.info("VIGILANTE detenido tras %d vuelta(s).", vuelta)
