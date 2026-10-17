import sys, time, json
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from src.nucleo.config import load_config
from src.whatsapp.session import SesionWhatsApp
from src.nucleo.logger import setup_logger
from src.whatsapp.reader import _JS_IR_ARRIBA, _JS_BAJAR_TRAMO, _JS_VISOR_PRINCIPAL, _BOTON_SIGUIENTE

cfg = load_config()
log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
OUT = RAIZ / "logs" / "probe_descarga"

JS_ALBUM = """() => { for (const el of document.querySelectorAll('[data-testid^="conv-msg-"]')) {
  if (!el.querySelector('[data-virtualized="true"]') && el.querySelector('[data-testid="media-album"]')) return el.dataset.id; } return null; }"""
JS_ESTADO = """() => {
  const cands = [...document.querySelectorAll('img,video,canvas')].map(e => ({e, r: e.getBoundingClientRect()})).filter(c => c.r.width * c.r.height > 60000);
  cands.sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height);
  const c = cands[0]; if (!c) return null;
  const cerca = [...document.querySelectorAll('[data-testid],[aria-label],[role=progressbar],svg')].filter(x => {
    const r = x.getBoundingClientRect(); return r.width > 0 && r.top > 60 && r.top < innerHeight - 100 && !/^(BUTTON)$/.test(x.tagName); })
    .map(x => (x.getAttribute('data-testid') || '') + '|' + (x.getAttribute('aria-label') || '') + '|' + x.tagName).slice(0, 30);
  return {tag: c.e.tagName, nw: c.e.naturalWidth, nh: c.e.naturalHeight, w: Math.round(c.r.width), h: Math.round(c.r.height), cerca};
}"""

with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0])
    p = s.pagina
    p.wait_for_timeout(4000)
    p.evaluate(_JS_IR_ARRIBA); p.wait_for_timeout(800)
    id_ = None
    for _ in range(60):
        id_ = p.evaluate(JS_ALBUM)
        if id_ or p.evaluate(_JS_BAJAR_TRAMO):
            break
        p.wait_for_timeout(400)
    print("album", id_, flush=True)
    b = p.locator(f'[data-id="{id_}"]')
    b.first.scroll_into_view_if_needed()
    b.locator('[data-testid="image-thumb"]').first.click()
    p.wait_for_timeout(2000)
    for n in range(1, 9):
        st = p.evaluate(JS_ESTADO)
        print(n, json.dumps(st, ensure_ascii=False)[:600], flush=True)
        if n in (5, 6):
            p.screenshot(path=str(OUT / f"borroso_{n}.png"))
            p.wait_for_timeout(8000)
            print("  tras 8 s:", json.dumps(p.evaluate(JS_ESTADO), ensure_ascii=False)[:300], flush=True)
            p.screenshot(path=str(OUT / f"borroso_{n}_despues.png"))
        p.locator(_BOTON_SIGUIENTE).first.click()
        p.wait_for_timeout(1500)
    p.locator('button[aria-label="Cerrar"]').first.click()
