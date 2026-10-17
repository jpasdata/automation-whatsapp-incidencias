"""
Cruce de las evidencias detectadas en el chat contra el Excel de incidencias.

Lógica pura (sin Playwright ni escritura): recibe los resultados del matcher y
devuelve, por cada foto/paquete, a qué fila del Excel corresponde, con qué
criterio (código -> elemento -> aviso) y si la hora cae en la ventana de la
incidencia. Sirve para ver el resultado "en seco" antes de escribir nada.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.excel.manager import ExcelManager, FilaIncidencia
from src.nucleo.modelos import CriterioBusqueda, ResultadoMatch, TipoOrigenMatch
from src.cruce.validacion_temporal import ResultadoValidacionTemporal, verificar_ventana_horaria


@dataclass
class ResultadoCruce:
    match: ResultadoMatch
    fila: FilaIncidencia | None
    criterio: CriterioBusqueda | None   # None si el mensaje no traía ningún número
    numero: str | None                  # el número que acertó en el Excel
    ventana: ResultadoValidacionTemporal | None
    aprendido: bool = False             # se encontró por un par aviso->incidencia aprendido del chat (no por el aviso del Excel)

    @property
    def estado(self) -> str:
        if not self.match.candidatos:
            return "sin_numero"                 # foto sin ningún número en el chat
        if self.fila is None:
            return "no_encontrada"              # número en el chat, pero no está en el Excel: pedir evidencia
        if self.ventana is not None and not self.ventana.dentro_de_ventana:
            return "revisar_horario"
        if self.match.origen == TipoOrigenMatch.COMENTARIO_AJENO:
            return "probable"                   # el número lo escribió otra persona: a revisar
        return "ok"


def cruzar(
    resultados: list[ResultadoMatch],
    excel: ExcelManager,
    margen_horas: float,
    provincias: set[str] | None = None,
    pares: dict[str, str] | None = None,
) -> list[ResultadoCruce]:
    cruces: list[ResultadoCruce] = []
    for r in resultados:
        if r.origen == TipoOrigenMatch.SIN_CODIGO or not r.candidatos:
            cruces.append(ResultadoCruce(r, None, None, None, None))
            continue
        cands, extra = list(r.candidatos), []
        for c in r.candidatos:  # aviso -> incidencia aprendida del chat (se prueba después de los números propios)
            inc = (pares or {}).get(c)
            if inc and inc not in cands:
                cands.append(inc)
                extra.append(inc)
        fila, criterio, numero = excel.buscar_fila_por_candidatos(cands, provincias)
        if fila is None:
            cruces.append(ResultadoCruce(r, None, CriterioBusqueda.NO_ENCONTRADO, None, None))
            continue
        ventana = verificar_ventana_horaria(r.mensaje.timestamp, fila.fecha_deteccion, fila.fecha_sr, margen_horas)
        cruces.append(ResultadoCruce(r, fila, criterio, numero, ventana, aprendido=bool(numero and numero in extra)))
    return cruces


def resumen(cruces: list[ResultadoCruce]) -> dict:
    por_estado = Counter(c.estado for c in cruces)
    incidencias = {c.fila.fila_excel for c in cruces if c.fila is not None}
    return {
        "paquetes": len(cruces),
        "fotos_videos": sum(c.match.mensaje.n_adjuntos for c in cruces),
        "por_estado": dict(por_estado),
        "incidencias_con_evidencia": len(incidencias),
        "por_origen": dict(Counter(c.match.origen.value for c in cruces)),
        "por_criterio": dict(Counter(c.criterio.value for c in cruces if c.criterio)),
    }
