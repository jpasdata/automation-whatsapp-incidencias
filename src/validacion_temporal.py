"""
Segundo criterio de Henry: una vez identificado a qué incidencia
pertenece el mensaje con la evidencia, hay que revisar si la evidencia
fue tomada DENTRO de las horas en que ocurrió/se resolvió esa
incidencia (entre Fecha Detección y Fecha SR), no en cualquier momento.

Esto evita el error de asociar por código una foto que en realidad es
de otro momento o de otra visita (puede pasar si dos incidencias
comparten circuito/zona y el supervisor confunde el código).

IMPORTANTE - valor pendiente de confirmar con Jeam/Henry:
El margen de tolerancia (MARGEN_HORAS_DEFECTO) es un punto de partida,
no un número definitivo. En campo es normal que la foto/video se mande
un rato después de terminar la reparación (al volver a tener señal, al
llegar al siguiente sitio, etc.), así que un margen de 0 horas sería
demasiado estricto y rechazaría evidencia válida. Ajustar en
config.yaml -> matching.margen_horas_evidencia según lo que muestre la
Fase 0 contra casos reales.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MARGEN_HORAS_DEFECTO = 4


@dataclass
class ResultadoValidacionTemporal:
    dentro_de_ventana: bool
    motivo: str


def verificar_ventana_horaria(
    timestamp_evidencia: datetime | None,
    fecha_deteccion: datetime | None,
    fecha_sr: datetime | None,
    margen_horas: float = MARGEN_HORAS_DEFECTO,
) -> ResultadoValidacionTemporal:
    """
    Evalúa si `timestamp_evidencia` (cuándo se mandó la foto/video en
    WhatsApp) cae dentro de [fecha_deteccion, fecha_sr + margen_horas].

    Si al Excel le falta Fecha Detección o Fecha SR para esa fila, no
    se puede validar -> se deja pasar con una advertencia explícita en
    el motivo, en vez de rechazar evidencia solo porque falta un dato.
    """
    if timestamp_evidencia is None:
        return ResultadoValidacionTemporal(
            dentro_de_ventana=False,
            motivo="No se pudo determinar la hora en que se envió la evidencia.",
        )

    if fecha_deteccion is None or fecha_sr is None:
        return ResultadoValidacionTemporal(
            dentro_de_ventana=True,
            motivo="No se validó la ventana horaria: el Excel no tiene Fecha Detección y/o Fecha SR para esta fila.",
        )

    limite_inferior = fecha_deteccion
    limite_superior = fecha_sr + timedelta(hours=margen_horas)

    if limite_inferior <= timestamp_evidencia <= limite_superior:
        return ResultadoValidacionTemporal(
            dentro_de_ventana=True,
            motivo=(
                f"La evidencia se envió dentro de la ventana esperada "
                f"({limite_inferior} a {limite_superior})."
            ),
        )

    if timestamp_evidencia < limite_inferior:
        return ResultadoValidacionTemporal(
            dentro_de_ventana=False,
            motivo=(
                f"La evidencia se envió ANTES de la Fecha Detección ({limite_inferior}); "
                f"revisar a mano, puede ser de otra incidencia."
            ),
        )

    return ResultadoValidacionTemporal(
        dentro_de_ventana=False,
        motivo=(
            f"La evidencia se envió DESPUÉS del límite permitido ({limite_superior}, "
            f"Fecha SR + {margen_horas}h de margen); revisar a mano."
        ),
    )
