"""
Análisis del COMPORTAMIENTO de quienes reportan evidencias en un grupo, a partir del índice local (sin abrir WhatsApp).
Responde, con números, cosas como: ¿el número va en la foto o en un texto aparte?, ¿antes o después?, ¿cuántos minutos
después?, ¿cuántas fotos por reporte?, ¿quién responde citando?, ¿qué tipo de número usa cada persona?
Sirve para ajustar las reglas del cruce (ventanas, prioridades) y para que el bot vigilante sepa cuánto esperar un
comentario tardío antes de dar una foto por huérfana.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from src.nucleo.modelos import Mensaje

RX_LARGO = re.compile(r"\b0?\d{11,12}\b")                 # COD-INCIDENCIA (12 dígitos)
RX_AVISO = re.compile(r"\b5\d{2}-?\d{4}\b|\b5\d{6}\b")      # N° de aviso: 7 dígitos que empiezan en 56/57 (a veces con guion)
RX_INCID = re.compile(r"\b11\d{5}\b")                       # incidencia corta (7 dígitos que empiezan en 11)
RX_ELEM = re.compile(r"\bF[\s:\-#]?\d{3,6}\b", re.I)        # número de elemento
RX_CUALQ = re.compile(r"\b\d{6,12}\b|\b\d{3}-\d{4}\b")


def tipos_de_numero(texto: str | None) -> set[str]:
    t = texto or ""
    out = set()
    if RX_LARGO.search(t):
        out.add("codigo_largo")
    if RX_INCID.search(t):
        out.add("incidencia")
    if RX_AVISO.search(t):
        out.add("aviso")
    if RX_ELEM.search(t):
        out.add("elemento")
    if not out and RX_CUALQ.search(t):
        out.add("otro_numero")
    return out


def _pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "-"


def _percentiles(v: list[float]) -> str:
    if not v:
        return "sin datos"
    v = sorted(v)
    p = lambda q: v[min(len(v) - 1, int(q * len(v)))]  # noqa: E731
    return f"n={len(v)} | mediana {p(0.5):.0f} min | P75 {p(0.75):.0f} | P90 {p(0.9):.0f} | P95 {p(0.95):.0f} | máx {v[-1]:.0f}"


def _min(a: datetime, b: datetime) -> float:
    return abs((b - a).total_seconds()) / 60


def _rafagas(media: list[Mensaje], max_gap_min: float = 2) -> list[list[Mensaje]]:
    """Fotos/videos seguidos del mismo remitente con menos de `max_gap_min` entre uno y otro."""
    out: list[list[Mensaje]] = []
    for m in media:
        if out and out[-1][-1].remitente == m.remitente and _min(out[-1][-1].timestamp, m.timestamp) <= max_gap_min:
            out[-1].append(m)
        else:
            out.append([m])
    return out


def analizar(mensajes: list[Mensaje]) -> dict:
    ms = sorted(mensajes, key=lambda m: m.timestamp)
    media = [m for m in ms if m.n_adjuntos > 0]
    textos = [m for m in ms if m.n_adjuntos == 0 and (m.texto or "").strip()]
    r: dict = {"mensajes": len(ms), "media": len(media), "textos": len(textos),
               "dias": len({m.timestamp.date() for m in ms}), "remitentes": len({m.remitente for m in ms})}

    # --- 1. dónde va el número -----------------------------------------------------------------
    con_leyenda = [m for m in media if (m.texto or "").strip()]
    con_num = [m for m in con_leyenda if tipos_de_numero(m.texto)]
    r["media_con_leyenda"], r["media_leyenda_con_numero"] = len(con_leyenda), len(con_num)
    r["tipos_numero_en_leyenda"] = Counter(t for m in con_num for t in tipos_de_numero(m.texto))
    textos_num = [m for m in textos if tipos_de_numero(m.texto)]
    r["textos_con_numero"] = len(textos_num)
    r["tipos_numero_en_texto_aparte"] = Counter(t for m in textos_num for t in tipos_de_numero(m.texto))

    # --- 2. ráfagas: cuántas fotos por reporte y dónde va la leyenda ----------------------------
    rafagas = _rafagas(media)
    r["rafagas"] = len(rafagas)
    r["tam_rafaga"] = Counter(min(len(g), 12) for g in rafagas)
    pos = Counter()
    for g in rafagas:
        for i, m in enumerate(g):
            if (m.texto or "").strip() and tipos_de_numero(m.texto):
                pos["primera" if i == 0 else "última" if i == len(g) - 1 else "intermedia"] += 1 if len(g) > 1 else 0
                break
    r["posicion_leyenda_en_rafaga"] = pos
    r["rafagas_sin_numero_propio"] = sum(not any(tipos_de_numero(m.texto) for m in g) for g in rafagas)

    # --- 3. texto aparte: ¿antes o después de las fotos? ¿cuántos minutos? ----------------------
    antes_mis, despues_mis, despues_otro, antes_otro = [], [], [], []
    for t in textos_num:
        prev = next((m for m in reversed(ms[: ms.index(t)]) if m.n_adjuntos > 0), None)
        sig = next((m for m in ms[ms.index(t) + 1:] if m.n_adjuntos > 0), None)
        if prev is not None:
            (despues_mis if prev.remitente == t.remitente else despues_otro).append(_min(prev.timestamp, t.timestamp))
        if sig is not None:
            (antes_mis if sig.remitente == t.remitente else antes_otro).append(_min(t.timestamp, sig.timestamp))
    r["texto_despues_de_foto_mismo_remitente"] = despues_mis
    r["texto_antes_de_foto_mismo_remitente"] = antes_mis
    r["texto_despues_de_foto_otro_remitente"] = despues_otro
    r["texto_antes_de_foto_otro_remitente"] = antes_otro

    # --- 4. respuestas citando ---------------------------------------------------------------
    resp = [m for m in ms if m.cita_texto and re.search(r"foto|imagen|video|ic-image|ic-video|📷|🎥", (m.cita_texto or ""), re.I)]
    resp_num = [m for m in resp if tipos_de_numero(m.texto)]
    r["respuestas_a_media"], r["respuestas_a_media_con_numero"] = len(resp), len(resp_num)
    demoras = []
    for m in resp_num:
        previa = next((x for x in reversed(ms[: ms.index(m)]) if x.n_adjuntos > 0 and x.remitente == m.cita_autor), None)
        if previa is not None:
            demoras.append(_min(previa.timestamp, m.timestamp))
    r["demora_respuesta_citada"] = demoras
    r["respuestas_mismo_autor"] = sum(1 for m in resp_num if m.cita_autor == m.remitente)

    # --- 5. por remitente ---------------------------------------------------------------------
    por: dict[str, dict] = defaultdict(lambda: {"media": 0, "leyenda_num": 0, "textos_num": 0, "tipos": Counter(), "horas": Counter(), "rafagas": 0})
    for m in media:
        d = por[m.remitente or "?"]
        d["media"] += 1
        d["horas"][m.timestamp.hour] += 1
        if tipos_de_numero(m.texto):
            d["leyenda_num"] += 1
            d["tipos"].update(tipos_de_numero(m.texto))
    for m in textos_num:
        d = por[m.remitente or "?"]
        d["textos_num"] += 1
        d["tipos"].update(tipos_de_numero(m.texto))
    for g in rafagas:
        por[g[0].remitente or "?"]["rafagas"] += 1
    r["por_remitente"] = dict(por)

    # --- 6. cuántas fotos quedarían huérfanas según la ventana de espera ---------------------------
    def identificada(g: list[Mensaje], ventana: float) -> bool:
        if any(tipos_de_numero(m.texto) for m in g):
            return True
        ini, fin = g[0].timestamp, g[-1].timestamp
        for t in textos_num:
            if t.remitente == g[0].remitente and 0 <= _min(fin, t.timestamp) <= ventana and t.timestamp >= ini:
                return True
            if t.remitente == g[0].remitente and t.timestamp < ini and _min(t.timestamp, ini) <= ventana:
                return True
        return any(c.cita_autor == g[0].remitente and tipos_de_numero(c.texto) and ini <= c.timestamp for c in resp_num
                   if _min(fin, c.timestamp) <= ventana)
    r["huerfanas_por_ventana"] = {v: sum(not identificada(g, v) for g in rafagas) for v in (5, 15, 30, 60, 180, 720, 1440)}
    r["por_hora"] = Counter(m.timestamp.hour for m in media)
    return r


def informe(r: dict, grupo: str = "") -> str:
    L = [f"# Comportamiento de reportes de evidencia{(' - ' + grupo) if grupo else ''}", "",
         f"{r['mensajes']} mensajes en {r['dias']} días de {r['remitentes']} remitentes: {r['media']} con foto/video, {r['textos']} de solo texto.", ""]
    L += ["## 1. ¿Dónde va el número?",
          f"- Fotos/videos con leyenda (texto en el mismo mensaje): {r['media_con_leyenda']} ({_pct(r['media_con_leyenda'], r['media'])} de los adjuntos).",
          f"- De esas, con un número identificable: {r['media_leyenda_con_numero']}. Tipos: {dict(r['tipos_numero_en_leyenda'])}.",
          f"- Mensajes de texto aparte con número: {r['textos_con_numero']}. Tipos: {dict(r['tipos_numero_en_texto_aparte'])}.", ""]
    n_raf = r["rafagas"]
    L += ["## 2. Ráfagas (fotos seguidas del mismo remitente, <=2 min entre una y otra)",
          f"- {n_raf} reportes; fotos por reporte: " + ", ".join(f"{k}{'+' if k == 12 else ''}: {v}" for k, v in sorted(r['tam_rafaga'].items())),
          f"- Posición de la leyenda con número dentro de la ráfaga (cuando hay más de 1): {dict(r['posicion_leyenda_en_rafaga'])}",
          f"- Ráfagas sin ningún número propio: {r['rafagas_sin_numero_propio']} ({_pct(r['rafagas_sin_numero_propio'], n_raf)}) -> dependen de un texto aparte, una respuesta o la ráfaga vecina.", ""]
    L += ["## 3. Texto con número aparte de las fotos (minutos de diferencia)",
          f"- Texto DESPUÉS de las fotos, mismo remitente: {_percentiles(r['texto_despues_de_foto_mismo_remitente'])}",
          f"- Texto ANTES de las fotos, mismo remitente: {_percentiles(r['texto_antes_de_foto_mismo_remitente'])}",
          f"- Texto DESPUÉS, otro remitente (p. ej. coordinador): {_percentiles(r['texto_despues_de_foto_otro_remitente'])}",
          f"- Texto ANTES, otro remitente: {_percentiles(r['texto_antes_de_foto_otro_remitente'])}",
          "  (la foto/mensaje vecino puede no ser el reportado: son cotas para elegir ventanas, no pruebas de relación)", ""]
    dem = r["demora_respuesta_citada"]
    L += ["## 4. Respuestas citando una foto/video",
          f"- Respuestas que citan media: {r['respuestas_a_media']}; con número: {r['respuestas_a_media_con_numero']} "
          f"(de ellas, el autor cita sus propias fotos: {r['respuestas_mismo_autor']}).",
          f"- Demora entre la última foto del citado y la respuesta: {_percentiles(dem)}", ""]
    L += ["## 5. Por remitente", f"{'Remitente':18} {'Adjuntos':>8} {'Reportes':>8} {'Leyenda c/nº':>12} {'Texto c/nº':>10}  Tipos de número / horas pico"]
    for k, d in sorted(r["por_remitente"].items(), key=lambda kv: -kv[1]["media"])[:25]:
        pico = ", ".join(f"{h}h" for h, _ in d["horas"].most_common(3))
        L.append(f"{k[:18]:18} {d['media']:8d} {d['rafagas']:8d} {_pct(d['leyenda_num'], d['media']):>12} {d['textos_num']:10d}  {dict(d['tipos'])} | {pico}")
    L += ["", "## 6. ¿Cuánto esperar antes de dar un reporte por huérfano?",
          "Ráfagas que NO tendrían número según la ventana de espera (minutos) para un texto o respuesta del mismo remitente:"]
    for v, n in r["huerfanas_por_ventana"].items():
        L.append(f"- {v:>5} min: {n} huérfanas ({_pct(n, n_raf)} de las ráfagas)")
    L += ["", "Horas con más fotos/videos: " + ", ".join(f"{h}h={n}" for h, n in r["por_hora"].most_common(6))]
    return "\n".join(L)
