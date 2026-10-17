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
import json
import logging
import random
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import eventos
from .config import provincias_de_grupo
from .cruce import ResultadoCruce, cruzar
from .descargas import RAIZ_EVIDENCIAS, TareaDescarga, slug_grupo, descargar_visibles, etiqueta_identificador, plan_descargas
from .excel_manager import ExcelManager
from .indice import Indice
from .matcher import asociar_mensajes
from .busqueda import cruces_de_grupo
from .modelos import Mensaje
from .whatsapp_reader import cargar_hacia_arriba, cosechar, leer_mensajes_recientes
from .whatsapp_session import SesionWhatsApp

logger = logging.getLogger("incidencias_wa")


def hay_hueco(recientes: list[Mensaje], conocidos: set[str]) -> bool:
    """True si lo leído NO se empalma con lo ya indexado: llegaron más mensajes de los que caben en pantalla mientras no se miraba."""
    return bool(conocidos) and bool(recientes) and not any(m.id_mensaje in conocidos for m in recientes)


def carpeta_sin_cruce(c: ResultadoCruce) -> str:
    return "_sin_numero" if c.estado == "sin_numero" else "_otras_incidencias"


def nombre_final(a: Path, t: TareaDescarga) -> str:
    """Nombre que debe llevar el archivo: <base con identificador>_<n>.<ext> (conserva el número de foto del álbum)."""
    m = re.search(r"_(\d+)$", a.stem)
    return f"{t.base}_{m.group(1) if m else 1}{a.suffix}"


def reubicar_identificadas(indice: Indice, grupo: str, destinos: dict[str, TareaDescarga]) -> int:
    """
    Mueve/renombra a su carpeta definitiva los archivos ya descargados cuyo destino cambió (se identificaron tarde, o
    cambió la regla de carpetas). A prueba de fallos: un archivo que no se puede mover se registra y se sigue; si el
    índice apunta a un archivo que ya no está en la ruta vieja pero sí en la nueva, se corrige el índice.
    """
    movidos = 0
    for id_msg, (estado, ruta) in indice.estado_descarga(grupo).items():
        if estado != "ok" or not ruta or id_msg not in destinos:
            continue
        t = destinos[id_msg]
        nuevos, cambio = [], False
        for r in (x for x in ruta.split(";") if x):
            a = Path(r)
            final = t.carpeta / nombre_final(a, t)
            if not a.exists():
                if final.exists():  # ya estaba movido pero el índice no lo sabía
                    nuevos.append(final)
                    cambio = True
                else:
                    logger.warning("  Archivo registrado que ya no existe: %s", a)
                continue
            if a == final:
                nuevos.append(a)
                continue
            try:
                final.parent.mkdir(parents=True, exist_ok=True)
                dest, k = final, 1
                while dest.exists():
                    dest = final.with_name(f"{final.stem}_x{k}{final.suffix}")
                    k += 1
                antigua = a.parent
                shutil.move(str(a), str(dest))
                nuevos.append(dest)
                cambio = True
                try:
                    antigua.rmdir()  # si quedó vacía
                except OSError:
                    pass
            except OSError as e:
                logger.error("  No se pudo mover %s -> %s: %s", a.name, final.parent, e)
                nuevos.append(a)
        if cambio:
            indice.marcar_descarga(grupo, id_msg, "ok", ";".join(str(n) for n in nuevos))
            movidos += 1
            logger.info("  REORGANIZADA: %s %s de %s -> %s/%s (cruce: %s)", t.meta.get("dia"), t.meta.get("hora"),
                        t.meta.get("remitente"), t.carpeta.parent.name, t.carpeta.name, t.meta.get("origen"))
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
            m.timestamp.strftime("%H:%M"), etiqueta_identificador(c) or "(sin número)", m.remitente, m.n_adjuntos, (m.texto or "").replace("\n", " ")[:160],
            c.estado, c.fila.fila_excel if c.fila else "", (c.fila.codigo_largo or c.fila.codigo_corto) if c.fila else "",
            c.numero or "", c.criterio.value if c.criterio else "", c.match.origen.value + (" +aprendido" if c.aprendido else ""), ", ".join(c.match.candidatos),
            est or "pendiente", ruta or "", m.id_mensaje,
        ])
    for dia, filas in por_dia.items():
        carpeta = raiz / slug_grupo(grupo) / dia
        carpeta.mkdir(parents=True, exist_ok=True)
        with open(carpeta / f"manifiesto_{dia}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["hora", "identificador", "remitente", "adjuntos", "leyenda", "estado_cruce", "fila_excel", "codigo", "numero_que_cruzo", "criterio",
                        "como_se_identifico", "numeros_en_el_chat", "descarga", "archivos", "id_mensaje"])
            w.writerows(sorted(filas))
    return len(por_dia)


class Vigilante:
    def __init__(self, cfg, grupos: list[str], crear_excel: Callable[[], ExcelManager], ventana_horas: float = 48,
                 espera_huerfana_h: float = 6, intervalo_seg: tuple[int, int] = (150, 300), todo: bool = True,
                 raiz: Path = RAIZ_EVIDENCIAS, ruta_indice: Path | None = None, ponerse_al_dia: bool = False, excel_vivo=None):
        from .historico import RUTA_INDICE

        self.cfg, self.grupos, self.crear_excel = cfg, grupos, crear_excel
        self.ventana_horas, self.espera_huerfana_h, self.intervalo_seg = ventana_horas, espera_huerfana_h, intervalo_seg
        self.todo, self.raiz, self.ruta_indice = todo, raiz, ruta_indice or RUTA_INDICE
        self.ponerse_al_dia = ponerse_al_dia
        self._arranque: set[str] = set()
        self.ruta_estado = Path(cfg.logging.carpeta_logs) / "vigilante_estado.json"
        self.excel_vivo = excel_vivo
        self._al_dia: set[str] = set()
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
        primera = grupo not in self._arranque
        self._arranque.add(grupo)
        conocidos = indice.ids(grupo)
        ultimo_previo = indice.rango(grupo)[1]
        if primera:
            if ultimo_previo:
                horas = (datetime.now() - ultimo_previo).total_seconds() / 3600
                logger.info("[%s] REANUDANDO: el último mensaje indexado es de %s (hace %.1f h) y hay %d mensajes ya conocidos; se sigue desde ahí "
                            "y se vuelve a cruzar todo lo reciente.", grupo[:30], ultimo_previo, horas, len(conocidos))
                eventos.evento(grupo, "vigilante", "reanudando", "ok", f"ultimo={ultimo_previo:%Y-%m-%d %H:%M} ausente_h={horas:.1f}")
                desde_cruce = min(desde_cruce, ultimo_previo - timedelta(hours=24))
            else:
                logger.info("[%s] PRIMERA VEZ: no hay nada indexado de este grupo; se empieza con lo que se vea ahora.", grupo[:30])
        recientes = leer_mensajes_recientes(pagina, max_pasos=40, intentos_tope=0, ids_conocidos=conocidos or None)
        hueco = hay_hueco(recientes, conocidos)
        nuevos = indice.guardar(grupo, recientes)
        hueco_cerrado = False
        if hueco:
            logger.warning("[%s] HUECO: lo leído no se empalma con lo indexado (último conocido %s): llegaron más mensajes de los que caben "
                           "en pantalla mientras no se miraba.", grupo[:30], ultimo_previo)
            eventos.evento(grupo, "vigilante", "hueco_detectado", "aviso", f"ultimo_conocido={ultimo_previo}")
            if self.ponerse_al_dia:
                nuevos += self._cerrar_hueco(pagina, indice, grupo, ultimo_previo)
                hueco_cerrado = True
            else:
                logger.warning("[%s] HUECO SIN CERRAR (--sin-mouse): esos mensajes no se leerán. Usa scripts/cargar_historico.py para recuperarlos.", grupo[:30])
        logger.info("[%s] leído: %d mensajes nuevos (índice %d)", grupo[:30], nuevos, indice.contar(grupo))

        excel = self._excel_vigente()
        cruces = cruces_de_grupo(self.cfg, excel, indice, grupo, desde_cruce)
        destinos = plan_descargas(cruces, self.raiz, grupo, set(), todo=self.todo, sin_cruce_dir=carpeta_sin_cruce)

        movidos = reubicar_identificadas(indice, grupo, destinos)
        hechas = {i for i, (est, _) in indice.estado_descarga(grupo).items() if est is not None}
        pendientes = {i: t for i, t in destinos.items() if i not in hechas}
        bajados = fallidos = 0
        if pendientes:
            logger.info("[%s] por bajar: %d mensajes (cruzan: %d, sin número: %d, otras incidencias: %d)", grupo[:30], len(pendientes),
                        sum(1 for t in pendientes.values() if t.estado != "sin_cruce" or t.meta.get("fila")),
                        sum(1 for t in pendientes.values() if "_sin_numero" in t.carpeta.parts),
                        sum(1 for t in pendientes.values() if "_otras_incidencias" in t.carpeta.parts))
            ok, mal = descargar_visibles(pagina, pendientes, indice, grupo, max_pasos=900 if hueco_cerrado else 120)
            bajados, fallidos = ok, mal
            hechas = {i for i, (est, _) in indice.estado_descarga(grupo).items() if est is not None}
            pendientes = {i: t for i, t in pendientes.items() if i not in hechas}
            if pendientes and self.ponerse_al_dia and grupo not in self._al_dia:
                # Lo más viejo ya no está pintado: Web solo pide mensajes antiguos con la rueda REAL del mouse
                # (bajar y subir), así que se sube como una persona hasta cubrir la ventana. Una vez por grupo.
                logger.info("[%s] %d mensajes anteriores fuera de pantalla: PONIÉNDOSE AL DÍA (sube con el mouse; no lo toques).",
                            grupo[:30], len(pendientes))
                self._al_dia.add(grupo)
                st = cargar_hacia_arriba(pagina, desde=desde_cruce, max_seg=900, rueda_real=True)
                logger.info("[%s] subida de puesta al día: %s", grupo[:30], st)
                ok, mal = descargar_visibles(pagina, pendientes, indice, grupo, max_pasos=800)
                bajados += ok
                fallidos += mal
                hechas = {i for i, (est, _) in indice.estado_descarga(grupo).items() if est is not None}
                pendientes = {i: t for i, t in pendientes.items() if i not in hechas}
            if pendientes:
                logger.info("[%s] %d mensajes siguen sin bajar (no están pintados; se bajan con --ponerse-al-dia o scripts/cargar_historico.py).",
                            grupo[:30], len(pendientes))
        # el manifiesto y el conteo de huérfanas se recalculan con el cruce final
        escribir_manifiestos(indice, grupo, cruces, self.raiz, desde_cruce)
        limite = datetime.now() - timedelta(hours=self.espera_huerfana_h)
        huerfanas = sum(1 for c in cruces if c.estado == "sin_numero" and c.match.mensaje.timestamp < limite)
        esperando = sum(1 for c in cruces if c.estado == "sin_numero" and c.match.mensaje.timestamp >= limite)
        resumen = (f"nuevos={nuevos} bajados={bajados} fallidos={fallidos} reubicados={movidos} "
                   f"esperando_comentario={esperando} huerfanas(>{self.espera_huerfana_h:g}h)={huerfanas} ({time.time() - t0:.0f}s)")
        logger.info("[%s] VUELTA: %s", grupo[:30], resumen)
        eventos.evento(grupo, "vigilante", "vuelta", "ok", resumen)
        self._guardar_estado(grupo, indice, resumen, len(pendientes) if pendientes else 0)
        if self.excel_vivo is not None:  # Excel en tiempo real: se reescribe cuando hubo algo nuevo
            self.excel_vivo.actualizar(indice, excel, forzar=bool(nuevos or bajados or movidos))
        return {"nuevos": nuevos, "bajados": bajados, "fallidos": fallidos, "movidos": movidos, "huerfanas": huerfanas}

    def _cerrar_hueco(self, pagina, indice: Indice, grupo: str, ultimo_previo: datetime | None) -> int:
        """Sube como una persona (rueda real) hasta empalmar con lo ya indexado, guardando cada tanda."""
        conocidos = indice.ids(grupo)
        total = 0
        logger.info("[%s] CERRANDO EL HUECO: subiendo con el mouse hasta empalmar con lo indexado (no lo toques unos minutos).", grupo[:30])

        def guardar_tanda() -> None:
            nonlocal total
            ms = cosechar(pagina, ids_conocidos=conocidos or None, espera_paso_ms=350)
            n = indice.guardar(grupo, ms)
            total += n
            conocidos.update(m.id_mensaje for m in ms if m.id_mensaje)
            logger.info("[%s]   tanda del hueco: %d mensajes nuevos", grupo[:30], n)

        desde = (ultimo_previo or datetime.now()) - timedelta(hours=1)
        st = cargar_hacia_arriba(pagina, desde=desde, max_seg=1500, rueda_real=True, al_tanda=guardar_tanda)
        ms = cosechar(pagina, ids_conocidos=conocidos or None)
        total += indice.guardar(grupo, ms)
        logger.info("[%s] hueco cerrado: %d mensajes recuperados (%s)", grupo[:30], total, st)
        eventos.evento(grupo, "vigilante", "hueco_cerrado", "ok", f"recuperados={total}")
        return total

    def _guardar_estado(self, grupo: str, indice: Indice, resumen: str, pendientes: int) -> None:
        """logs/vigilante_estado.json: dónde quedó cada grupo (para saber por dónde seguir y poder revisarlo a mano)."""
        try:
            estado = json.loads(self.ruta_estado.read_text(encoding="utf-8")) if self.ruta_estado.exists() else {}
        except (OSError, ValueError):
            estado = {}
        primero, ultimo = indice.rango(grupo)
        estado[grupo] = {
            "ultimo_mensaje_indexado": ultimo.isoformat(timespec="minutes") if ultimo else None,
            "mensaje_mas_antiguo": primero.isoformat(timespec="minutes") if primero else None,
            "mensajes_en_indice": indice.contar(grupo), "ultima_vuelta": datetime.now().isoformat(timespec="seconds"),
            "pendientes_por_bajar": pendientes, "resumen_ultima_vuelta": resumen,
        }
        try:
            self.ruta_estado.parent.mkdir(parents=True, exist_ok=True)
            self.ruta_estado.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _mostrar_estado_guardado(self) -> None:
        if not self.ruta_estado.exists():
            logger.info("VIGILANTE: no hay estado guardado de una corrida anterior (primera vez).")
            return
        try:
            estado = json.loads(self.ruta_estado.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for g, e in estado.items():
            logger.info("VIGILANTE - última vez en '%s': vuelta %s | último mensaje indexado %s | %s mensajes | pendientes por bajar: %s",
                        g[:34], e.get("ultima_vuelta"), e.get("ultimo_mensaje_indexado"), e.get("mensajes_en_indice"), e.get("pendientes_por_bajar"))

    # --- bucle principal ---------------------------------------------------------------------------
    def correr(self, detener: Callable[[], bool] = lambda: False, max_vueltas: int | None = None) -> None:
        """La sesión del navegador se abre UNA vez y se mantiene todo el día; solo se recrea si se cae."""
        vuelta = 0
        logger.info("VIGILANTE iniciado: grupos=%s, cruza las últimas %g h, espera %g h antes de dar por huérfana una foto sin número.",
                    self.grupos, self.ventana_horas, self.espera_huerfana_h)
        eventos.evento("-", "vigilante", "inicio", "ok", f"grupos={self.grupos}")
        self._mostrar_estado_guardado()
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
