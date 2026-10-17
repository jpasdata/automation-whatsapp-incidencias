"""
Aprendizaje de pares aviso <-> incidencia a partir del propio chat.

El Excel trae `NUMERO AVISO` solo en una parte de las filas, pero la gente identifica sus fotos por aviso. A veces escribe
los dos números juntos ("Aviso 5636582 ... Incidencia 1170118") o uno justo después del otro. Esos pares permiten encontrar la
fila del Excel por su incidencia aunque su aviso no esté anotado. Solo se usan pares que no se contradicen.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Iterable

from src.nucleo.modelos import Mensaje

RX_AVISO = re.compile(r"\b(5\d{2})-?(\d{4})\b")
RX_INCID = re.compile(r"\b(11\d{5})\b")
RX_LARGO = re.compile(r"\b0(11\d{5})\d{4}\b")  # 12 dígitos: 0 + incidencia corta + 0001


def avisos_en(texto: str | None) -> list[str]:
    return list(dict.fromkeys(a + b for a, b in RX_AVISO.findall(texto or "")))


def incidencias_en(texto: str | None) -> list[str]:
    t = texto or ""
    return list(dict.fromkeys(RX_INCID.findall(t) + RX_LARGO.findall(t)))


def aprender_pares(mensajes: Iterable[Mensaje], ventana_adyacente_min: float = 3) -> dict[str, str]:
    """
    {aviso: incidencia_corta}. Dos fuentes:
      1. El mismo mensaje trae exactamente un aviso y una incidencia.
      2. Un texto con una incidencia (sin aviso) está a <= `ventana_adyacente_min` de otro mensaje del MISMO remitente que
         trae exactamente un aviso (sin incidencia).
    Si un aviso queda asociado a incidencias distintas, se descarta (ambiguo).
    """
    ms = sorted(mensajes, key=lambda m: m.timestamp)
    votos: dict[str, Counter] = defaultdict(Counter)
    for m in ms:
        a, i = avisos_en(m.texto), incidencias_en(m.texto)
        if len(a) == 1 and len(i) == 1:
            votos[a[0]][i[0]] += 1
    ventana = timedelta(minutes=ventana_adyacente_min)
    for k, m in enumerate(ms):
        inc = incidencias_en(m.texto)
        if len(inc) != 1 or avisos_en(m.texto):
            continue
        vecinos = [ms[j] for j in range(k - 1, -1, -1) if m.timestamp - ms[j].timestamp <= ventana]
        vecinos += [ms[j] for j in range(k + 1, len(ms)) if ms[j].timestamp - m.timestamp <= ventana]
        for o in vecinos:
            if o.remitente == m.remitente and len(avisos_en(o.texto)) == 1 and not incidencias_en(o.texto):
                votos[avisos_en(o.texto)[0]][inc[0]] += 1
                break
    pares = {}
    for aviso, c in votos.items():
        if len(c) == 1:
            pares[aviso] = next(iter(c))
    return pares


def pares_desde_indice(indice) -> dict[str, str]:
    """Pares aprendidos de TODOS los grupos indexados (un aviso identifica a la misma incidencia en cualquier grupo)."""
    todos: list[Mensaje] = []
    for g in indice.grupos():
        todos.extend(indice.mensajes(g))
    return aprender_pares(todos)
