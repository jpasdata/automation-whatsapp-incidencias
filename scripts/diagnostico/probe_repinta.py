import sys, time
from pathlib import Path
RAIZ = Path(sys.argv[1]); sys.path.insert(0, str(RAIZ))
from src.nucleo.config import load_config
from src.whatsapp.session import SesionWhatsApp
from src.nucleo.logger import setup_logger
from src.whatsapp import reader as R
from src.bot.descargas import _JS_IDS_PINTADOS
cfg = load_config(); log = setup_logger(cfg.logging.carpeta_logs, "WARNING")
with SesionWhatsApp(cfg.whatsapp.carpeta_sesion, headless=False, logger=log) as s:
    s.abrir_chat(cfg.whatsapp.grupos[0]); p = s.pagina; p.wait_for_timeout(4000)
    st = R.cargar_hacia_arriba(p, max_seg=150, rueda_real=True)
    print("subida:", st, flush=True)
    p.evaluate(R._JS_IR_ARRIBA); p.wait_for_timeout(1500)
    vistos = []; setv = set(); primero = None
    for paso in range(400):
        ids = p.evaluate(_JS_IDS_PINTADOS)
        for i in ids:
            if i not in setv: setv.add(i); vistos.append(i)
        if primero is None: primero = list(ids)
        if p.evaluate(R._JS_BAJAR_TRAMO): break
        p.wait_for_timeout(350)
    print("pasos:", paso + 1, "| ids distintos pintados al bajar:", len(vistos), "| pintados al inicio:", len(primero or []), flush=True)
    print("¿siguen pintados los del inicio al final?", len(set(primero or []) & set(p.evaluate(_JS_IDS_PINTADOS))), flush=True)
