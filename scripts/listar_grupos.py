#!/usr/bin/env python3
"""
Abre WhatsApp Web (sesión persistente), espera el login (QR la primera vez),
lista los nombres de chats/grupos visibles y los guarda en logs/chats_visibles.txt.
Solo lee: no abre chats, no descarga, no envía nada.

Uso:
    python scripts/listar_grupos.py [segundos_abierto]
"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.whatsapp_session import SELECTORES, TIMEOUT_LOGIN_MS, URL_WHATSAPP_WEB  # noqa: E402

segundos_abierto = int(sys.argv[1]) if len(sys.argv) > 1 else 600
salida = RAIZ / "logs" / "chats_visibles.txt"
salida.parent.mkdir(exist_ok=True)

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        str(RAIZ / "sesion_whatsapp"), headless=False, args=["--disable-blink-features=AutomationControlled"]
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL_WHATSAPP_WEB)
    print("Esperando login (escanea el QR si aparece)...", flush=True)
    try:
        page.wait_for_selector("#pane-side", timeout=TIMEOUT_LOGIN_MS)
    except Exception as e:  # noqa: BLE001
        print(f"No se detectó el panel de chats (#pane-side) ({e}). Puede ser el selector o que no se escaneó el QR.", flush=True)
    else:
        page.wait_for_timeout(4000)  # deja cargar la lista
        nombres = page.eval_on_selector_all(
            '#pane-side [role="row"] span[title], #pane-side [role="listitem"] span[title]',
            "els => [...new Set(els.map(e => e.getAttribute('title')))]",
        )
        salida.write_text("\n".join(nombres), encoding="utf-8")
        print(f"{len(nombres)} chats visibles guardados en {salida}", flush=True)
    print(f"Ventana abierta {segundos_abierto}s; ciérrala cuando quieras.", flush=True)
    t0 = time.time()
    while time.time() - t0 < segundos_abierto and ctx.pages:
        time.sleep(1)
    try:
        ctx.close()
    except Exception:  # noqa: BLE001
        pass
