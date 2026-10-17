import sys, time, sqlite3
from pathlib import Path
RAIZ = Path(sys.argv[1]); sys.path.insert(0, str(RAIZ))
from src.config import load_config
from src.whatsapp_session import SesionWhatsApp
from src.logger import setup_logger
from src import whatsapp_reader as R
from src.descargas import _JS_IDS_PINTADOS
cfg = load_config(); log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
c = sqlite3.connect(RAIZ / "data/indice/indice.sqlite3")
idx = {r[0]: r[1] for r in c.execute("select id, ts from mensajes where ts>='2026-10-14'")}
JS_PASO = """(f) => { const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
 const cands=[panel,...panel.querySelectorAll('div')]; const el=cands.filter(e=>e.scrollHeight>e.clientHeight+20&&/(auto|scroll)/.test(getComputedStyle(e).overflowY)).sort((a,b)=>b.clientHeight-a.clientHeight)[0];
 const antes=el.scrollTop; el.scrollTop += el.clientHeight*f; return {top: el.scrollTop, sh: el.scrollHeight, ch: el.clientHeight, movio: el.scrollTop>antes}; }"""
with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0]); p = s.pagina; p.wait_for_timeout(4000)
    st = R.cargar_hacia_arriba(p, max_seg=120, rueda_real=True)
    print("subida:", st, flush=True)
    p.evaluate(R._JS_IR_ARRIBA); p.wait_for_timeout(1500)
    setv = set(); n = 0; ult = None
    while n < 600:
        n += 1
        for i in p.evaluate(_JS_IDS_PINTADOS): setv.add(i)
        r = p.evaluate(JS_PASO, 0.4); ult = r
        if n % 40 == 0: print("paso", n, r, "distintos", len(setv), flush=True)
        if not r["movio"]: break
        p.wait_for_timeout(500)
    print("FIN pasos", n, ult, "distintos", len(setv), flush=True)
    vis = [i for i in setv if i in idx]
    print("pintados que están en el índice (>=14/10):", len(vis), "de", len(idx), "del índice; fracción vista:", round(len(vis)/len(idx), 2), flush=True)
    if vis:
        ts = sorted(idx[i] for i in vis); print("rango visto:", ts[0], ts[-1], flush=True)
