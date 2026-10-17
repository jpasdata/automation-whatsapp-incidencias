import sys, time
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from playwright.sync_api import sync_playwright
from src.nucleo.config import load_config

cfg = load_config()
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(str(RAIZ / cfg.whatsapp.carpeta_sesion), headless=False, viewport=None)
    p = ctx.pages[0] if ctx.pages else ctx.new_page()
    p.goto("https://web.whatsapp.com")
    for i in range(12):
        p.wait_for_timeout(5000)
        estado = p.evaluate("""() => ({
          lista: !!document.querySelector('#pane-side'),
          qr: !!document.querySelector('canvas'),
          texto: (document.body.innerText || '').slice(0, 200).replace(/\\s+/g, ' ')})""")
        print(i * 5 + 5, "s", estado, flush=True)
        if estado["lista"]:
            break
    p.screenshot(path=str(RAIZ / "logs" / "pantalla.png"))
    print("captura guardada", flush=True)
    p.wait_for_timeout(20000)
    ctx.close()
