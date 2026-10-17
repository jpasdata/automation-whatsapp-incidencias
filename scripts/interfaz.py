#!/usr/bin/env python3
"""
Interfaz sencilla: un botón para iniciar/detener la carga de histórico + descarga de evidencias y un panel
que muestra qué está haciendo (fase, avance del índice, fotos descargadas y el registro en vivo).

Uso:  python scripts/interfaz.py     (o doble clic en Iniciar_interfaz.bat)

No contiene lógica propia: lanza scripts/cargar_historico.py (o scripts/actualizar.py) como proceso aparte
y lee lo que ese proceso va escribiendo.
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
from src.historico import RUTA_INDICE  # noqa: E402
from src.indice import Indice  # noqa: E402

MODOS = {
    "Histórico + descargar evidencias": ["scripts/cargar_historico.py", "--descargar"],
    "Histórico sin descargar": ["scripts/cargar_historico.py"],
    "Solo actualizar lo nuevo": ["scripts/actualizar.py"],
}


class Interfaz:
    def __init__(self, raiz: tk.Tk):
        self.cfg = load_config()
        self.r = raiz
        self.proc: subprocess.Popen | None = None
        self.cola: queue.Queue[str] = queue.Queue()
        self.inicio: datetime | None = None
        raiz.title("Evidencias WhatsApp - Incidencias")
        raiz.geometry("860x600")
        marco = ttk.Frame(raiz, padding=10)
        marco.pack(fill="both", expand=True)

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Grupo:").pack(side="left")
        self.grupo = tk.StringVar(value=self.cfg.whatsapp.grupos[0])
        ttk.Combobox(fila, textvariable=self.grupo, values=self.cfg.whatsapp.grupos, width=38).pack(side="left", padx=6)
        ttk.Label(fila, text="Modo:").pack(side="left")
        self.modo = tk.StringVar(value=list(MODOS)[0])
        ttk.Combobox(fila, textvariable=self.modo, values=list(MODOS), width=30, state="readonly").pack(side="left", padx=6)
        ttk.Label(fila, text="Minutos:").pack(side="left")
        self.minutos = tk.StringVar(value="100")
        ttk.Spinbox(fila, from_=5, to=600, textvariable=self.minutos, width=5).pack(side="left", padx=6)

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=8)
        self.btn = tk.Button(botones, text="INICIAR", font=("Segoe UI", 14, "bold"), bg="#2e7d32", fg="white",
                             width=14, command=self.alternar)
        self.btn.pack(side="left")
        self.estado = tk.StringVar(value="Detenido")
        tk.Label(botones, textvariable=self.estado, font=("Segoe UI", 13, "bold")).pack(side="left", padx=16)

        panel = ttk.LabelFrame(marco, text="Qué está haciendo", padding=8)
        panel.pack(fill="x")
        self.v = {k: tk.StringVar(value="-") for k in ("fase", "tandas", "indice", "antiguo", "fotos", "tiempo")}
        etiquetas = [("fase", "Fase"), ("tandas", "Tandas cargadas"), ("indice", "Mensajes en el índice"),
                     ("antiguo", "Mensaje más antiguo"), ("fotos", "Descargas"), ("tiempo", "Tiempo corrido")]
        for i, (k, t) in enumerate(etiquetas):
            ttk.Label(panel, text=t + ":").grid(row=i // 2, column=(i % 2) * 2, sticky="e", padx=4, pady=2)
            ttk.Label(panel, textvariable=self.v[k], font=("Segoe UI", 10, "bold")).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=4)

        self.texto = tk.Text(marco, height=18, bg="#111", fg="#ddd", font=("Consolas", 9), wrap="word")
        self.texto.pack(fill="both", expand=True, pady=(8, 0))
        aviso = ("Mientras corre, no muevas el mouse ni toques la ventana de Chromium (el scroll usa el mouse real).")
        ttk.Label(marco, text=aviso, foreground="#b71c1c").pack(anchor="w", pady=(4, 0))
        self.refrescar()

    # --- control -----------------------------------------------------------------------------
    def alternar(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.detener()
        else:
            self.iniciar()

    def iniciar(self) -> None:
        orden = [sys.executable, "-u", *MODOS[self.modo.get()]]
        if "cargar_historico" in orden[2]:
            orden += ["--grupo", self.grupo.get(), "--minutos", self.minutos.get()]
        entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(orden, cwd=RAIZ, env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
        threading.Thread(target=self._leer, daemon=True).start()
        self.inicio = datetime.now()
        self.texto.delete("1.0", "end")
        self.btn.config(text="DETENER", bg="#c62828")
        self.estado.set("Corriendo...")
        self.v["fase"].set("Abriendo WhatsApp Web")

    def detener(self) -> None:
        if self.proc and self.proc.poll() is None:
            # taskkill /T cierra también el navegador que abrió el proceso
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, creationflags=0x08000000)
        self.estado.set("Detenido por ti")

    def _leer(self) -> None:
        for linea in self.proc.stdout:  # type: ignore[union-attr]
            self.cola.put(linea.rstrip())
        self.cola.put("\0FIN")

    # --- refresco ----------------------------------------------------------------------------
    def _interpretar(self, linea: str) -> None:
        if m := re.search(r"Ronda (\d+) - fase (\d)", linea):
            self.v["fase"].set(f"Ronda {m[1]}: " + ("subiendo el chat" if m[2] == "1" else "leyendo lo cargado"))
        if m := re.search(r"tandas: (\d+) \| burbujas: (\d+)", linea):
            self.v["tandas"].set(f"{m[1]}  (burbujas pintadas: {m[2]})")
        if "descargas:" in linea or "Descargas:" in linea:
            self.v["fotos"].set(linea.split("descargas:")[-1].split("Descargas:")[-1].strip()[:70])
        if "Histórico completo" in linea:
            self.v["fase"].set("Histórico completo")

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
        if self.inicio and self.proc and self.proc.poll() is None:
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
            n = sum(1 for p in RAIZ_EVIDENCIAS.rglob("*") if p.is_file() and p.name != ".gitkeep")
            if self.v["fotos"].get() in ("-", ""):
                self.v["fotos"].set(f"{n} archivos en data/Evidencias_WhatsApp")
        except Exception:  # noqa: BLE001 - el índice puede estar bloqueado un instante
            pass


if __name__ == "__main__":
    raiz = tk.Tk()
    Interfaz(raiz)
    raiz.mainloop()
