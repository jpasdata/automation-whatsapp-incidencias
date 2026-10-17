"""
Estructuras de datos compartidas entre el lector de WhatsApp, el
matcher y el manejador de Excel.

Mantener estas clases separadas de Playwright es lo que permite
probar toda la lógica de "a qué incidencia pertenece esta foto" con
pytest, sin necesitar un navegador ni una sesión real de WhatsApp.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


def normalizar_texto(valor) -> str | None:
    """Sin tildes, en mayúsculas y sin espacios sobrantes: "Panamá Oeste " -> "PANAMA OESTE". None/vacío -> None."""
    if valor is None:
        return None
    t = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode().upper().strip()
    return t or None


class TipoOrigenMatch(str, Enum):
    MISMO_MENSAJE = "mismo_mensaje"          # el código venía en el pie de foto
    MENSAJE_CERCANO = "mensaje_cercano"       # el código estaba en un texto separado del mismo remitente
    RESPUESTA = "respuesta"                   # un texto con el código CITÓ (respondió a) el paquete multimedia
    MENSAJE_POSTERIOR = "mensaje_posterior"   # mandó las fotos y escribió el código DESPUÉS (sin citar)
    RAFAGA = "rafaga"                         # foto suelta sin número, pegada (<= 2 min) a otra del mismo remitente que sí lo trae
    SIN_CODIGO = "sin_codigo"                 # no se encontró ningún código


class CriterioBusqueda(str, Enum):
    """
    Con qué identificador se encontró (o no) la fila del Excel, siguiendo
    la cascada que Henry usa a mano: código -> elemento -> aviso -> nada.
    """
    CODIGO = "codigo"
    NUMERO_ELEMENTO = "numero_elemento"
    NUMERO_AVISO = "numero_aviso"
    NO_ENCONTRADO = "no_encontrado"


@dataclass
class Mensaje:
    """Un mensaje del grupo, ya normalizado (sin detalles de Playwright)."""
    remitente: str
    timestamp: datetime
    texto: str | None = None
    tiene_adjunto: bool = False
    tipo_adjunto: str | None = None   # "imagen" | "video" | None
    id_mensaje: str | None = None     # identificador interno de WhatsApp Web, si está disponible
    n_adjuntos: int = 0               # cuántas fotos/videos trae la burbuja (un álbum trae varios)
    cita_autor: str | None = None     # si es una respuesta: autor del mensaje citado
    cita_texto: str | None = None     # ...y el resumen de lo citado ("6 fotos", "video", texto)


@dataclass
class ResultadoMatch:
    """El resultado de asociar un mensaje con adjunto a un código de incidencia."""
    mensaje: Mensaje
    codigo: str | None
    origen: TipoOrigenMatch
    ruta_local: Path | None = None
    candidatos: list[str] = field(default_factory=list)  # TODOS los números del texto (incidencia, elemento, aviso...)
