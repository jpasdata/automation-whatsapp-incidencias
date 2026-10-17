"""
Fase 0: Exploración. NO descarga nada, NO modifica el Excel, NO envía
mensajes. Solo mira y reporta, para resolver con datos reales las 3
cosas que quedaron pendientes:

  1. Quién debería recibir el recordatorio cuando falta evidencia.
  2. El mapeo nombre de WhatsApp -> número de teléfono.
  3. El formato real del código que escriben en el grupo (corto/largo/variable).

El resultado se guarda en logs/reporte_exploracion_<fecha>.json para
revisarlo con calma, y también se imprime un resumen en consola.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.nucleo.config import load_config, resolver_cargar_desde
from src.nucleo.logger import setup_logger
from src.cruce.matcher import asociar_mensajes
from src.whatsapp.reader import leer_mensajes_recientes, listar_participantes
from src.whatsapp.session import SesionWhatsApp


def ejecutar_exploracion(incluir_participantes: bool = False) -> dict:
    cfg = load_config()
    logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
    logger.info("=== INICIO Fase 0: Exploración (solo lectura, no modifica nada) ===")

    reporte: dict = {
        "fecha_ejecucion": datetime.now().isoformat(),
        "grupos": [],
        "mensajes_con_adjunto": [],
        "codigos_detectados_con_patron_actual": [],
    }

    desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
    logger.info("Histórico a cargar desde: %s", desde or "(lo que haya cargado)")

    with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=cfg.whatsapp.headless, logger=logger) as sesion:
        for grupo in cfg.whatsapp.grupos:
            logger.info("--- Grupo: %s ---", grupo)
            entrada_grupo: dict = {"grupo": grupo, "participantes": [], "error": None}
            reporte["grupos"].append(entrada_grupo)
            try:
                sesion.abrir_chat(grupo)
            except Exception as e:  # noqa: BLE001
                logger.error("No se pudo abrir el grupo '%s': %s", grupo, e)
                entrada_grupo["error"] = str(e)
                continue

            # Abrir el perfil del grupo deja un panel lateral que tapa los mensajes y
            # estorba la lectura, así que por defecto NO se hace (no hace falta para el flujo).
            if incluir_participantes:
                try:
                    participantes = listar_participantes(sesion.pagina)
                    entrada_grupo["participantes"] = participantes
                    logger.info("Participantes encontrados: %d", len(participantes))
                except Exception as e:  # noqa: BLE001
                    logger.error("No se pudo leer la lista de participantes: %s", e)

            mensajes = leer_mensajes_recientes(sesion.pagina, desde=desde)
            entrada_grupo["total_mensajes_leidos"] = len(mensajes)
            entrada_grupo["respuestas_con_cita"] = [
                {"remitente": m.remitente, "texto": m.texto, "cita_autor": m.cita_autor, "cita_texto": m.cita_texto}
                for m in mensajes if m.cita_autor
            ]
            for r in asociar_mensajes(
                mensajes,
                cfg.matching.patron_codigo_regex,
                cfg.matching.ventana_minutos_mensaje_separado,
                cfg.matching.patron_elemento_regex,
            ):
                m = r.mensaje
                reporte["mensajes_con_adjunto"].append({
                    "grupo": grupo,
                    "remitente": m.remitente,
                    "hora": m.timestamp.isoformat(),
                    "texto": m.texto,
                    "tipo_adjunto": m.tipo_adjunto,
                    "n_adjuntos": m.n_adjuntos,
                    "origen_asociacion": r.origen.value,
                    "candidatos": r.candidatos,
                    "codigo_detectado_con_patron_actual": r.codigo,
                })
                if r.codigo:
                    reporte["codigos_detectados_con_patron_actual"].append(r.codigo)

    _guardar_reporte(reporte, cfg.logging.carpeta_logs, logger)
    _imprimir_resumen(reporte, logger)
    return reporte


def _guardar_reporte(reporte: dict, carpeta_logs: str, logger: logging.Logger) -> Path:
    carpeta = Path(carpeta_logs) / "archivo" / "exploracion"
    carpeta.mkdir(parents=True, exist_ok=True)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"reporte_exploracion_{datetime.now():%Y%m%d_%H%M%S}.json"
    ruta = carpeta / nombre
    ruta.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info("Reporte guardado en: %s", ruta)
    return ruta


def _imprimir_resumen(reporte: dict, logger: logging.Logger) -> None:
    total_adjuntos = len(reporte["mensajes_con_adjunto"])
    total_con_codigo = len(reporte["codigos_detectados_con_patron_actual"])
    logger.info("--- RESUMEN ---")
    logger.info("Grupos revisados: %d", len(reporte["grupos"]))
    logger.info("Mensajes con foto/video revisados: %d", total_adjuntos)
    logger.info(
        "De esos, cuántos tenían un código reconocible con el patrón actual: %d (%s)",
        total_con_codigo,
        reporte.get("patron_regex_usado", "ver config.yaml"),
    )
    logger.info(
        "Revisa el JSON completo para decidir: formato real del código, "
        "quién manda qué, y qué número corresponde a cada nombre."
    )


if __name__ == "__main__":
    ejecutar_exploracion()
