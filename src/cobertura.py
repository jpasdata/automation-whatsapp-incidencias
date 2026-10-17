"""
Cobertura: por cada incidencia del Excel (de las provincias que atiende un grupo),
qué evidencia se encontró en el chat. Es lo que Henry necesita ver: qué incidencias
tienen evidencia, con qué criterio, y cuáles hay que pedir.
Lógica pura (recibe filas y cruces ya calculados).
"""
from __future__ import annotations

from datetime import datetime

from .cruce import ResultadoCruce
from .excel_manager import FilaIncidencia

COLUMNAS = [
    "fila_excel", "cod_incidencia", "incidencia", "numero_aviso", "elemento", "provincia",
    "fecha_deteccion", "fecha_sr", "nota_manual_excel", "estado_evidencia",
    "paquetes", "fotos_videos", "primera_hora", "ultima_hora", "criterios", "origenes", "remitentes", "observacion",
]


def cobertura(filas: list[FilaIncidencia], cruces: list[ResultadoCruce]) -> list[dict]:
    """Una fila por incidencia. estado_evidencia: 'con_evidencia' | 'revisar_horario' | 'sin_evidencia'."""
    por_fila: dict[int, list[ResultadoCruce]] = {}
    for c in cruces:
        if c.fila is not None:
            por_fila.setdefault(c.fila.fila_excel, []).append(c)

    salida: list[dict] = []
    for f in filas:
        cs = por_fila.get(f.fila_excel, [])
        horas = sorted(c.match.mensaje.timestamp for c in cs)
        if not cs:
            estado, obs = "sin_evidencia", "No apareció ningún mensaje con este número en el período cargado: pedir evidencia."
        elif any(c.estado == "ok" for c in cs):
            estado, obs = "con_evidencia", ""
        else:
            estado = "revisar_horario"
            obs = "Hay evidencia pero fuera de la ventana horaria de la incidencia: revisar a mano."
        salida.append({
            "fila_excel": f.fila_excel,
            "cod_incidencia": f.codigo_largo,
            "incidencia": f.codigo_corto,
            "numero_aviso": f.numero_aviso,
            "elemento": f.numero_elemento,
            "provincia": f.provincia,
            "fecha_deteccion": f.fecha_deteccion,
            "fecha_sr": f.fecha_sr,
            "nota_manual_excel": f.nota_evidencia_manual,
            "estado_evidencia": estado,
            "paquetes": len(cs),
            "fotos_videos": sum(c.match.mensaje.n_adjuntos for c in cs),
            "primera_hora": horas[0] if horas else None,
            "ultima_hora": horas[-1] if horas else None,
            "criterios": ", ".join(sorted({c.criterio.value for c in cs if c.criterio})),
            "origenes": ", ".join(sorted({c.match.origen.value for c in cs})),
            "remitentes": ", ".join(sorted({c.match.mensaje.remitente for c in cs})),
            "observacion": obs,
        })
    return salida


def resumen_cobertura(filas_cobertura: list[dict], desde: datetime | None = None, hasta: datetime | None = None) -> dict:
    """Totales, opcionalmente solo de las incidencias detectadas entre `desde` y `hasta` (inclusive, por día)."""
    sel = filas_cobertura
    if desde or hasta:
        sel = [
            r for r in filas_cobertura
            if r["fecha_deteccion"] is not None
            and (desde is None or r["fecha_deteccion"].date() >= desde.date())
            and (hasta is None or r["fecha_deteccion"].date() <= hasta.date())
        ]
    total = len(sel)
    con = sum(1 for r in sel if r["estado_evidencia"] == "con_evidencia")
    rev = sum(1 for r in sel if r["estado_evidencia"] == "revisar_horario")
    return {"incidencias": total, "con_evidencia": con, "revisar_horario": rev, "sin_evidencia": total - con - rev}
