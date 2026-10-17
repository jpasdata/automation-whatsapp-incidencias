"""
Estado de las descargas: qué se bajó y qué no, para saberlo de un vistazo.

Fuentes: la carpeta de evidencias (lo que de verdad está en disco), logs/descargas_detalle.csv (cada intento, con su
motivo de fallo) y logs/descargas_pendientes.csv (lo que cruza con una incidencia y aún no se baja).
"""
from __future__ import annotations

import csv
from collections import defaultdict

from src.nucleo import eventos
from src.nucleo.rutas import R
from pathlib import Path

EXT_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".3gp"}


def _leer_csv(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def resumen(raiz_evidencias: Path | None = None, carpeta_logs: Path | None = None) -> str:
    raiz_evidencias = raiz_evidencias or R.evidencias
    carpeta_logs = carpeta_logs or R.logs
    por_dia: dict[tuple[str, str], dict] = defaultdict(lambda: {"fotos": 0, "videos": 0, "bytes": 0, "incid": set()})
    if raiz_evidencias.exists():
        for f in raiz_evidencias.rglob("*"):
            if f.is_file() and f.name != ".gitkeep" and len(f.relative_to(raiz_evidencias).parts) >= 3:
                grupo, dia = f.relative_to(raiz_evidencias).parts[:2]
                d = por_dia[(grupo, dia)]
                d["videos" if f.suffix.lower() in EXT_VIDEO else "fotos"] += 1
                d["bytes"] += f.stat().st_size
                d["incid"].add(f.parent.name)

    # último resultado por mensaje (un mensaje puede reintentarse)
    ultimo: dict[str, dict] = {}
    for fila in eventos.leer_todos("descargas_detalle.csv", carpeta_logs):   # todas las corridas; la última fila de cada mensaje manda
        ultimo[fila.get("id_mensaje", "")] = fila
    errores = [f for f in ultimo.values() if f.get("resultado") in ("error", "parcial")]
    carpeta_p = eventos.ultima_corrida(carpeta_logs, "descargas_pendientes.csv")
    pendientes = _leer_csv(carpeta_p / "descargas_pendientes.csv") if carpeta_p else []

    lineas = ["=== ESTADO DE DESCARGAS ===", "", "En disco (lo realmente descargado):",
              f"{'Grupo':36} {'Día':10} {'Fotos':>6} {'Videos':>6} {'MB':>8}  Incidencias"]
    if not por_dia:
        lineas.append("  (todavía no hay archivos descargados)")
    for (grupo, dia), d in sorted(por_dia.items()):
        lineas.append(f"{grupo[:36]:36} {dia:10} {d['fotos']:6d} {d['videos']:6d} {d['bytes'] / 1e6:8.1f}  {len(d['incid'])}")
    tot_f = sum(d["fotos"] for d in por_dia.values())
    tot_v = sum(d["videos"] for d in por_dia.values())
    lineas += ["", f"TOTAL: {tot_f} fotos, {tot_v} videos.",
               f"Intentos registrados: {len(ultimo)} mensajes (ok: {sum(f.get('resultado') == 'ok' for f in ultimo.values())}, "
               f"parcial: {sum(f.get('resultado') == 'parcial' for f in ultimo.values())}, "
               f"error: {sum(f.get('resultado') == 'error' for f in ultimo.values())})."]
    if errores:
        lineas += ["", "FALLAS (último intento por mensaje):"]
        for f in errores[:40]:
            lineas.append(f"  {f.get('dia') or '-'} {f.get('hora') or ''} {f.get('remitente', '')[:18]:18} fila {f.get('fila')}: "
                          f"{f.get('resultado')} - {f.get('error', '')[:110]}")
        if len(errores) > 40:
            lineas.append(f"  ... y {len(errores) - 40} más en logs/descargas_detalle.csv")
    lineas += ["", f"PENDIENTES (cruzan con una incidencia y aún no se bajan): {len(pendientes)}"]
    for f in pendientes[:25]:
        lineas.append(f"  {f.get('dia') or '-'} {f.get('hora') or ''} {f.get('remitente', '')[:18]:18} fila {f.get('fila')} {f.get('codigo')}")
    if len(pendientes) > 25:
        lineas.append(f"  ... y {len(pendientes) - 25} más en logs/descargas_pendientes.csv")
    return "\n".join(lineas)
