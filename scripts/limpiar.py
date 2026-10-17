#!/usr/bin/env python3
"""
Limpieza segura del proyecto. NUNCA borra evidencias, el índice, la sesión de WhatsApp ni las incidencias: lo que sobra se ARCHIVA.

Qué hace:
  1. Respalda el índice (data/indice/respaldo/, se conservan los 5 más recientes).
  2. Quita cachés de Python (__pycache__, .pytest_cache).
  3. Logs: archiva los archivos sueltos de logs/ que no son de una corrida, y las carpetas de corridas de más de `--dias-logs` días
     (por defecto 30) a logs/archivo/corridas_viejas/.
  4. Reportes: los Excel con fecha que queden sueltos en data/Reportes/ pasan a data/Reportes/historial/; quita copias duplicadas idénticas.
  5. Quita carpetas vacías dentro de data/Evidencias_WhatsApp/ y el candado de sesión si quedó de un proceso que ya no existe.
  6. Con --reorganizar: mueve/renombra lo ya descargado según el cruce actual (scripts/reorganizar_descargas.py).

Uso:  python scripts/limpiar.py --simular      (solo muestra lo que haría)
      python scripts/limpiar.py                (lo aplica)
"""
import argparse
import filecmp
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.nucleo.bloqueo import _vivo  # noqa: E402
from src.nucleo.rutas import R  # noqa: E402

LOGS_PROTEGIDOS = ("corridas", "estado", "archivo", "ultima_corrida.txt", ".gitkeep")


def planificar(dias_logs: int = 30) -> list[tuple[str, Path, Path | None]]:
    """Lista de acciones (tipo, origen, destino|None). No toca nada."""
    ahora = datetime.now()
    acciones: list[tuple[str, Path, Path | None]] = []
    for d in RAIZ.rglob("__pycache__"):
        if ".venv" not in d.parts and "sesion_whatsapp" not in d.parts:
            acciones.append(("borrar caché", d, None))
    if (RAIZ / ".pytest_cache").exists():
        acciones.append(("borrar caché", RAIZ / ".pytest_cache", None))
    # logs sueltos y corridas viejas
    destino_logs = R.logs_archivo / f"limpieza_{ahora:%Y-%m-%d_%H%M}"
    for f in sorted(R.logs.iterdir()) if R.logs.exists() else []:
        if f.name not in LOGS_PROTEGIDOS:
            acciones.append(("archivar log suelto", f, destino_logs / f.name))
    limite = time.time() - dias_logs * 86400
    for dia in sorted(R.logs_corridas.iterdir()) if R.logs_corridas.exists() else []:
        for corrida in sorted(dia.iterdir()) if dia.is_dir() else []:
            if corrida.is_dir() and corrida.stat().st_mtime < limite:
                acciones.append((f"archivar corrida de hace más de {dias_logs} días", corrida, R.logs_archivo / "corridas_viejas" / dia.name / corrida.name))
    # reportes
    for f in sorted(R.reportes.glob("Reporte_*.xlsx")) if R.reportes.exists() else []:
        acciones.append(("archivar reporte con fecha", f, R.reportes_historial / f.name))
    for carpeta in (R.reportes_historial, R.reportes_analisis):
        for f in sorted(carpeta.glob("*_dup.*")) if carpeta.exists() else []:
            original = f.with_name(f.name.replace("_dup", ""))
            if original.exists() and filecmp.cmp(f, original, shallow=False):
                acciones.append(("quitar copia duplicada idéntica", f, None))
    # evidencias vacías y candado
    if R.evidencias.exists():
        for d in sorted((p for p in R.evidencias.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
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
    if respaldar_indice and R.indice_db.exists():
        carpeta = R.indice_dir / "respaldo"
        carpeta.mkdir(exist_ok=True)
        nuevo = carpeta / f"indice_{datetime.now():%Y%m%d_%H%M}.sqlite3"
        shutil.copy2(R.indice_db, nuevo)
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
    ap.add_argument("--dias-logs", type=int, default=30, help="corridas de log más viejas que esto se archivan (default 30)")
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

    acciones = planificar(args.dias_logs)
    resumen: dict[str, int] = {}
    for tipo, *_ in acciones:
        resumen[tipo] = resumen.get(tipo, 0) + 1
    print("=== LIMPIEZA " + ("(SIMULACIÓN: no se toca nada)" if args.simular else "") + " ===")
    print("Se respalda el índice (data/indice/respaldo/)." if R.indice_db.exists() else "No hay índice que respaldar.")
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
    print("Listo. Nada de evidencias, índice, sesión ni incidencias fue borrado.")


if __name__ == "__main__":
    main()
