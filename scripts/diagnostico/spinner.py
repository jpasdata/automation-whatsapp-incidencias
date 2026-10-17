import sys, time, json
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from src.config import load_config
from src.whatsapp_session import SesionWhatsApp
from src.logger import setup_logger
from src import whatsapp_reader as R
from src.rueda import PresionContinua

cfg = load_config()
log = setup_logger(cfg.logging.carpeta_logs, "WARNING")

# Todo lo que NO es mensaje dentro del panel y parece un indicador de carga / aviso
JS = """() => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return null;
  const out = [];
  const rx = /(spin|load|progress|refresh|sync|loader|circle)/i;
  for (const el of panel.querySelectorAll('*')) {
    if (el.closest('[data-testid^="conv-msg-"]')) continue;
    const tid = el.getAttribute('data-testid') || '', role = el.getAttribute('role') || '', aria = el.getAttribute('aria-label') || '',
          icon = el.getAttribute('data-icon') || '', cls = (el.getAttribute('class') || '').toString();
    const txt = (el.children.length === 0 ? (el.textContent || '').trim() : '');
    const esSvgCirculo = el.tagName === 'circle' || (el.tagName === 'svg' && el.querySelector('circle'));
    if (rx.test(tid) || rx.test(role) || rx.test(aria) || rx.test(icon) || role === 'progressbar' || esSvgCirculo
        || /(sincroniz|cargando|loading|mensajes anteriores|older)/i.test(txt)) {
      const r = el.getBoundingClientRect();
      out.push({tag: el.tagName, tid, role, aria, icon, txt: txt.slice(0, 80), y: Math.round(r.y), h: Math.round(r.height), vis: r.height > 0});
    }
  }
  return out;
}"""

muestras = []
with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0])
    p = s.pagina
    p.wait_for_timeout(3000)
    pres = PresionContinua(p, True)
    R._calentar(pres, 2)
    t0 = time.time()
    previo = None
    while time.time() - t0 < 95:
        R._subir_rapido_al_tope(p)
        t1 = time.time()
        while time.time() - t1 < 14 and time.time() - t0 < 95:
            pres.rafaga_humana()
            n = p.evaluate(R._JS_CONTAR_BURBUJAS)
            cand = p.evaluate(JS)
            firma = json.dumps([(c["tag"], c["tid"], c["role"], c["icon"], c["txt"][:30]) for c in cand or []], ensure_ascii=False)
            muestras.append({"t": round(time.time() - t0, 1), "burbujas": n, "n_cand": len(cand or []), "firma": firma})
    # resumen: firmas distintas y cuándo aparecen respecto de cambios de burbujas
    firmas = {}
    for m in muestras:
        firmas.setdefault(m["firma"], []).append(m["t"])
    print("MUESTRAS:", len(muestras), flush=True)
    for f, ts in sorted(firmas.items(), key=lambda kv: -len(kv[1])):
        print(f"FIRMA x{len(ts)} (t={ts[0]}..{ts[-1]}): {f[:400]}", flush=True)
    cambios = [(a["t"], a["burbujas"], b["burbujas"]) for a, b in zip(muestras, muestras[1:]) if b["burbujas"] != a["burbujas"]]
    print("CAMBIOS_BURBUJAS:", cambios, flush=True)
    (RAIZ / "logs" / "spinner.json").write_text(json.dumps(muestras, ensure_ascii=False), encoding="utf-8")
