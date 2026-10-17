"""
Logging centralizado. Todo lo que hace la automatización queda escrito
en disco con rotación diaria, además de mostrarse en consola.

Por qué: esto corre sin supervisión (tarea programada). Si algo falla
a las 3am, el log del día es la única forma de saber qué pasó.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logger(carpeta_logs: str, nivel: str = "INFO", nombre: str = "incidencias_wa") -> logging.Logger:
    carpeta = Path(carpeta_logs)
    carpeta.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(nombre)
    logger.setLevel(nivel.upper())

    # Evita duplicar handlers si setup_logger se llama más de una vez
    # (por ejemplo en tests que importan varios módulos).
    if logger.handlers:
        return logger

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Un archivo por día, conserva 30 días de histórico.
    archivo_handler = logging.handlers.TimedRotatingFileHandler(
        carpeta / "automatizacion.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    archivo_handler.setFormatter(formato)
    logger.addHandler(archivo_handler)

    consola_handler = logging.StreamHandler()
    consola_handler.setFormatter(formato)
    logger.addHandler(consola_handler)

    return logger
