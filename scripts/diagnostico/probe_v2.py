import sys, json
from pathlib import Path
RAIZ = Path(sys.argv[1]); sys.path.insert(0, str(RAIZ))
from src.nucleo.config import load_config
from src.whatsapp.session import SesionWhatsApp
from src.nucleo.logger import setup_logger
from src.whatsapp.reader import _JS_IR_ARRIBA, _JS_BAJAR_TRAMO
cfg = load_config(); log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
OUT = RAIZ / "logs" / "probe_descarga"
JS_V = """() => { for (const el of document.querySelectorAll('[data-testid^="conv-msg-"]')) {
  if (!el.querySelector('[data-virtualized="true"]') && el.querySelector('[data-testid="video-content"]')) return el.dataset.id; } return null; }"""
JS_ST = """() => ({
  videos: [...document.querySelectorAll('video')].map(v => ({src: (v.currentSrc||v.src||'').slice(0,40), rs: v.readyState, w: v.videoWidth, dur: v.duration, paused: v.paused, rect: (r => [Math.round(r.width), Math.round(r.height)])(v.getBoundingClientRect())})),
  tids: [...document.querySelectorAll('[data-testid^="media"],[data-testid*="video"],[data-testid*="play"],[data-testid*="spinner"]')].map(x => x.getAttribute('data-testid')).slice(0, 25),
  btns: [...document.querySelectorAll('button[aria-label]')].map(b => b.getAttribute('aria-label')).slice(0, 20)})"""
with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0]); p = s.pagina; p.wait_for_timeout(4000)
    p.evaluate(_JS_IR_ARRIBA); p.wait_for_timeout(800)
    id_ = None
    for _ in range(60):
        id_ = p.evaluate(JS_V)
        if id_ or p.evaluate(_JS_BAJAR_TRAMO): break
        p.wait_for_timeout(400)
    print("bubble", id_, flush=True)
    b = p.locator(f'[data-id="{id_}"]'); b.first.scroll_into_view_if_needed()
    print("tids burbuja:", p.evaluate("(id) => [...document.querySelector('[data-id=\"'+id+'\"]').querySelectorAll('[data-testid]')].map(e=>e.getAttribute('data-testid')).slice(0,30)", id_), flush=True)
    b.locator('[data-testid="video-content"]').first.click()
    for t in (1, 3, 6, 10):
        p.wait_for_timeout(t * 1000 if t == 1 else 2500)
        print(t, json.dumps(p.evaluate(JS_ST), ensure_ascii=False), flush=True)
        p.screenshot(path=str(OUT / f"video_{t}.png"))
    p.locator('button[aria-label="Cerrar"]').first.click()
