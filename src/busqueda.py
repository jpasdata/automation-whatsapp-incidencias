"""
Punto único para "cruzar un grupo": mensajes del índice -> asociación foto/número (ventana propia del grupo, comentarios de otras
personas como 'probable') -> cruce con el Excel (con los pares aviso->incidencia aprendidos del chat de todos los grupos).
Lo usan el vigilante, la descarga, el reporte Excel y los scripts, para que todos apliquen exactamente las mismas reglas.
"""
from __future__ import annotations

from datetime import datetime

from .aprendizaje import pares_desde_indice
from .config import provincias_de_grupo, ventana_texto_de_grupo
from .cruce import ResultadoCruce, cruzar
from .matcher import asociar_mensajes


def cruces_de_grupo(cfg, excel, indice, grupo: str, desde: datetime, pares: dict[str, str] | None = None) -> list[ResultadoCruce]:
    m = cfg.matching
    if pares is None:
        pares = pares_desde_indice(indice)
    resultados = [
        r for r in asociar_mensajes(
            indice.mensajes(grupo), m.patron_codigo_regex, ventana_texto_de_grupo(cfg, grupo), m.patron_elemento_regex,
            ventana_ajena_minutos=m.ventana_minutos_comentario_ajeno,
        ) if r.mensaje.timestamp >= desde and r.mensaje.n_adjuntos > 0
    ]
    return cruzar(resultados, excel, m.margen_horas_evidencia, provincias_de_grupo(cfg, grupo), pares=pares)
