"""
Registros CSV de lo que hace el bot (uno por hecho), para filtrar en Excel y ubicar fallas:
  logs/descargas_detalle.csv : una fila por mensaje con adjunto que se intentó bajar (resultado, motivo, tiempos).
  logs/eventos_bot.csv       : hitos de la corrida (abrir chat, tandas, cruces, errores).
Se escriben al instante (append) para que no se pierda nada si el proceso se cierra.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path

CARPETA = Path(__file__).resolve().parent.parent / "logs"
_lock = threading.Lock()


def configurar(carpeta_logs: str | Path) -> None:
    global CARPETA
    CARPETA = Path(carpeta_logs)
    CARPETA.mkdir(parents=True, exist_ok=True)


def registrar_csv(nombre: str, fila: dict) -> None:
    """Agrega una fila a logs/<nombre>; escribe el encabezado si el archivo es nuevo. Nunca lanza error."""
    try:
        ruta = CARPETA / nombre
        fila = {"ts": datetime.now().isoformat(timespec="seconds"), **fila}
        with _lock:
            nuevo = not ruta.exists() or ruta.stat().st_size == 0
            if not nuevo:
                with open(ruta, newline="", encoding="utf-8-sig") as f:
                    encabezado = next(csv.reader(f), [])
                if encabezado != list(fila):  # cambió el formato: se archiva el viejo para no mezclar columnas
                    ruta.rename(ruta.with_name(f"{ruta.stem}_{datetime.now():%Y%m%d_%H%M%S}{ruta.suffix}"))
                    nuevo = True
            with open(ruta, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(fila), extrasaction="ignore")
                if nuevo:
                    w.writeheader()
                w.writerow(fila)
    except Exception:  # noqa: BLE001 - registrar no debe tumbar al bot
        pass


def evento(grupo: str, fase: str, accion: str, resultado: str = "ok", detalle: str = "") -> None:
    registrar_csv("eventos_bot.csv", {"grupo": grupo, "fase": fase, "accion": accion, "resultado": resultado, "detalle": detalle})
