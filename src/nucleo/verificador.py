"""
Verificador previo ("preflight"): revisa que el PC y el proyecto estén listos para correr y, si algo falla,
dice QUÉ HACER para arreglarlo. Se usa antes de iniciar (interfaz y scripts).

Niveles: OK (todo bien) · AVISO (se puede correr, pero ojo) · ERROR (no correr hasta arreglarlo).
"""
from __future__ import annotations

import importlib
import os
import shutil
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .rutas import R, Rutas

RAIZ = R.raiz
OK, AVISO, ERROR = "OK", "AVISO", "ERROR"


@dataclass
class Resultado:
    nivel: str
    titulo: str
    detalle: str = ""
    arreglo: str = ""   # qué hacer si no está OK

    def texto(self) -> str:
        marca = {OK: "[ OK  ]", AVISO: "[AVISO]", ERROR: "[ERROR]"}[self.nivel]
        t = f"{marca} {self.titulo}" + (f" - {self.detalle}" if self.detalle else "")
        if self.nivel != OK and self.arreglo:
            t += f"\n          -> QUÉ HACER: {self.arreglo}"
        return t


def _r(nivel, titulo, detalle="", arreglo="") -> Resultado:
    return Resultado(nivel, titulo, detalle, arreglo)


def revisar_python() -> Resultado:
    v = sys.version_info
    if v < (3, 10):
        return _r(ERROR, "Python", f"{v.major}.{v.minor}", "Instala Python 3.10 o superior (https://www.python.org/downloads/) y vuelve a abrir.")
    return _r(OK, "Python", f"{v.major}.{v.minor}.{v.micro}")


def revisar_paquetes() -> list[Resultado]:
    faltan = []
    for modulo in ("playwright", "pandas", "openpyxl", "yaml"):
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltan.append(modulo)
    if faltan:
        return [_r(ERROR, "Librerías de Python", "faltan: " + ", ".join(faltan),
                   "En la carpeta del proyecto ejecuta:  pip install -r requirements.txt")]
    return [_r(OK, "Librerías de Python", "playwright, pandas, openpyxl, PyYAML")]


def revisar_chromium() -> Resultado:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            ruta = Path(pw.chromium.executable_path)
        if ruta.exists():
            return _r(OK, "Navegador Chromium de Playwright")
    except Exception:  # noqa: BLE001
        pass
    return _r(ERROR, "Navegador Chromium de Playwright", "no está instalado",
              "Ejecuta:  python -m playwright install chromium")


def revisar_pantalla() -> Resultado:
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return _r(AVISO, "Interfaz gráfica (tkinter)", "no disponible",
                  "Reinstala Python marcando 'tcl/tk and IDLE'. Sin esto se puede correr por consola (scripts/cargar_historico.py).")
    return _r(OK, "Interfaz gráfica (tkinter)")


def revisar_internet() -> Resultado:
    try:
        socket.create_connection(("web.whatsapp.com", 443), timeout=6).close()
        return _r(OK, "Internet / WhatsApp Web", "web.whatsapp.com responde")
    except OSError:
        return _r(ERROR, "Internet / WhatsApp Web", "no se llega a web.whatsapp.com",
                  "Revisa la conexión, el proxy o el firewall del PC.")


def revisar_disco(raiz: Path = RAIZ, minimo_gb: float = 2.0) -> Resultado:
    libre = shutil.disk_usage(raiz).free / 1e9
    if libre < minimo_gb:
        return _r(AVISO, "Espacio en disco", f"{libre:.1f} GB libres",
                  f"Libera espacio (se recomiendan {minimo_gb:.0f} GB+; las fotos y la sesión de WhatsApp ocupan bastante).")
    return _r(OK, "Espacio en disco", f"{libre:.0f} GB libres")


def revisar_carpetas(raiz: Path = RAIZ) -> Resultado:
    malas = []
    for d in Rutas(raiz).carpetas_de_trabajo():
        rel = str(d.relative_to(raiz)).replace("\\", "/")
        try:
            d.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=d):
                pass
        except OSError:
            malas.append(rel)
    if malas:
        return _r(ERROR, "Carpetas de trabajo", "sin permiso de escritura en: " + ", ".join(malas),
                  "Mueve el proyecto a una carpeta donde tu usuario pueda escribir (no Archivos de Programa).")
    return _r(OK, "Carpetas de trabajo", "data/, logs/ y evidencias escribibles")


def revisar_candado(raiz: Path = RAIZ) -> Resultado:
    from src.nucleo.bloqueo import _vivo

    lock = raiz / "sesion_whatsapp.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and pid != os.getpid() and _vivo(pid):
            return _r(ERROR, "Otra corrida activa", f"el proceso {pid} ya usa la sesión de WhatsApp",
                      "Espera a que termine o ciérralo (dos procesos con la misma sesión la dañan).")
    return _r(OK, "Ninguna otra corrida usando la sesión")


def revisar_config(raiz: Path = RAIZ):
    """Devuelve (lista de resultados, cfg o None)."""
    from src.nucleo.config import ConfigError, load_config, resolver_cargar_desde

    ruta = raiz / "config" / "config.yaml"
    if not ruta.exists():
        return [_r(ERROR, "config/config.yaml", "no existe",
                   "Copia config/config.example.yaml a config/config.yaml y ajusta grupos, Excel y provincias.")], None
    try:
        cfg = load_config(ruta)
    except (ConfigError, Exception) as e:  # noqa: BLE001
        return [_r(ERROR, "config/config.yaml", f"inválido: {str(e)[:150]}", "Corrige el archivo siguiendo config.example.yaml.")], None
    res = [_r(OK, "config/config.yaml", "carga bien")]
    grupos = [g for g in cfg.whatsapp.grupos if g and g != "NOMBRE_EXACTO_DEL_GRUPO"]
    if not grupos:
        res.append(_r(ERROR, "Grupos de WhatsApp", "no hay ninguno configurado",
                      "En config.yaml, whatsapp.grupos: pon parte del título de cada grupo (python scripts/listar_grupos.py los muestra)."))
    else:
        res.append(_r(OK, "Grupos de WhatsApp", ", ".join(grupos)))
    if resolver_cargar_desde(cfg.whatsapp.cargar_desde) is None:
        res.append(_r(AVISO, "Fecha de inicio del histórico", "whatsapp.cargar_desde está vacío",
                      "Pon 'mes_actual' o una fecha AAAA-MM-DD (p. ej. 2026-10-01) para saber hasta dónde subir."))
    return res, cfg


def revisar_excel(cfg, raiz: Path = RAIZ) -> list[Resultado]:
    from src.nucleo.config import provincias_de_grupo
    from src.excel.manager import ExcelManager

    ruta = Path(cfg.excel.ruta_archivo)
    if not ruta.is_absolute():
        ruta = raiz / ruta
    if not ruta.exists():
        return [_r(ERROR, "Excel de incidencias", f"no existe {ruta}",
                   "Si este PC es nuevo: abre la interfaz, pulsa «Importar traspaso» y responde «sí» a reemplazar el Excel (la base viaja en el traspaso). "
                   "O copia INCIDENCIAS_BASE.xlsx a data\\Incidencias\\. También puedes crearla desde el Excel original: python scripts/incidencias.py crear.")]
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            copia = Path(tmp) / "copia.xlsx"
            shutil.copy(ruta, copia)  # se revisa una copia: el original no se toca
            e = cfg.excel
            excel = ExcelManager.desde_config(str(copia), e)
            excel.abrir()
            por_provincia = excel.resumen_por_provincia()
    except Exception as ex:  # noqa: BLE001
        return [_r(ERROR, "Excel de incidencias", f"no se pudo leer: {str(ex)[:160]}",
                   "Revisa que la hoja y los nombres de columna de config.yaml (sección excel) coincidan con el Excel (si venías de una versión anterior, corre: python scripts/traspaso.py ajustar-config).")]
    res = [_r(OK, "Excel de incidencias", f"hoja '{cfg.excel.nombre_hoja}', {sum(por_provincia.values())} incidencias")]
    for g in cfg.whatsapp.grupos:
        provs = provincias_de_grupo(cfg, g)
        if not provs:
            res.append(_r(AVISO, f"Provincia del grupo '{g}'", "sin provincia configurada: cruzará contra TODO el Excel",
                          "Agrégala en config.yaml, matching.provincias_por_grupo."))
        elif not any(por_provincia.get(p, 0) for p in provs):
            res.append(_r(AVISO, f"Provincia del grupo '{g}'", f"{sorted(provs)} no aparece en el Excel",
                          "Revisa que el nombre de la provincia coincida con la columna del Excel."))
        else:
            res.append(_r(OK, f"Provincia del grupo '{g}'", f"{sum(por_provincia.get(p, 0) for p in provs)} incidencias"))
    return res


def revisar_sesion(cfg, raiz: Path = RAIZ) -> Resultado:
    carpeta = Path(cfg.whatsapp.carpeta_sesion)
    if not carpeta.is_absolute():
        carpeta = raiz / carpeta
    if carpeta.exists() and any(carpeta.iterdir()):
        return _r(OK, "Sesión de WhatsApp Web", "hay un login guardado (si pidiera QR, escanéalo)")
    return _r(AVISO, "Sesión de WhatsApp Web", "primera vez en este PC",
              "Al iniciar se abrirá WhatsApp Web: escanea el QR con el celular y NO cierres la ventana hasta ver tus chats.")


def verificar(raiz: Path = RAIZ) -> list[Resultado]:
    """Corre todas las revisiones. Un error en una no impide que se muestren las demás."""
    res = [revisar_python(), *revisar_paquetes(), revisar_chromium(), revisar_pantalla(), revisar_internet(),
           revisar_disco(raiz), revisar_carpetas(raiz), revisar_candado(raiz)]
    r_cfg, cfg = revisar_config(raiz)
    res += r_cfg
    if cfg is not None:
        res += revisar_excel(cfg, raiz)
        res.append(revisar_sesion(cfg, raiz))
    return res


def hay_errores(resultados: list[Resultado]) -> bool:
    return any(r.nivel == ERROR for r in resultados)


def informe(resultados: list[Resultado]) -> str:
    n_err = sum(r.nivel == ERROR for r in resultados)
    n_av = sum(r.nivel == AVISO for r in resultados)
    pie = ("LISTO PARA CORRER" if not n_err else f"NO CORRER TODAVÍA: {n_err} error(es) por arreglar")
    return "\n".join(r.texto() for r in resultados) + f"\n\n=> {pie}" + (f" ({n_av} aviso(s))" if n_av else "")
