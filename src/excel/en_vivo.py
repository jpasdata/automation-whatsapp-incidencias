"""
Excel en tiempo real: cada vez que hay mensajes nuevos, descargas o cruces, se reescriben solos (sin pedir nada):
  data/Reportes/Cruce_en_vivo.xlsx                              - reporte con formato (resumen, por incidencia, por día, descargas, sin cruce)
  data/Reportes/RESULTADO_CREACION_INCIDENCIAS_CRUZADO.xlsx     - copia del Excel de incidencias con Estado_Automatico y
                                                                  Ruta_Evidencia llenados en cada fila (el original no se toca)
Se escriben en un archivo temporal y se reemplazan al final; si el Excel está abierto en el PC (bloqueado) se avisa y se
reintenta en la siguiente actualización, sin detener al bot.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from src.nucleo import eventos
from src.nucleo.rutas import R
from src.excel.reporte import analizar_grupo, escribir_cruzado, generar_reporte

logger = logging.getLogger("incidencias_wa")


class ExcelEnVivo:
    def __init__(self, cfg, desde: datetime, grupos: list[str], carpeta: Path | None = None, min_segundos: float = 90):
        self.cfg, self.desde, self.grupos, self.min_segundos = cfg, desde, grupos, min_segundos
        self.carpeta = carpeta or R.reportes_en_vivo
        self._ultimo = 0.0
        self.ruta_reporte = self.carpeta / "Cruce_en_vivo.xlsx"
        self.ruta_cruzado = self.carpeta / "RESULTADO_CREACION_INCIDENCIAS_CRUZADO.xlsx"

    def actualizar(self, indice, excel, forzar: bool = False) -> bool:
        """Reescribe los dos Excel. Respeta `min_segundos` entre actualizaciones salvo `forzar`. True si se escribió."""
        if not forzar and time.time() - self._ultimo < self.min_segundos:
            return False
        t0 = time.time()
        try:
            indexados = set(indice.grupos())
            analisis = [analizar_grupo(self.cfg, excel, indice, g, self.desde) for g in self.grupos if g in indexados]
            if not analisis:
                return False
            generar_reporte(self.cfg, excel, indice, [a["grupo"] for a in analisis], self.desde, self.ruta_reporte, analisis=analisis)
            ruta_original = Path(self.cfg.excel.ruta_archivo)
            filas = escribir_cruzado(self.cfg, analisis, ruta_original, self.ruta_cruzado)
        except PermissionError:
            logger.warning("EXCEL EN VIVO: no se pudo escribir porque el archivo está abierto en Excel; se reintenta en la próxima actualización.")
            return False
        except Exception:  # noqa: BLE001 - el Excel en vivo nunca debe tumbar al bot
            logger.exception("EXCEL EN VIVO: falló la actualización.")
            return False
        self._ultimo = time.time()
        con = sum(1 for a in analisis for i in a["incidencias"] if i["estado"].startswith(("Con evidencia", "Revisar", "Probable")))
        logger.info("EXCEL EN VIVO actualizado (%.0fs): %d filas escritas, %d incidencias con evidencia -> %s", time.time() - t0, filas, con, self.ruta_cruzado)
        eventos.evento("-", "excel_vivo", "actualizado", "ok", f"filas={filas} con_evidencia={con}")
        return True
