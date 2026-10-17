"""
Lógica pura de asociación: dado una lista de mensajes del grupo,
decide a qué número(s) de incidencia corresponde cada foto/video.

Casos reales que cubre (los 3 primeros del usuario; el 4.º lo explicó Henry):
  1. Imagen con el número en el mismo mensaje (pie de foto).
  2. Texto separado ANTES ("esta es la incidencia tal") + fotos poco después,
     del mismo remitente.
  3. Fotos primero y el número DESPUÉS en un texto del mismo remitente:
     a) respondiendo/citando el paquete multimedia -> RESPUESTA (el más fiable);
     b) escribiéndolo suelto -> MENSAJE_POSTERIOR.
  4. Nada de lo anterior -> SIN_CODIGO (no se descarta).

Un texto puede traer varios números a la vez (incidencia, elemento, aviso);
se devuelven todos en `candidatos` para probarlos en cascada contra el Excel.

Este módulo NO toca Playwright, NO toca el filesystem y NO toca Excel.
"""
from __future__ import annotations

import re
from datetime import timedelta

from .modelos import Mensaje, ResultadoMatch, TipoOrigenMatch

# Elementos como "F-15966", "F:08976", "F08977": prefijo F + 3-6 dígitos.
PATRON_ELEMENTO_DEFECTO = r"\bF[\s:\-#]?\d{3,6}\b"


def extraer_codigo(texto: str | None, patron_regex: str) -> str | None:
    """Devuelve el primer código que matchee el patrón, o None."""
    if not texto:
        return None
    match = re.search(patron_regex, texto)
    return match.group(0) if match else None


def normalizar_candidato(valor: str) -> str:
    """"f-15966" / "F: 15966" -> "F15966"; los números puros quedan igual."""
    return re.sub(r"[\s:\-#]", "", valor).upper()


def extraer_candidatos(texto: str | None, patrones: list[str]) -> list[str]:
    """Todos los números que matcheen cualquier patrón, sin repetir, en orden de aparición."""
    if not texto:
        return []
    encontrados: list[tuple[int, str]] = []
    for patron in patrones:
        for m in re.finditer(patron, texto, flags=re.IGNORECASE):
            encontrados.append((m.start(), normalizar_candidato(m.group(0))))
    vistos: list[str] = []
    for _, valor in sorted(encontrados):
        if valor not in vistos:
            vistos.append(valor)
    return vistos


def asociar_mensajes(
    mensajes: list[Mensaje],
    patron_regex: str,
    ventana_minutos: int = 15,
    patron_elemento: str | None = PATRON_ELEMENTO_DEFECTO,
    ventana_rafaga_minutos: float = 2,
) -> list[ResultadoMatch]:
    """
    Devuelve un ResultadoMatch por cada mensaje con adjunto. Prioridad:
      1. Número en el propio mensaje con el adjunto -> MISMO_MENSAJE.
      2. Un texto con número que CITA ese paquete multimedia -> RESPUESTA.
      3. Texto del MISMO remitente con número, antes o después dentro de
         `ventana_minutos` (gana el más cercano en el tiempo; a igual
         distancia, el anterior) -> MENSAJE_CERCANO / MENSAJE_POSTERIOR.
      4. Ráfaga: foto suelta del mismo remitente a <= `ventana_rafaga_minutos`
         de otra foto que sí quedó con número (en el campo mandan varias fotos
         sueltas seguidas y solo una lleva el pie) -> RAFAGA.
      5. SIN_CODIGO.

    Un mismo texto puede servir a varias fotos seguidas (es común mandar
    2-3 fotos de la misma incidencia con el número escrito una sola vez).
    """
    patrones = [patron_regex] + ([patron_elemento] if patron_elemento else [])
    ms = sorted(mensajes, key=lambda m: m.timestamp)  # estable: empates conservan el orden del chat
    candidatos = [extraer_candidatos(m.texto, patrones) for m in ms]

    # Respuestas: texto sin adjunto, con número, que cita un paquete multimedia.
    por_respuesta: dict[int, list[str]] = {}
    for i, m in enumerate(ms):
        if m.tiene_adjunto or not candidatos[i] or not m.cita_autor:
            continue
        destino = _buscar_media_citada(ms, i)
        if destino is not None:
            por_respuesta.setdefault(destino, candidatos[i])

    resultados: list[ResultadoMatch] = []
    for i, msg in enumerate(ms):
        if not msg.tiene_adjunto:
            continue

        if candidatos[i]:
            # Si además alguien respondió citando este paquete con más números
            # (p. ej. el código de incidencia), se suman como candidatos extra.
            propios = candidatos[i] + [c for c in por_respuesta.get(i, []) if c not in candidatos[i]]
            resultados.append(_resultado(msg, propios, TipoOrigenMatch.MISMO_MENSAJE))
        elif i in por_respuesta:
            resultados.append(_resultado(msg, por_respuesta[i], TipoOrigenMatch.RESPUESTA))
        else:
            cercano = _buscar_texto_cercano(ms, candidatos, i, ventana_minutos)
            if cercano:
                resultados.append(_resultado(msg, *cercano))
            else:
                resultados.append(ResultadoMatch(mensaje=msg, codigo=None, origen=TipoOrigenMatch.SIN_CODIGO))
    return _aplicar_rafagas(resultados, timedelta(minutes=ventana_rafaga_minutos))


def _aplicar_rafagas(resultados: list[ResultadoMatch], ventana: timedelta) -> list[ResultadoMatch]:
    """Las fotos sin número heredan el de la foto con número más cercana (mismo remitente, dentro de `ventana`).
    Solo se heredan números de fotos que ya los tenían por sí mismas (no se encadena ráfaga con ráfaga)."""
    firmes = [r for r in resultados if r.origen in (TipoOrigenMatch.MISMO_MENSAJE, TipoOrigenMatch.RESPUESTA)]
    nuevos: list[ResultadoMatch] = []
    for r in resultados:
        if r.origen != TipoOrigenMatch.SIN_CODIGO:
            nuevos.append(r)
            continue
        cercanos = [
            (abs(f.mensaje.timestamp - r.mensaje.timestamp), i, f) for i, f in enumerate(firmes)
            if f.mensaje.remitente == r.mensaje.remitente and abs(f.mensaje.timestamp - r.mensaje.timestamp) <= ventana
        ]
        if not cercanos:
            nuevos.append(r)
            continue
        _, _, vecino = min(cercanos, key=lambda t: (t[0], t[1]))
        nuevos.append(ResultadoMatch(mensaje=r.mensaje, codigo=vecino.codigo, origen=TipoOrigenMatch.RAFAGA, candidatos=list(vecino.candidatos)))
    return nuevos


def _resultado(msg: Mensaje, cands: list[str], origen: TipoOrigenMatch) -> ResultadoMatch:
    return ResultadoMatch(mensaje=msg, codigo=cands[0], origen=origen, candidatos=list(cands))


def _numero_citado(cita_texto: str | None) -> int | None:
    """"6 fotos" -> 6; "7 fotos, 1 video" -> 8; "foto"/"video" -> 1; otro texto -> None."""
    if not cita_texto:
        return None
    partes = re.findall(r"(\d+)?\s*(foto|imagen|imágen|video|vídeo)", cita_texto.lower())
    if not partes:
        return None
    return sum(int(n) if n else 1 for n, _ in partes)


def _buscar_media_citada(ms: list[Mensaje], i: int) -> int | None:
    """
    WhatsApp Web no expone el id del mensaje citado, solo su autor y un
    resumen ("6 fotos"). Se busca hacia atrás un mensaje con adjunto de ese
    autor; si el resumen trae cuántas fotos son y alguna coincide en
    cantidad, gana esa; si no, la más reciente.
    """
    msg = ms[i]
    esperado = _numero_citado(msg.cita_texto)
    mas_reciente: int | None = None
    for j in range(i - 1, -1, -1):
        previo = ms[j]
        if not previo.tiene_adjunto or previo.remitente != msg.cita_autor:
            continue
        if mas_reciente is None:
            mas_reciente = j
        # WhatsApp muestra como máximo 4 miniaturas en un álbum ("+N" el resto)
        if esperado is not None and (previo.n_adjuntos == esperado or (previo.n_adjuntos >= 4 and esperado >= 4)):
            return j
    return mas_reciente


def _buscar_texto_cercano(
    ms: list[Mensaje], candidatos: list[list[str]], i: int, ventana_minutos: int
) -> tuple[list[str], TipoOrigenMatch] | None:
    msg = ms[i]
    ventana = timedelta(minutes=ventana_minutos)

    def _es_texto_valido(j: int) -> bool:
        t = ms[j]
        # Se ignoran textos que son respuesta a OTRO paquete: pertenecen a ese.
        return t.remitente == msg.remitente and not t.tiene_adjunto and bool(candidatos[j]) and not t.cita_autor

    previo = next(
        (j for j in range(i - 1, -1, -1) if msg.timestamp - ms[j].timestamp <= ventana and _es_texto_valido(j)),
        None,
    )
    posterior = next(
        (j for j in range(i + 1, len(ms)) if ms[j].timestamp - msg.timestamp <= ventana and _es_texto_valido(j)),
        None,
    )
    if previo is None and posterior is None:
        return None
    if posterior is None:
        return candidatos[previo], TipoOrigenMatch.MENSAJE_CERCANO
    if previo is None:
        return candidatos[posterior], TipoOrigenMatch.MENSAJE_POSTERIOR
    d_prev = msg.timestamp - ms[previo].timestamp
    d_post = ms[posterior].timestamp - msg.timestamp
    if d_post < d_prev:
        return candidatos[posterior], TipoOrigenMatch.MENSAJE_POSTERIOR
    return candidatos[previo], TipoOrigenMatch.MENSAJE_CERCANO
