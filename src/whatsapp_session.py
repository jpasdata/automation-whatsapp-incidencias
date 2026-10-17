"""
Apertura de WhatsApp Web con sesión persistente (Playwright).

Primera vez: abre el navegador visible, el usuario escanea el QR a mano.
Veces siguientes: reutiliza la sesión guardada en `carpeta_sesion` y
entra directo, sin pedir QR.

IMPORTANTE sobre selectores: WhatsApp Web cambia su HTML con cierta
frecuencia. Los selectores de abajo (atributos data-testid y aria-label,
que son los más estables que ofrece WhatsApp Web) están verificados al
momento de escribir esto, pero si en algún momento dejan de funcionar,
el primer sospechoso es un cambio de interfaz de WhatsApp, no un bug
del script. Se centralizan aquí, en un solo diccionario, para que
ajustarlos sea cambiar una línea y no buscar en 5 archivos.
"""
from __future__ import annotations

import logging

from playwright.sync_api import BrowserContext, Page, sync_playwright

SELECTORES = {
    "panel_chats": "#pane-side",  # verificado en vivo: aparece al iniciar sesión
    "caja_busqueda_chats": 'input[data-tab="3"]',  # ahora es un <input>, ya no un contenteditable
    "titulo_chat_abierto": 'header span[dir="auto"]',
    "panel_mensajes": 'div[data-testid="conversation-panel-messages"]',
    "burbuja_mensaje": 'div.message-in, div.message-out',
    "boton_menu_grupo": '#main header [role="button"][aria-label="Información del perfil"], #main header [title="Información del perfil"]',
    "lista_participantes": 'div[data-testid="group-info-drawer"] div[data-testid="cell-frame-container"]',
}

# Textos de botones de avisos/modales de WhatsApp Web ("Novedades...", etc.)
BOTONES_AVISO = ("Continuar", "Aceptar", "Entendido", "Listo", "Ahora no", "Continue", "Got it", "OK", "Not now")
BOTONES_CERRAR = ("Cerrar", "Close")

URL_WHATSAPP_WEB = "https://web.whatsapp.com"
TIMEOUT_LOGIN_MS = 120_000  # 2 minutos para escanear el QR la primera vez


class SesionWhatsApp:
    """
    Uso recomendado (context manager):

        with SesionWhatsApp(carpeta_sesion="./sesion_whatsapp", headless=False) as sesion:
            pagina = sesion.pagina
            ...

    Así el navegador se cierra bien incluso si algo lanza una excepción.
    """

    def __init__(self, carpeta_sesion: str, headless: bool = False, logger: logging.Logger | None = None):
        self.carpeta_sesion = carpeta_sesion
        self.headless = headless
        self.logger = logger or logging.getLogger("incidencias_wa")
        self._playwright = None
        self._contexto: BrowserContext | None = None
        self.pagina: Page | None = None

    def __enter__(self) -> "SesionWhatsApp":
        self.logger.info("Iniciando Playwright con sesión persistente en '%s'", self.carpeta_sesion)
        self._playwright = sync_playwright().start()
        self._contexto = self._playwright.chromium.launch_persistent_context(
            self.carpeta_sesion,
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.pagina = self._contexto.new_page()
        self.pagina.goto(URL_WHATSAPP_WEB)
        self._esperar_login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.logger.info("Cerrando sesión de Playwright.")
        if self._contexto:
            self._contexto.close()
        if self._playwright:
            self._playwright.stop()

    def _esperar_login(self) -> None:
        """
        Espera a que aparezca la lista de chats (señal de que ya se
        inició sesión, sea porque se reusó la sesión guardada o porque
        el usuario acaba de escanear el QR).
        """
        assert self.pagina is not None
        self.logger.info("Esperando que cargue WhatsApp Web (puede pedir escanear QR la primera vez)...")
        self.pagina.wait_for_selector(
            SELECTORES["panel_chats"],
            timeout=TIMEOUT_LOGIN_MS,
        )
        self.logger.info("Sesión de WhatsApp Web activa.")
        self.cerrar_avisos()

    def cerrar_avisos(self) -> int:
        """
        Cierra avisos/modales que WhatsApp Web superpone (p. ej. "Novedades
        en WhatsApp Web") y que bloquearían los clics siguientes. Pulsa el
        botón de aceptar o de cerrar si existe. NUNCA pulsa Escape: con un
        chat abierto, Escape cierra el chat (se comprobó en vivo). Un diálogo
        desconocido solo se registra en el log. Devuelve cuántos cerró.
        """
        assert self.pagina is not None
        cerrados = 0
        for _ in range(3):  # por si salen varios seguidos
            try:
                dialogo = self.pagina.locator('[role="dialog"]').first
                if dialogo.count() == 0 or not dialogo.is_visible():
                    break
                cerrado = False
                for texto in BOTONES_AVISO + BOTONES_CERRAR:
                    boton = dialogo.get_by_role("button", name=texto, exact=True)
                    if boton.count() > 0:
                        boton.first.click(timeout=3000)
                        cerrado = True
                        break
                if not cerrado:
                    resumen = (dialogo.inner_text(timeout=1000) or "").strip().replace("\n", " ")[:80]
                    self.logger.info("Diálogo sin botón conocido, se deja como está: %r", resumen)
                    break
                self.pagina.wait_for_timeout(500)
                cerrados += 1
                self.logger.info("Aviso de WhatsApp Web cerrado automáticamente.")
            except Exception as e:  # noqa: BLE001
                self.logger.debug("cerrar_avisos: %s", e)
                break
        return cerrados

    def abrir_chat(self, nombre_grupo: str) -> None:
        """
        Abre el chat cuyo título CONTIENE `nombre_grupo` (los títulos reales
        llevan emojis como ✅ que es incómodo copiar exactos). Si el texto
        coincide con más de un chat se usa el primero y se avisa en el log.
        """
        assert self.pagina is not None
        self.logger.info("Abriendo chat: %s", nombre_grupo)
        self.cerrar_avisos()

        caja = self.pagina.locator(SELECTORES["caja_busqueda_chats"]).first
        caja.click()
        self.pagina.keyboard.press("Control+A")
        self.pagina.keyboard.press("Delete")
        self.pagina.keyboard.type(nombre_grupo, delay=30)
        self.pagina.wait_for_timeout(1500)  # deja que WhatsApp filtre la lista

        coincidencias = self.pagina.locator(f'{SELECTORES["panel_chats"]} span[title]').filter(has_text=nombre_grupo)
        if coincidencias.count() == 0:
            raise RuntimeError(f"No se encontró ningún chat que contenga '{nombre_grupo}'.")
        if coincidencias.count() > 1:
            self.logger.warning("'%s' coincide con %d chats; se usa el primero.", nombre_grupo, coincidencias.count())
        coincidencias.first.click()

        self.pagina.wait_for_selector(SELECTORES["panel_mensajes"], timeout=15_000)
        self.cerrar_avisos()
        self.logger.info("Chat '%s' abierto.", nombre_grupo)
