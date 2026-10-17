"""
Logging centralizado y ORGANIZADO POR CORRIDA. Cada vez que corre un proceso se crea su propia carpeta:

    logs/corridas/<AAAA-MM-DD>/<HHMMSS>_<modo>/
        automatizacion_001.log   lo importante (INFO+)
        detalle_001.log          TODO (DEBUG+) con módulo, función y línea; sirve para ubicar dónde falló algo
        descargas_detalle.csv    una fila por descarga (resultado, motivo del fallo, tiempos)
        eventos.csv              hitos de la corrida
    logs/ultima_corrida.txt     ruta de la corrida más reciente

Los archivos de log no crecen sin límite: al pasar de cierto tamaño se abre el siguiente (_002, _003…); los anteriores no se tocan.
Un vigilante que corre días enteros genera varios archivos dentro de su carpeta, en vez de uno enorme.

Por qué: esto corre sin supervisión. Si algo falla a las 3am, la carpeta de esa corrida es la única forma de saber qué pasó.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from . import eventos

MAX_AUTOMATIZACION = 3_000_000   # bytes por archivo
MAX_DETALLE = 8_000_000


class ArchivoPorTamano(logging.Handler):
    """Escribe en <prefijo>_001.log y, al pasar de `max_bytes`, sigue en <prefijo>_002.log (sin renombrar ni borrar los anteriores)."""

    def __init__(self, carpeta: Path, prefijo: str, max_bytes: int, nivel: int, formato: logging.Formatter):
        super().__init__(nivel)
        self.carpeta, self.prefijo, self.max_bytes = Path(carpeta), prefijo, max_bytes
        self.setFormatter(formato)
        self.parte, self._tam, self._f = 0, 0, None
        self._abrir()

    def _abrir(self) -> None:
        if self._f:
            self._f.close()
        self.parte += 1
        self._f = open(self.carpeta / f"{self.prefijo}_{self.parte:03d}.log", "a", encoding="utf-8")
        self._tam = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            linea = self.format(record) + "\n"
            if self._tam and self._tam + len(linea.encode("utf-8")) > self.max_bytes:
                self._abrir()
            self._f.write(linea)
            self._f.flush()
            self._tam += len(linea.encode("utf-8"))
        except Exception:  # noqa: BLE001 - un fallo al loguear no debe tumbar al bot
            self.handleError(record)

    def close(self) -> None:
        if self._f:
            self._f.close()
        super().close()


def nueva_carpeta_de_corrida(carpeta_logs: str | Path, modo: str) -> Path:
    ahora = datetime.now()
    modo = "".join(c if c.isalnum() or c in "-_" else "-" for c in modo)[:30] or "corrida"
    d = Path(carpeta_logs) / "corridas" / f"{ahora:%Y-%m-%d}" / f"{ahora:%H%M%S}_{modo}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logger(carpeta_logs: str, nivel: str = "INFO", nombre: str = "incidencias_wa", corrida: str | None = None) -> logging.Logger:
    logger = logging.getLogger(nombre)
    logger.setLevel(logging.DEBUG)  # el nivel de cada salida se fija en su handler

    # Evita duplicar handlers si setup_logger se llama más de una vez (por ejemplo en tests que importan varios módulos).
    if logger.handlers:
        return logger

    modo = corrida or Path(sys.argv[0]).stem or "corrida"
    carpeta = nueva_carpeta_de_corrida(carpeta_logs, modo)
    formato = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    formato_detalle = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(module)s.%(funcName)s:%(lineno)d | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger.addHandler(ArchivoPorTamano(carpeta, "automatizacion", MAX_AUTOMATIZACION, logging.INFO, formato))
    logger.addHandler(ArchivoPorTamano(carpeta, "detalle", MAX_DETALLE, logging.DEBUG, formato_detalle))
    consola = logging.StreamHandler()
    consola.setLevel(nivel.upper())
    consola.setFormatter(formato)
    logger.addHandler(consola)

    eventos.configurar(carpeta)  # los CSV de esta corrida van en su misma carpeta
    try:
        (Path(carpeta_logs) / "ultima_corrida.txt").write_text(str(carpeta), encoding="utf-8")
    except OSError:
        pass

    def _excepcion_no_atrapada(tipo, valor, tb):
        logger.critical("Excepción no atrapada: el programa se detiene.", exc_info=(tipo, valor, tb))
        sys.__excepthook__(tipo, valor, tb)

    sys.excepthook = _excepcion_no_atrapada
    logger.info("Corrida '%s': logs en %s", modo, carpeta)
    return logger
