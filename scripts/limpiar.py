#!/usr/bin/env python3
"""
Limpieza segura del proyecto. NUNCA borra evidencias, el índice, la sesión de WhatsApp ni el Excel: lo que sobra se ARCHIVA.

Qué hace:
  1. Respalda el índice (data/indice/respaldo/, se conservan los 5 más recientes).
  2. Quita cachés de Python (__pycache__, .pytest_cache).
  3. Mueve a logs/archivo/limpieza_<fecha>/ los archivos sueltos de logs/ que no usa el bot (pruebas, capturas, salidas viejas).
  4. Mueve los reportes Excel con fecha de data/Reportes/ a data/Reportes/pruebas/ (deja Cruce_en_vivo y el CRUZADO).
  5. Quita carpetas vacías dentro de data/Evidencias_WhatsApp/ y el candado de sesión si quedó de un proceso que ya no existe.
  6. Con --reorganizar: mueve/renombra lo ya descargado según el cruce actual (scripts/reorganizar_descargas.py).

Uso:  python scripts/limpiar.py --simular      (solo muestra lo que haría)
      python scripts/limpiar.py                (lo aplica)
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bloqueo import _vivo  # noqa: E402

LOGS_DEL_BOT = ("automatizacion.log", "detalle.log", "descargas_detalle.csv", "descargas_pendientes.csv", "eventos_bot.csv", ".gitkeep")


def planificar() -> list[tuple[str, Path, Path | None]]:
    """Lista de acciones (tipo, origen, destino|None). No toca nada."""
    ahora = datetime.now()
    acciones: list[tuple[str, Path, Path | None]] = []
    for d in RAIZ.rglob("__pycache__"):
        if ".venv" not in d.parts and "sesion_whatsapp" not in d.parts:
            acciones.append(("borrar caché", d, None))
    if (RAIZ / ".pytest_cache").exists():
        acciones.append(("borrar caché", RAIZ / ".pytest_cache", None))
    logs = RAIZ / "logs"
    destino_logs = logs / "archivo" / f"limpieza_{ahora:%Y-%m-%d_%H%M}"
    for f in sorted(logs.iterdir()) if logs.exists() else []:
        if f.name in ("archivo",) or f.name.startswith(LOGS_DEL_BOT[:2]):
            continue
        if f.name not in LOGS_DEL_BOT:
            acciones.append(("archivar log suelto", f, destino_logs / f.name))
    rep = RAIZ / "data" / "Reportes"
    for f in sorted(rep.glob("Reporte_*.xlsx")) if rep.exists() else []:
        acciones.append(("archivar reporte con fecha", f, rep / "pruebas" / f.name))
    ev = RAIZ / "data" / "Evidencias_WhatsApp"
    if ev.exists():
        for d in sorted((p for p in ev.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(d.iterdir()):
                acciones.append(("quitar carpeta vacía", d, None))
    lock = RAIZ / "sesion_whatsapp.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if not pid or not _vivo(pid):
            acciones.append(("quitar candado huérfano", lock, None))
    return acciones


def aplicar(acciones, respaldar_indice: bool = True) -> list[str]:
    hechas: list[str] = []
    if respaldar_indice:
        idx = RAIZ / "data" / "indice" / "indice.sqlite3"
        if idx.exists():
            carpeta = idx.parent / "respaldo"
            carpeta.mkdir(exist_ok=True)
            nuevo = carpeta / f"indice_{datetime.now():%Y%m%d_%H%M}.sqlite3"
            shutil.copy2(idx, nuevo)
            hechas.append(f"respaldo del índice: {nuevo.name}")
            for viejo in sorted(carpeta.glob("indice_*.sqlite3"))[:-5]:
                viejo.unlink()
                hechas.append(f"respaldo viejo eliminado: {viejo.name}")
    for tipo, origen, destino in acciones:
        try:
            if destino is not None:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(origen), str(destino))
            elif origen.is_dir():
                shutil.rmtree(origen) if tipo == "borrar caché" else origen.rmdir()
            else:
                origen.unlink()
            hechas.append(f"{tipo}: {origen.relative_to(RAIZ)}")
        except OSError as e:  # archivo abierto en otro programa (p. ej. un Excel): se omite y se sigue
            hechas.append(f"OMITIDO ({tipo}, está en uso o sin permiso): {origen.relative_to(RAIZ)} - {str(e)[:60]}")
    return hechas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="solo mostrar lo que se haría")
    ap.add_argument("--reorganizar", action="store_true", help="además, reorganizar lo ya descargado")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lock = RAIZ / "sesion_whatsapp.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text().strip() or 0)
        except ValueError:
            pid = 0
        if pid and _vivo(pid):
            sys.exit(f"Hay un proceso del bot corriendo (pid {pid}). Deténlo antes de limpiar.")

    acciones = planificar()
    resumen: dict[str, int] = {}
    for tipo, *_ in acciones:
        resumen[tipo] = resumen.get(tipo, 0) + 1
    print("=== LIMPIEZA " + ("(SIMULACIÓN: no se toca nada)" if args.simular else "") + " ===")
    print("Se respalda el índice (data/indice/respaldo/)." if (RAIZ / "data/indice/indice.sqlite3").exists() else "No hay índice que respaldar.")
    for tipo, n in resumen.items():
        print(f"  - {tipo}: {n}")
    if args.reorganizar:
        print("  - reorganizar lo ya descargado según el cruce actual")
    if not acciones and not args.reorganizar:
        print("Nada que limpiar: el proyecto ya está ordenado.")
    if args.simular:
        for tipo, origen, destino in acciones[:40]:
            print(f"      {tipo}: {origen.relative_to(RAIZ)}" + (f" -> {destino.relative_to(RAIZ)}" if destino else ""))
        if len(acciones) > 40:
            print(f"      ... y {len(acciones) - 40} más")
        return
    for linea in aplicar(acciones):
        print("  ", linea)
    if args.reorganizar:
        print("Reorganizando lo descargado...")
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "reorganizar_descargas.py")], cwd=RAIZ, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print("\n".join(l for l in (r.stdout + r.stderr).splitlines() if "reorganizados" in l or "no conoce" in l or "Error" in l))
    print("Listo. Nada de evidencias, índice, sesión ni Excel fue borrado.")


if __name__ == "__main__":
    main()
