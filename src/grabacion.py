"""
Grabación de los eventos de entrada que recibe la página mientras una PERSONA hace scroll,
para compararlos con los que genera el script y copiar lo que sí funciona (ritmo, tamaño de
cada giro de rueda, movimientos del mouse, etc.).
"""
from __future__ import annotations

import collections
import statistics

JS_GRABAR = """() => {
  window.__ev = []; window.__t0 = performance.now();
  const push = o => { if (window.__ev.length < 20000) window.__ev.push(o); };
  const t = () => Math.round(performance.now() - window.__t0);
  if (!window.__grabando) {
    window.__grabando = true;
    for (const tipo of ['wheel','mousemove','pointermove','mousedown','mouseup','keydown']) {
      window.addEventListener(tipo, e => {
        const o = {t: t(), tipo, trusted: e.isTrusted};
        if (tipo === 'wheel') { o.dy = Math.round(e.deltaY); o.dm = e.deltaMode; }
        if (tipo.includes('move')) { o.x = Math.round(e.clientX); o.y = Math.round(e.clientY); }
        if (tipo === 'keydown') { o.k = e.key; }
        push(o);
      }, true);
    }
    document.addEventListener('scroll', e => {
      push({t: t(), tipo: 'scroll', trusted: e.isTrusted, top: Math.round(e.target.scrollTop || 0)});
    }, true);
  }
}"""

JS_LEER = "() => window.__ev || []"


def resumir(eventos: list[dict]) -> dict:
    """Métricas del patrón de scroll: cuántas muescas, de qué tamaño, a qué ritmo y en qué ráfagas."""
    wheels = [e for e in eventos if e["tipo"] == "wheel"]
    ints = [b["t"] - a["t"] for a, b in zip(wheels, wheels[1:])]
    # ráfaga = giros separados por menos de 250 ms
    rafagas, actual = [], 0
    for i in ints:
        if i < 250:
            actual += 1
        else:
            rafagas.append(actual + 1)
            actual = 0
    if wheels:
        rafagas.append(actual + 1)
    arriba = [w for w in wheels if w["dy"] < 0]
    abajo = [w for w in wheels if w["dy"] > 0]
    dur = (eventos[-1]["t"] - eventos[0]["t"]) / 1000 if len(eventos) > 1 else 0
    return {
        "duracion_s": round(dur, 1),
        "eventos_por_tipo": dict(collections.Counter(e["tipo"] for e in eventos)),
        "todos_trusted": all(e["trusted"] for e in eventos) if eventos else None,
        "wheel_total": len(wheels),
        "wheel_arriba": len(arriba),
        "wheel_abajo": len(abajo),
        "wheel_dy_frecuentes": collections.Counter(abs(w["dy"]) for w in wheels).most_common(6),
        "wheel_intervalo_ms_mediana": statistics.median(ints) if ints else None,
        "wheel_intervalo_ms_p10_p90": (
            sorted(ints)[len(ints) // 10], sorted(ints)[(len(ints) * 9) // 10]
        ) if len(ints) >= 10 else None,
        "rafagas_n": len(rafagas),
        "rafaga_muescas_mediana": statistics.median(rafagas) if rafagas else None,
        "pausas_entre_rafagas_ms_mediana": (
            statistics.median([i for i in ints if i >= 250]) if any(i >= 250 for i in ints) else None
        ),
        "muescas_por_segundo": round(len(wheels) / dur, 1) if dur else None,
    }
