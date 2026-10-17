import sys, time
from pathlib import Path
RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ))
from src.config import load_config
from src.whatsapp_session import SesionWhatsApp
from src.logger import setup_logger
from src.whatsapp_reader import descargar_adjunto, _JS_IR_ARRIBA, _JS_BAJAR_TRAMO

cfg = load_config()
log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
OUT = RAIZ / "logs" / "probe_descarga"
OUT.mkdir(parents=True, exist_ok=True)

JS_BUSCAR = """() => {
  const out = {video: null, album: null};
  for (const el of document.querySelectorAll('[data-testid^="conv-msg-"]')) {
    if (el.querySelector('[data-virtualized="true"]')) continue;
    const thumbs = el.querySelectorAll('[data-testid="image-thumb"]').length;
    const vids = el.querySelectorAll('[data-testid="video-content"]').length;
    const album = !!el.querySelector('[data-testid="media-album"]');
    if (vids && !out.video) out.video = {id: el.dataset.id, vids, thumbs, album};
    if ((album || thumbs > 1) && !out.album) out.album = {id: el.dataset.id, vids, thumbs, album, texto: el.innerText.slice(0, 60)};
  }
  return out;
}"""

with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0])
    p = s.pagina
    p.wait_for_timeout(4000)
    encontrado = {"video": None, "album": None}
    # recorre lo pintado de arriba abajo buscando un video y un álbum
    p.evaluate(_JS_IR_ARRIBA); p.wait_for_timeout(800)
    for paso in range(60):
        r = p.evaluate(JS_BUSCAR)
        for k in encontrado:
            if r[k] and not encontrado[k]:
                encontrado[k] = r[k]
        if all(encontrado.values()):
            break
        if p.evaluate(_JS_BAJAR_TRAMO):
            break
        p.wait_for_timeout(400)
    print("ENCONTRADO", encontrado, flush=True)
    for k in ("video",):
        e = encontrado[k]
        if not e:
            print(k, "-> no hay en lo pintado"); continue
        bub = p.locator(f'[data-id="{e["id"]}"]')
        mini = bub.locator('[data-testid="video-content"]') if k == 'video' else bub.locator('[data-testid="image-thumb"], [data-testid="video-content"]')
        bub.first.scroll_into_view_if_needed()
        t0 = time.time()
        rutas = descargar_adjunto(p, mini.first, OUT / k, f"prueba_{k}", todo_el_album=(k == "album"))
        print(k.upper(), len(rutas), "archivo(s) en", round(time.time() - t0, 1), "s:",
              [(r.name, r.stat().st_size) for r in rutas], flush=True)
    print("burbujas tras cerrar visor:", p.evaluate("() => document.querySelectorAll('[data-testid^=\"conv-msg-\"]').length"))
