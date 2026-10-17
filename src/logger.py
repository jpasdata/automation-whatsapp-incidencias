"""
Logging centralizado. Todo lo que hace la automatización queda escrito en disco, además de mostrarse en consola.

Tres salidas (todas en logs/):
  - automatizacion.log : lo importante (INFO+), un archivo por día, 30 días.
  - detalle.log        : TODO (DEBUG+) con módulo, función y línea; cada ciclo de scroll, cada lectura, cada
                         descarga y cada error con su traza. Es el que sirve para ubicar dónde falló algo.
  - *.csv              : un registro por hecho (ver src/eventos.py): descargas_detalle.csv, eventos_bot.csv.

Por qué: esto corre sin supervisión. Si algo falla a las 3am, estos archivos son la única forma de saber qué pasó.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logger(carpeta_logs: str, nivel: str = "INFO", nombre: str = "incidencias_wa") -> logging.Logger:
    carpeta = Path(carpeta_logs)
    carpeta.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(nombre)
    logger.setLevel(logging.DEBUG)  # el nivel de cada salida se fija en su handler

    # Evita duplicar handlers si setup_logger se llama más de una vez
    # (por ejemplo en tests que importan varios módulos).
    if logger.handlers:
        return logger

    formato = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    formato_detalle = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(module)s.%(funcName)s:%(lineno)d | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    archivo = logging.handlers.TimedRotatingFileHandler(carpeta / "automatizacion.log", when="midnight", backupCount=30, encoding="utf-8")
    archivo.setLevel(logging.INFO)
    archivo.setFormatter(formato)
    logger.addHandler(archivo)

    detalle = logging.handlers.RotatingFileHandler(carpeta / "detalle.log", maxBytes=25_000_000, backupCount=6, encoding="utf-8")
    detalle.setLevel(logging.DEBUG)
    detalle.setFormatter(formato_detalle)
    logger.addHandler(detalle)

    consola = logging.StreamHandler()
    consola.setLevel(nivel.upper())
    consola.setFormatter(formato)
    logger.addHandler(consola)

    def _excepcion_no_atrapada(tipo, valor, tb):
        logger.critical("Excepción no atrapada: el programa se detiene.", exc_info=(tipo, valor, tb))
        sys.__excepthook__(tipo, valor, tb)

    sys.excepthook = _excepcion_no_atrapada
    logger.debug("Logger listo. Carpeta de logs: %s | nivel consola: %s", carpeta.resolve(), nivel.upper())
    return logger
