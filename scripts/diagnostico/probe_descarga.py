import sys, time, json, base64
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from src.nucleo.config import load_config
from src.whatsapp.session import SesionWhatsApp
from src.nucleo.logger import setup_logger

cfg = load_config()
log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
OUT = RAIZ / "logs" / "probe_descarga"
OUT.mkdir(parents=True, exist_ok=True)

JS_THUMBS = """() => [...document.querySelectorAll('[data-testid="conversation-panel-messages"] [data-testid="image-thumb"]')].map((e, i) => {
  const img = e.querySelector('img'); const r = e.getBoundingClientRect();
  return {i, y: Math.round(r.y), h: Math.round(r.height), src: img ? (img.src || '').slice(0, 60) : null, vis: r.height > 0 && r.y > 0 && r.y < innerHeight};
})"""
JS_VISOR = """() => {
  const out = {};
  out.imgs = [...document.querySelectorAll('img')].filter(i => i.naturalWidth > 400).map(i => ({src: (i.src||'').slice(0, 80), w: i.naturalWidth, h: i.naturalHeight}));
  out.btns = [...document.querySelectorAll('button,[role=button],[aria-label],[data-testid]')].filter(e => /(download|descarg|close|cerrar|next|prev|sigu|anter)/i.test((e.getAttribute('aria-label')||'') + (e.getAttribute('data-testid')||'') + (e.getAttribute('data-icon')||''))).map(e => ({tag: e.tagName, aria: e.getAttribute('aria-label'), tid: e.getAttribute('data-testid'), icon: e.getAttribute('data-icon')})).slice(0, 20);
  return out;
}"""
JS_FETCH = """async (src) => { const r = await fetch(src); const b = await r.blob(); const buf = await b.arrayBuffer();
  let s = ''; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return {tipo: b.type, n: u.length, b64: btoa(s)}; }"""

with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0])
    p = s.pagina
    p.wait_for_timeout(4000)
    th = p.evaluate(JS_THUMBS)
    print("THUMBS", len(th), [t for t in th if t["vis"]][:5], flush=True)
    vis = [t for t in th if t["vis"]]
    if not vis:
        print("sin miniaturas visibles"); sys.exit()
    t0 = time.time()
    p.locator('[data-testid="conversation-panel-messages"] [data-testid="image-thumb"]').nth(vis[-1]["i"]).click()
    p.wait_for_timeout(1500)
    v = p.evaluate(JS_VISOR)
    print("VISOR", json.dumps(v, ensure_ascii=False), flush=True)
    p.screenshot(path=str(OUT / "visor.png"))
    grandes = v["imgs"]
    if grandes:
        src = p.evaluate("""() => [...document.querySelectorAll('img')].filter(i => i.naturalWidth > 400).map(i => i.src)[0]""")
        r = p.evaluate(JS_FETCH, src)
        (OUT / "foto1.jpg").write_bytes(base64.b64decode(r["b64"]))
        print("FETCH", r["tipo"], r["n"], "bytes en", round(time.time() - t0, 1), "s", flush=True)
    p.keyboard.press("Escape")
    p.wait_for_timeout(800)
    print("tras Escape, burbujas:", p.evaluate("() => document.querySelectorAll('[data-testid^=\"conv-msg-\"]').length"))
