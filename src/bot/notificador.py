"""
FUERA DE ALCANCE EN EL FLUJO ACTUAL -- este módulo no se importa desde
main.py ni desde ningún script.

Henry (quien revisa lo que llega) confirmó que el aviso de "falta
evidencia" lo maneja él por CORREO, no por WhatsApp. Por lo tanto esta
automatización no necesita mandar nada por WhatsApp: su alcance es
descargar/clasificar las evidencias y dejar el Excel actualizado para
que Henry decida a quién pedírsela, por el canal que ya usa.

Este archivo queda en el proyecto solo como una idea para una fase
futura -- si algún día se decide automatizar también el aviso, lo más
fiel a como se trabaja hoy sería una integración de CORREO (smtplib /
Gmail API / Outlook), no de WhatsApp. El código de abajo (envío por
WhatsApp vía wa.me) se deja escrito por si cambia de opinión, pero no
se ejecuta ni se prueba activamente mientras el alcance sea "solo
WhatsApp" para descarga/clasificación.
"""
from __future__ import annotations

import logging

from playwright.sync_api import Page

from src.whatsapp.session import SELECTORES

logger = logging.getLogger("incidencias_wa")


class NotificacionesBloqueadasError(Exception):
    """Se intentó notificar sin que notificaciones.activas esté en true."""


class Notificador:
    def __init__(self, pagina: Page, activas: bool, mapeo_nombre_telefono: dict[str, str], plantilla_mensaje: str):
        self.pagina = pagina
        self.activas = activas
        self.mapeo_nombre_telefono = mapeo_nombre_telefono
        self.plantilla_mensaje = plantilla_mensaje

    def enviar_recordatorio(self, nombre: str, codigo: str) -> bool:
        if not self.activas:
            logger.info(
                "[SIMULADO] No se envía nada (notificaciones.activas=false). "
                "Mensaje que se habría enviado a %s sobre %s: %s",
                nombre, codigo, self._armar_mensaje(nombre, codigo),
            )
            return False

        telefono = self.mapeo_nombre_telefono.get(nombre)
        if not telefono:
            logger.warning(
                "No hay teléfono mapeado para '%s' en config.yaml -> notificaciones.mapeo_nombre_telefono. "
                "No se envía el recordatorio de la incidencia %s.",
                nombre, codigo,
            )
            return False

        mensaje = self._armar_mensaje(nombre, codigo)
        return self._enviar_por_numero(telefono, mensaje)

    def _armar_mensaje(self, nombre: str, codigo: str) -> str:
        return self.plantilla_mensaje.format(nombre=nombre, codigo=codigo)

    def _enviar_por_numero(self, telefono: str, mensaje: str) -> bool:
        """Usa el enlace wa.me para abrir el chat directo y envía el mensaje."""
        telefono_limpio = "".join(c for c in telefono if c.isdigit())
        url = f"https://web.whatsapp.com/send?phone={telefono_limpio}&text={mensaje}"
        try:
            self.pagina.goto(url)
            caja_texto = self.pagina.locator(SELECTORES["caja_busqueda_chats"].replace('data-tab="3"', 'data-tab="10"'))
            caja_texto.wait_for(timeout=15_000)
            self.pagina.keyboard.press("Enter")
            logger.info("Recordatorio enviado a %s.", telefono_limpio)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Falló el envío a %s: %s", telefono_limpio, e)
            return False
