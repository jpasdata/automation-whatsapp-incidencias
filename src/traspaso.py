"""
Traspaso del trabajo adelantado de un PC a otro (y de vuelta), sin perder nada ni repetir descargas.

Exportar crea un .zip con: el índice (todo lo leído y qué se descargó), las evidencias descargadas, el estado del vigilante y el Excel de
incidencias. NO incluye la sesión de WhatsApp (en el otro PC se escanea el QR) ni la configuración.
Importar MEZCLA el contenido en el PC actual: agrega mensajes y estados que faltan, copia las evidencias sin pisar las que ya hay y
reapunta las rutas del índice a este PC. Se puede importar varias veces y en cualquier dirección.
Ojo: no correr el bot en los dos PCs a la vez (bajarían lo mismo dos veces).
"""
from __future__ import annotations

import json
import shutil
import socket
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .indice import Indice

EXT_COMPRIMIDAS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".webm", ".mkv", ".3gp", ".zip"}


def exportar(raiz: Path, salida: Path | None = None, con_excel: bool = True) -> Path:
    """Crea el .zip de traspaso. Devuelve su ruta."""
    destino = salida or raiz / "data" / "Traspasos" / f"Traspaso_{datetime.now():%Y%m%d_%H%M}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    ruta_indice = raiz / "data" / "indice" / "indice.sqlite3"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, zipfile.ZipFile(destino, "w", allowZip64=True) as z:
        if ruta_indice.exists():
            copia = Path(tmp) / "indice.sqlite3"
            origen, dest = sqlite3.connect(ruta_indice), sqlite3.connect(copia)
            origen.backup(dest)  # copia consistente aunque el bot esté escribiendo
            origen.close()
            dest.close()
            z.write(copia, "indice.sqlite3", compress_type=zipfile.ZIP_DEFLATED)
        ev = raiz / "data" / "Evidencias_WhatsApp"
        n_archivos = 0
        for f in sorted(ev.rglob("*")) if ev.exists() else []:
            if f.is_file() and f.name != ".gitkeep":
                tipo = zipfile.ZIP_STORED if f.suffix.lower() in EXT_COMPRIMIDAS else zipfile.ZIP_DEFLATED
                z.write(f, "Evidencias_WhatsApp/" + f.relative_to(ev).as_posix(), compress_type=tipo)
                n_archivos += 1
        estado = raiz / "logs" / "vigilante_estado.json"
        if estado.exists():
            z.write(estado, "vigilante_estado.json")
        excel = raiz / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx"
        if con_excel and excel.exists():
            z.write(excel, "RESULTADO_CREACION_INCIDENCIAS.xlsx", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("MANIFIESTO.json", json.dumps({
            "creado": datetime.now().isoformat(timespec="seconds"), "pc": socket.gethostname(), "archivos_de_evidencia": n_archivos,
            "incluye_excel": bool(con_excel and excel.exists()),
        }, ensure_ascii=False, indent=2))
    return destino


def importar(raiz: Path, zip_ruta: Path, con_excel: bool = False) -> dict:
    """Mezcla un .zip de traspaso en este PC. Devuelve un resumen de lo hecho."""
    resumen: dict = {}
    ev = raiz / "data" / "Evidencias_WhatsApp"
    ruta_indice = raiz / "data" / "indice" / "indice.sqlite3"
    ruta_indice.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, zipfile.ZipFile(zip_ruta) as z:
        nombres = z.namelist()
        if "MANIFIESTO.json" in nombres:
            resumen["origen"] = json.loads(z.read("MANIFIESTO.json").decode("utf-8"))
        # 1) evidencias: se copian sin pisar lo que ya existe
        copiados = omitidos = 0
        for n in nombres:
            if n.startswith("Evidencias_WhatsApp/") and not n.endswith("/"):
                dest = ev / n.split("/", 1)[1]
                if dest.exists():
                    omitidos += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                copiados += 1
        resumen["evidencias_copiadas"], resumen["evidencias_ya_existian"] = copiados, omitidos
        # 2) índice: respaldo del actual, mezcla y reapuntado de rutas
        if "indice.sqlite3" in nombres:
            if ruta_indice.exists():
                resp = ruta_indice.parent / "respaldo"
                resp.mkdir(exist_ok=True)
                shutil.copy2(ruta_indice, resp / f"indice_antes_de_importar_{datetime.now():%Y%m%d_%H%M}.sqlite3")
            z.extract("indice.sqlite3", tmp)
            with Indice(ruta_indice) as ix:
                resumen.update(ix.fusionar(Path(tmp) / "indice.sqlite3"))
                resumen["rutas_reapuntadas"] = ix.rebasar_rutas(ev)
        # 3) estado del vigilante (solo si aquí no hay) y Excel (solo si se pide)
        estado = raiz / "logs" / "vigilante_estado.json"
        if "vigilante_estado.json" in nombres and not estado.exists():
            estado.parent.mkdir(exist_ok=True)
            estado.write_bytes(z.read("vigilante_estado.json"))
        if con_excel and "RESULTADO_CREACION_INCIDENCIAS.xlsx" in nombres:
            destino = raiz / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx"
            if destino.exists():
                shutil.copy2(destino, destino.with_name(f"RESULTADO_CREACION_INCIDENCIAS_antes_{datetime.now():%Y%m%d_%H%M}.xlsx"))
            destino.write_bytes(z.read("RESULTADO_CREACION_INCIDENCIAS.xlsx"))
            resumen["excel_reemplazado"] = True
    return resumen
