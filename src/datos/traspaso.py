"""
Traspaso del trabajo adelantado de un PC a otro (y de vuelta), sin perder nada ni repetir descargas.

Exportar crea un .zip con: el índice (todo lo leído y qué se descargó), las evidencias descargadas, el estado del vigilante y la carpeta de
incidencias (la base y lo que esté pendiente en `nuevas/`). NO incluye la sesión de WhatsApp (en el otro PC se escanea el QR) ni la configuración.
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

from src.datos.indice import Indice
from src.nucleo.rutas import Rutas

EXT_COMPRIMIDAS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".webm", ".mkv", ".3gp", ".zip"}
PREFIJO_EVIDENCIAS, PREFIJO_INCIDENCIAS = "Evidencias_WhatsApp/", "Incidencias/"


def exportar(raiz: Path, salida: Path | None = None, con_excel: bool = True) -> Path:
    """Crea el .zip de traspaso. Devuelve su ruta."""
    r = Rutas(raiz)
    destino = salida or r.traspasos / f"Traspaso_{datetime.now():%Y%m%d_%H%M}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, zipfile.ZipFile(destino, "w", allowZip64=True) as z:
        if r.indice_db.exists():
            copia = Path(tmp) / "indice.sqlite3"
            origen, dest = sqlite3.connect(r.indice_db), sqlite3.connect(copia)
            origen.backup(dest)  # copia consistente aunque el bot esté escribiendo
            origen.close()
            dest.close()
            z.write(copia, "indice.sqlite3", compress_type=zipfile.ZIP_DEFLATED)
        n_archivos = 0
        for f in sorted(r.evidencias.rglob("*")) if r.evidencias.exists() else []:
            if f.is_file() and f.name != ".gitkeep":
                tipo = zipfile.ZIP_STORED if f.suffix.lower() in EXT_COMPRIMIDAS else zipfile.ZIP_DEFLATED
                z.write(f, PREFIJO_EVIDENCIAS + f.relative_to(r.evidencias).as_posix(), compress_type=tipo)
                n_archivos += 1
        if r.estado_vigilante.exists():
            z.write(r.estado_vigilante, "vigilante_estado.json")
        incluye_excel = False
        if con_excel and r.incidencias.exists():
            for f in sorted(r.incidencias.rglob("*.xlsx")):
                if f.relative_to(r.incidencias).parts[0] in ("respaldo", "procesadas") or f.name.startswith("~$"):
                    continue
                z.write(f, PREFIJO_INCIDENCIAS + f.relative_to(r.incidencias).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
                incluye_excel = True
        z.writestr("MANIFIESTO.json", json.dumps({
            "creado": datetime.now().isoformat(timespec="seconds"), "pc": socket.gethostname(), "archivos_de_evidencia": n_archivos,
            "incluye_excel": incluye_excel,
        }, ensure_ascii=False, indent=2))
    return destino


def importar(raiz: Path, zip_ruta: Path, con_excel: bool = False) -> dict:
    """Mezcla un .zip de traspaso en este PC. Devuelve un resumen de lo hecho."""
    r = Rutas(raiz)
    resumen: dict = {}
    r.indice_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, zipfile.ZipFile(zip_ruta) as z:
        nombres = z.namelist()
        if "MANIFIESTO.json" in nombres:
            resumen["origen"] = json.loads(z.read("MANIFIESTO.json").decode("utf-8"))
        # 1) evidencias: se copian sin pisar lo que ya existe
        copiados = omitidos = 0
        for n in nombres:
            if n.startswith(PREFIJO_EVIDENCIAS) and not n.endswith("/"):
                dest = r.evidencias / n[len(PREFIJO_EVIDENCIAS):]
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
            if r.indice_db.exists():
                resp = r.indice_dir / "respaldo"
                resp.mkdir(exist_ok=True)
                shutil.copy2(r.indice_db, resp / f"indice_antes_de_importar_{datetime.now():%Y%m%d_%H%M}.sqlite3")
            z.extract("indice.sqlite3", tmp)
            with Indice(r.indice_db) as ix:
                resumen.update(ix.fusionar(Path(tmp) / "indice.sqlite3"))
                resumen["rutas_reapuntadas"] = ix.rebasar_rutas(r.evidencias)
        # 3) estado del vigilante (solo si aquí no hay)
        if "vigilante_estado.json" in nombres and not r.estado_vigilante.exists():
            r.logs_estado.mkdir(parents=True, exist_ok=True)
            r.estado_vigilante.write_bytes(z.read("vigilante_estado.json"))
        # 4) incidencias: solo si se pide (deja copia de la base actual)
        if con_excel:
            reemplazados = []
            for n in nombres:
                if n.startswith(PREFIJO_INCIDENCIAS) and n.endswith(".xlsx"):
                    destino = r.incidencias / n[len(PREFIJO_INCIDENCIAS):]
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    if destino.exists():
                        (r.incidencias / "respaldo").mkdir(exist_ok=True)
                        shutil.copy2(destino, r.incidencias / "respaldo" / f"{destino.stem}_antes_de_importar_{datetime.now():%Y%m%d_%H%M}.xlsx")
                    destino.write_bytes(z.read(n))
                    reemplazados.append(destino.name)
            for sub in ("nuevas", "procesadas", "respaldo", "original"):
                (r.incidencias / sub).mkdir(parents=True, exist_ok=True)
            resumen["excel_reemplazado"] = reemplazados
    return resumen
