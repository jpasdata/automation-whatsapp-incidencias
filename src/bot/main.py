"""
Orquestador de la automatización (alcance actual: Fases 1-2 solamente):
  Fase 1: descarga y clasifica adjuntos del grupo.
  Fase 2: cruza con el Excel (columnas nuevas, sin tocar EVIDENCIA).

NO incluye envío de notificaciones por WhatsApp. Henry confirmó que el
aviso de "falta evidencia" lo maneja él mismo por CORREO, no por
WhatsApp -- así que esta automatización no tiene que avisarle a nadie,
solo dejarle el Excel actualizado con qué se encontró y qué no, para
que él decida a quién pedírsela. `notificador.py` queda en el proyecto
como una idea para una fase futura (ver README, "Fuera de alcance por
ahora"), pero no se usa en este flujo.

Pensado para correr como tarea programada (cada hora, por ejemplo).
Cada corrida queda completa en el log del día, con qué se descargó y
con qué quedó sin encontrar.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.nucleo.config import AppConfig, load_config, provincias_de_grupo, resolver_cargar_desde
from src.excel.manager import ExcelManager
from src.nucleo.logger import setup_logger
from src.cruce.matcher import asociar_mensajes
from src.nucleo.modelos import CriterioBusqueda, TipoOrigenMatch
from src.cruce.validacion_temporal import verificar_ventana_horaria
from src.whatsapp.reader import descargar_adjunto, leer_mensajes_recientes
from src.whatsapp.session import SELECTORES, SesionWhatsApp


def ejecutar_automatizacion() -> None:
    cfg = load_config()
    logger = setup_logger(cfg.logging.carpeta_logs, cfg.logging.nivel)
    logger.info("=== INICIO corrida de automatización ===")

    if not cfg.whatsapp.grupos or "NOMBRE_EXACTO_DEL_GRUPO" in cfg.whatsapp.grupos:
        logger.error(
            "config.yaml todavía tiene el nombre de grupo de ejemplo. "
            "Edítalo antes de correr esto de verdad."
        )
        return

    excel = ExcelManager(
        ruta_archivo=cfg.excel.ruta_archivo,
        nombre_hoja=cfg.excel.nombre_hoja,
        columna_codigo_largo=cfg.excel.columna_codigo_largo,
        columna_codigo_corto=cfg.excel.columna_codigo_corto,
        columna_evidencia_manual=cfg.excel.columna_evidencia_manual,
        columna_estado_automatico=cfg.excel.columna_estado_automatico,
        columna_ruta_foto=cfg.excel.columna_ruta_foto,
        columna_observaciones=cfg.excel.columna_observaciones,
        columna_numero_aviso=cfg.excel.columna_numero_aviso,
        columna_fecha_deteccion=cfg.excel.columna_fecha_deteccion,
        columna_fecha_sr=cfg.excel.columna_fecha_sr,
        columna_provincia=cfg.excel.columna_provincia,
        hojas_extra=cfg.excel.hojas_extra,
    )
    excel.abrir()
    logger.info("Excel abierto: %s (hoja: %s)", cfg.excel.ruta_archivo, cfg.excel.nombre_hoja)

    with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=cfg.whatsapp.headless, logger=logger) as sesion:
        desde = resolver_cargar_desde(cfg.whatsapp.cargar_desde)
        logger.info("Histórico a cargar desde: %s", desde or "(lo que haya cargado)")
        for grupo in cfg.whatsapp.grupos:
            logger.info("--- Grupo: %s ---", grupo)
            try:
                sesion.abrir_chat(grupo)
                mensajes = leer_mensajes_recientes(sesion.pagina, desde=desde)
            except Exception as e:  # noqa: BLE001 - un grupo que falla no debe tumbar a los demás
                logger.error("No se pudo procesar el grupo '%s': %s", grupo, e)
                continue
            resultados = asociar_mensajes(
                mensajes,
                patron_regex=cfg.matching.patron_codigo_regex,
                ventana_minutos=cfg.matching.ventana_minutos_mensaje_separado,
                patron_elemento=cfg.matching.patron_elemento_regex,
            )
            logger.info("Mensajes con adjunto procesados en '%s': %d", grupo, len(resultados))
            _procesar_resultados(resultados, excel, cfg, logger, provincias_de_grupo(cfg, grupo))

    excel.guardar()
    logger.info("Excel actualizado y guardado: %s", cfg.excel.ruta_archivo)
    logger.info(
        "No se envía ninguna notificación por WhatsApp (Henry avisa por correo, "
        "fuera del alcance de esta automatización por ahora)."
    )
    logger.info("=== FIN corrida de automatización ===")


def _procesar_resultados(
    resultados, excel: ExcelManager, cfg: AppConfig, logger: logging.Logger, provincias: set[str] | None = None
) -> None:
    """
    Para cada adjunto detectado:
      1. Si no hay ningún código/número en el mensaje -> SIN_CODIGO, se
         guarda para revisión manual (caso 3 original).
      2. Si hay un número, se busca en el Excel en cascada -- igual que
         lo hace Henry a mano -- probando primero como código de
         incidencia, luego como número de elemento, luego como número
         de aviso (ver excel_manager.buscar_fila_por_identificadores).
      3. Si no aparece por ninguno de los tres -> se marca explícitamente
         "No encontrada, pedir evidencia" (esto es NUEVO: antes se
         guardaba sin más detalle).
      4. Si aparece, se valida que la evidencia se haya enviado dentro
         de la ventana horaria de esa incidencia (Fecha Detección ->
         Fecha SR + margen). Si cae fuera, se guarda igual pero se marca
         para revisión manual en vez de darla por buena automáticamente.
    """
    carpeta_base = Path(cfg.rutas.carpeta_evidencias)
    hoy = datetime.now().strftime("%Y-%m-%d")

    for resultado in resultados:
        numero_detectado = resultado.codigo  # puede ser código, elemento o aviso -- no sabemos cuál hasta buscarlo

        if resultado.origen == TipoOrigenMatch.SIN_CODIGO or not numero_detectado:
            carpeta_destino = carpeta_base / cfg.rutas.carpeta_sin_codigo / hoy
            nombre_archivo = f"{datetime.now():%H-%M-%S}_{resultado.mensaje.remitente}.jpg"
            logger.info("Sin ningún número detectado en el mensaje, se guarda para revisión manual: %s", nombre_archivo)
            _descargar_y_continuar(carpeta_destino, nombre_archivo)
            continue

        candidatos = resultado.candidatos or [numero_detectado]
        fila, criterio, numero_detectado = excel.buscar_fila_por_candidatos(candidatos, provincias)
        numero_detectado = numero_detectado or candidatos[0]

        if criterio == CriterioBusqueda.NO_ENCONTRADO:
            logger.warning(
                "'%s' no se encontró ni como código, ni como número de elemento, "
                "ni como número de aviso. NO ENCONTRADA -> hay que pedir evidencia.",
                numero_detectado,
            )
            carpeta_destino = carpeta_base / cfg.rutas.carpeta_sin_codigo / hoy
            nombre_archivo = f"{numero_detectado}_no_encontrado_en_excel.jpg"
            _descargar_y_continuar(carpeta_destino, nombre_archivo)
            continue

        logger.info("'%s' encontrado en el Excel por criterio: %s (fila %d)", numero_detectado, criterio.value, fila.fila_excel)

        validacion = verificar_ventana_horaria(
            timestamp_evidencia=resultado.mensaje.timestamp,
            fecha_deteccion=fila.fecha_deteccion,
            fecha_sr=fila.fecha_sr,
            margen_horas=cfg.matching.margen_horas_evidencia,
        )
        if not validacion.dentro_de_ventana:
            logger.warning("Evidencia de '%s' fuera de la ventana horaria esperada: %s", numero_detectado, validacion.motivo)
        else:
            logger.info("Validación horaria de '%s': %s", numero_detectado, validacion.motivo)

        carpeta_destino = carpeta_base / cfg.rutas.carpeta_identificadas / numero_detectado
        nombre_archivo = f"{numero_detectado}_{hoy}.jpg"

        # NOTA: aquí se necesita el locator real de Playwright de la burbuja
        # para descargar; en este esqueleto se deja la llamada preparada,
        # pendiente de conectar con el locator concreto una vez confirmado
        # el recorrido real de mensajes en Fase 0.
        ruta_descargada = None  # = descargar_adjunto(pagina, burbuja_locator, carpeta_destino, nombre_archivo)

        if ruta_descargada:
            estado = "Descargada" if validacion.dentro_de_ventana else "Descargada_revisar_horario"
        else:
            estado = "Detectada_pendiente_descarga"

        excel.actualizar_estado_automatico(
            fila.fila_excel,
            estado=estado,
            ruta_foto=str(ruta_descargada) if ruta_descargada else None,
        )


def _descargar_y_continuar(carpeta_destino: Path, nombre_archivo: str) -> None:
    """Placeholder explícito para el caso sin match / sin código: hoy solo
    deja la carpeta lista; la descarga real se conecta junto con el resto
    de descargar_adjunto() en Fase 1 (ver nota en README)."""
    carpeta_destino.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    ejecutar_automatizacion()
