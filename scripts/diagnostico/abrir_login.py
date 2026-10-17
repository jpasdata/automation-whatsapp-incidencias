import sys, time
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from playwright.sync_api import sync_playwright
from src.config import load_config

cfg = load_config()
with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(str(RAIZ / cfg.whatsapp.carpeta_sesion), headless=False, viewport=None)
    p = ctx.pages[0] if ctx.pages else ctx.new_page()
    p.goto("https://web.whatsapp.com")
    t0 = time.time()
    visto = None
    try:
        while time.time() - t0 < 900:
            p.wait_for_timeout(3000)
            estado = p.evaluate("() => ({lista: !!document.querySelector('#pane-side'), qr: !!document.querySelector('canvas')})")
            print(round(time.time() - t0), estado, flush=True)
            if estado["lista"]:
                visto = visto or time.time()
                if time.time() - visto > 60:  # dar tiempo a que la sesión se guarde bien
                    break
    except Exception as e:
        print("ventana cerrada:", str(e)[:80], flush=True)
    else:
        print("sesion lista y guardada; cerrando", flush=True)
        ctx.close()
