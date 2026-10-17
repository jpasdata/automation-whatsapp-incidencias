#!/usr/bin/env python3
"""
Interfaz sencilla: elige grupo, modo y tiempo (hoy y N días antes), un botón INICIAR/DETENER y un panel que muestra
qué está haciendo (grupo, fase, tandas, cruce en vivo, descargas) más el registro en vivo.

Uso:  python scripts/interfaz.py     (o doble clic en Iniciar_interfaz.bat)

No contiene lógica propia: lanza scripts/cargar_historico.py (o scripts/actualizar.py) como proceso aparte
y lee lo que ese proceso va escribiendo. El detalle completo queda en logs/detalle.log.
"""
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.config import load_config  # noqa: E402
from src.descargas import RAIZ_EVIDENCIAS  # noqa: E402
from src.estado_descargas import resumen as resumen_descargas  # noqa: E402
from src.historico import RUTA_INDICE  # noqa: E402
from src.indice import Indice  # noqa: E402
from src.verificador import hay_errores, informe, verificar  # noqa: E402

TODOS = "(TODOS los grupos, uno tras otro)"
# modo -> (script, opciones fijas)
MODOS = {
    "Subir + cruzar + descargar lo que cruza": ("scripts/cargar_historico.py", ["--descargar"]),
    "Subir + cruzar + descargar TODO (cruce o no)": ("scripts/cargar_historico.py", ["--descargar", "--todo"]),
    "Solo subir e indexar (sin descargar)": ("scripts/cargar_historico.py", []),
    "Solo actualizar lo nuevo (rápido, todos los grupos)": ("scripts/actualizar.py", []),
    "VIGILANTE: bajar todo lo que llega, todo el día": ("scripts/vigilante.py", []),
}


class Interfaz:
    def __init__(self, raiz: tk.Tk):
        self.cfg = load_config()
        self.r = raiz
        self.proc: subprocess.Popen | None = None
        self.cola: queue.Queue[str] = queue.Queue()
        self.inicio: datetime | None = None
        self.parar = False
        raiz.title("Evidencias WhatsApp - Incidencias")
        raiz.geometry("940x680")
        marco = ttk.Frame(raiz, padding=10)
        marco.pack(fill="both", expand=True)

        f1 = ttk.Frame(marco)
        f1.pack(fill="x")
        ttk.Label(f1, text="Grupo:").pack(side="left")
        self.grupo = tk.StringVar(value=self.cfg.whatsapp.grupos[0])
        ttk.Combobox(f1, textvariable=self.grupo, values=[*self.cfg.whatsapp.grupos, TODOS], width=46, state="readonly").pack(side="left", padx=6)
        ttk.Label(f1, text="Modo:").pack(side="left")
        self.modo = tk.StringVar(value=list(MODOS)[0])
        ttk.Combobox(f1, textvariable=self.modo, values=list(MODOS), width=44, state="readonly").pack(side="left", padx=6)

        f2 = ttk.Frame(marco)
        f2.pack(fill="x", pady=6)
        ttk.Label(f2, text="Tiempo: hoy y").pack(side="left")
        self.dias = tk.StringVar(value="4")
        ttk.Spinbox(f2, from_=0, to=60, textvariable=self.dias, width=4).pack(side="left", padx=4)
        ttk.Label(f2, text="días antes   |   o desde (AAAA-MM-DD, opcional):").pack(side="left")
        self.desde = tk.StringVar(value="")
        ttk.Entry(f2, textvariable=self.desde, width=12).pack(side="left", padx=4)
        ttk.Label(f2, text="   Tope por grupo (min):").pack(side="left")
        self.minutos = tk.StringVar(value="100")
        ttk.Spinbox(f2, from_=5, to=600, textvariable=self.minutos, width=5).pack(side="left", padx=4)

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=6)
        self.btn = tk.Button(botones, text="INICIAR", font=("Segoe UI", 14, "bold"), bg="#2e7d32", fg="white", width=12, command=self.alternar)
        self.btn.pack(side="left")
        for texto, cmd in (("Verificar entorno", self.verificar_entorno), ("Estado de descargas", self.ver_estado_descargas), ("Generar reporte Excel", self.generar_reporte),
                           ("Abrir evidencias", lambda: os.startfile(RAIZ_EVIDENCIAS)), ("Abrir logs", lambda: os.startfile(RAIZ / "logs"))):
            tk.Button(botones, text=texto, font=("Segoe UI", 10), command=cmd).pack(side="left", padx=5)
        self.estado = tk.StringVar(value="Detenido")
        tk.Label(botones, textvariable=self.estado, font=("Segoe UI", 12, "bold")).pack(side="left", padx=12)

        panel = ttk.LabelFrame(marco, text="Qué está haciendo", padding=8)
        panel.pack(fill="x")
        claves = [("grupo", "Grupo actual"), ("fase", "Fase"), ("tandas", "Tandas cargadas"), ("tiempo", "Tiempo corrido"),
                  ("indice", "Mensajes en el índice"), ("antiguo", "Mensaje más antiguo"), ("cruce", "Cruce en vivo"), ("fotos", "Descargas")]
        self.v = {k: tk.StringVar(value="-") for k, _ in claves}
        for i, (k, t) in enumerate(claves):
            ancho = k in ("cruce",)
            ttk.Label(panel, text=t + ":").grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=4, pady=2)
            ttk.Label(panel, textvariable=self.v[k], font=("Segoe UI", 9, "bold"), wraplength=330 if not ancho else 330).grid(
                row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=4)

        self.texto = tk.Text(marco, height=18, bg="#111", fg="#ddd", font=("Consolas", 9), wrap="word")
        self.texto.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(marco, text="Mientras corre, no muevas el mouse ni toques la ventana de Chromium (el scroll usa el mouse real).",
                  foreground="#b71c1c").pack(anchor="w", pady=(4, 0))
        self.refrescar()

    # --- control -----------------------------------------------------------------------------
    def alternar(self) -> None:
        if self.btn.cget("text") == "DETENER":
            self.detener()
        else:
            self.iniciar()

    def _mostrar(self, texto: str) -> None:
        self.texto.delete("1.0", "end")
        self.texto.insert("end", texto + "\n")

    def verificar_entorno(self) -> bool:
        """Corre las revisiones previas y las muestra en el panel. True si se puede correr."""
        self.estado.set("Verificando...")
        self.r.update_idletasks()
        res = verificar()
        self._mostrar(informe(res))
        ok = not hay_errores(res)
        self.estado.set("Listo para correr" if ok else "Hay errores: lee 'QUÉ HACER'")
        return ok

    def ver_estado_descargas(self) -> None:
        self._mostrar(resumen_descargas())

    def generar_reporte(self) -> None:
        """Genera el reporte Excel con formato a partir de lo indexado y descargado (no abre WhatsApp)."""
        orden = [sys.executable, "scripts/generar_reporte.py", "--todos"]
        orden += ["--desde", self.desde.get().strip()] if self.desde.get().strip() else ["--dias", self.dias.get().strip() or "4"]
        self.estado.set("Generando reporte...")
        self.r.update_idletasks()
        p = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=0x08000000)
        self._mostrar((p.stdout + p.stderr).strip())
        self.estado.set("Reporte listo (carpeta data/Reportes)" if p.returncode == 0 else "Error al generar el reporte")
        if p.returncode == 0:
            os.startfile(RAIZ / "data" / "Reportes")

    def armar_comando(self) -> list[str]:
        script, fijas = MODOS[self.modo.get()]
        orden = [sys.executable, "-u", script, *fijas]
        if "vigilante" in script:
            orden += ["--todos"] if self.grupo.get() == TODOS else ["--grupo", self.grupo.get()]
        if "cargar_historico" in script:
            orden += ["--todos"] if self.grupo.get() == TODOS else ["--grupo", self.grupo.get()]
            orden += ["--minutos", self.minutos.get()]
            if self.desde.get().strip():
                orden += ["--desde", self.desde.get().strip()]
            elif self.dias.get().strip():
                orden += ["--dias", self.dias.get().strip()]
        return orden

    def iniciar(self) -> None:
        if not self.verificar_entorno():
            return
        orden = self.armar_comando()
        self.parar = False
        self._mostrar("Comando: " + " ".join(orden[2:]) + "\n")
        threading.Thread(target=self._correr, args=(orden,), daemon=True).start()
        self.inicio = datetime.now()
        self.btn.config(text="DETENER", bg="#c62828")
        self.estado.set("Corriendo...")
        for k in ("grupo", "fase", "tandas", "cruce", "fotos"):
            self.v[k].set("-")
        self.v["fase"].set("Abriendo WhatsApp Web")

    def _correr(self, orden: list[str]) -> None:
        entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(orden, cwd=RAIZ, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
        for linea in self.proc.stdout:  # type: ignore[union-attr]
            self.cola.put(linea.rstrip())
        self.proc.wait()
        self.cola.put("\0FIN")

    def detener(self) -> None:
        self.parar = True
        if self.proc and self.proc.poll() is None:
            # taskkill /T cierra también el navegador que abrió el proceso
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, creationflags=0x08000000)
        self.estado.set("Detenido por ti")

    # --- refresco ----------------------------------------------------------------------------
    def _interpretar(self, linea: str) -> None:
        if m := re.search(r"##### Grupo (\d+)/(\d+): (.+?) #####", linea):
            self.v["grupo"].set(f"{m[1]}/{m[2]}: {m[3][:42]}")
        if m := re.search(r"Ronda (\d+) - fase (\d)", linea):
            self.v["fase"].set(f"Ronda {m[1]}: " + ("subiendo el chat" if m[2] == "1" else "leyendo lo cargado"))
        if m := re.search(r"tandas: (\d+) \| burbujas: (\d+)", linea):
            self.v["tandas"].set(f"{m[1]}  (burbujas pintadas: {m[2]})")
        if "CRUCE EN VIVO" in linea:
            self.v["cruce"].set(linea.split("CRUCE EN VIVO:")[-1].strip()[:200])
        if m := re.search(r"DESCARGA \(pasada (\d)/(\d)\)", linea):
            self.v["fase"].set(f"Descargando (pasada {m[1]}/{m[2]})")
        if "Bajando " in linea or "-> ok" in linea or "-> error" in linea or "-> parcial" in linea or "Barrido" in linea or "DESCARGA" in linea:
            self.v["fotos"].set(linea.split("|")[-1].strip()[:150])
        if "VUELTA:" in linea:
            self.v["fotos"].set(linea.split("VUELTA:")[-1].strip()[:150])
            self.v["fase"].set("Vigilante: " + linea.split("]")[0].split("|")[-1].strip()[:40])
        if "IDENTIFICADA DESPUÉS" in linea:
            self.v["cruce"].set(linea.split("IDENTIFICADA DESPUÉS:")[-1].strip()[:160])
        if "Histórico completo" in linea:
            self.v["fase"].set("Histórico completo: pasando a descargar")

    def refrescar(self) -> None:
        try:
            while True:
                linea = self.cola.get_nowait()
                if linea == "\0FIN":
                    cod = self.proc.poll() if self.proc else None
                    self.btn.config(text="INICIAR", bg="#2e7d32")
                    if self.estado.get() != "Detenido por ti":
                        self.estado.set("Terminado" if cod == 0 else f"Terminó con código {cod}")
                    continue
                self._interpretar(linea)
                self.texto.insert("end", linea + "\n")
                self.texto.see("end")
        except queue.Empty:
            pass
        if self.inicio and self.btn.cget("text") == "DETENER":
            self.v["tiempo"].set(str(datetime.now() - self.inicio).split(".")[0])
        self._resumen_indice()
        self.r.after(1000, self.refrescar)

    def _resumen_indice(self) -> None:
        try:
            with Indice(RUTA_INDICE) as ix:
                g = next((x for x in ix.grupos() if self.grupo.get().lower() in x.lower() or x.lower() in self.grupo.get().lower()), None)
                if g:
                    self.v["indice"].set(str(ix.contar(g)))
                    a = ix.rango(g)[0]
                    self.v["antiguo"].set(a.strftime("%Y-%m-%d %H:%M") if a else "-")
            if self.v["fotos"].get() in ("-", ""):
                n = sum(1 for p in RAIZ_EVIDENCIAS.rglob("*") if p.is_file() and p.name != ".gitkeep")
                self.v["fotos"].set(f"{n} archivos en data/Evidencias_WhatsApp")
        except Exception:  # noqa: BLE001 - el índice puede estar bloqueado un instante
            pass


if __name__ == "__main__":
    raiz = tk.Tk()
    Interfaz(raiz)
    raiz.mainloop()
