#!/usr/bin/env python3
"""
Interfaz moderna (CustomTkinter): elige grupo, modo y tiempo (hoy y N días antes), un botón INICIAR/DETENER y tarjetas que
muestran qué está haciendo (grupo, fase, tandas, cruce en vivo, descargas) más el registro en vivo con colores.

Uso:  python scripts/interfaz.py     (o doble clic en Iniciar_interfaz.bat)

No contiene lógica propia: lanza scripts/cargar_historico.py, scripts/vigilante.py, etc. como proceso aparte y lee lo que
ese proceso va escribiendo. El detalle completo queda en logs/detalle.log.
"""
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    sys.exit("Falta la librería de la interfaz. Ejecuta:  pip install -r requirements.txt")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.nucleo.config import load_config  # noqa: E402
from src.nucleo.rutas import R  # noqa: E402
from src.nucleo import eventos  # noqa: E402
from src.bot.descargas import RAIZ_EVIDENCIAS  # noqa: E402
from src.datos.estado_descargas import resumen as resumen_descargas  # noqa: E402
from src.datos.historico import RUTA_INDICE  # noqa: E402
from src.datos.indice import Indice  # noqa: E402
from src.nucleo.verificador import hay_errores, informe, verificar  # noqa: E402

TODOS = "(TODOS los grupos, uno tras otro)"
# modo -> (script, opciones fijas)
MODOS = {
    "Subir + cruzar + descargar lo que cruza": ("scripts/cargar_historico.py", ["--descargar"]),
    "Subir + cruzar + descargar TODO (cruce o no)": ("scripts/cargar_historico.py", ["--descargar", "--todo"]),
    "Solo subir e indexar (sin descargar)": ("scripts/cargar_historico.py", []),
    "Solo actualizar lo nuevo (rápido, todos los grupos)": ("scripts/actualizar.py", []),
    "VIGILANTE: bajar todo lo que llega, todo el día": ("scripts/vigilante.py", []),
}

MODO_CORTO = {"VIGILANTE": "VIGILANTE", "Solo actualizar": "ACTUALIZAR", "Solo subir": "SUBIR E INDEXAR", "descargar TODO": "HISTÓRICO (todo)", "descargar lo que cruza": "HISTÓRICO (lo que cruza)"}


def modo_corto(modo: str) -> str:
    return next((v for k, v in MODO_CORTO.items() if k in modo), modo)


# Paleta (claro, oscuro)
FONDO = ("#f1f5f9", "#0b1220")
TARJETA = ("#ffffff", "#162033")
BORDE = ("#e2e8f0", "#243049")
TEXTO = ("#0f172a", "#e5edf8")
TENUE = ("#64748b", "#8fa1bd")
VERDE, VERDE_H = "#16a34a", "#15803d"
ROJO, ROJO_H = "#dc2626", "#b91c1c"
AZUL, AZUL_H = "#2563eb", "#1d4ed8"
AMBAR = "#d97706"
FUENTE = "Segoe UI"


class Interfaz:
    def __init__(self, raiz: ctk.CTk):
        self.cfg = load_config()
        self.r = raiz
        self.proc: subprocess.Popen | None = None
        self.cola: queue.Queue[str] = queue.Queue()
        self.inicio: datetime | None = None
        self.parar = False
        raiz.title("Evidencias WhatsApp · Incidencias")
        raiz.geometry("1420x860")
        raiz.minsize(1240, 700)
        raiz.configure(fg_color=FONDO)
        raiz.grid_columnconfigure(1, weight=1)
        raiz.grid_rowconfigure(0, weight=1)
        self._lateral(raiz)
        self._principal(raiz)
        self.refrescar()

    # --- construcción de la interfaz ---------------------------------------------------------------
    def _lateral(self, raiz) -> None:
        lat = ctk.CTkFrame(raiz, width=236, corner_radius=0, fg_color=TARJETA, border_width=0)
        lat.grid(row=0, column=0, sticky="nsew")
        lat.grid_propagate(False)
        ctk.CTkLabel(lat, text="📷  Evidencias", font=(FUENTE, 22, "bold"), text_color=TEXTO).pack(anchor="w", padx=22, pady=(24, 0))
        ctk.CTkLabel(lat, text="WhatsApp → Incidencias de Henry", font=(FUENTE, 12), text_color=TENUE).pack(anchor="w", padx=22, pady=(0, 18))

        def seccion(titulo):
            ctk.CTkLabel(lat, text=titulo.upper(), font=(FUENTE, 10, "bold"), text_color=TENUE).pack(anchor="w", padx=22, pady=(14, 4))

        def boton(texto, cmd, color=None):
            ctk.CTkButton(lat, text=texto, command=cmd, anchor="w", height=36, corner_radius=8, font=(FUENTE, 13),
                          fg_color=color or "transparent", hover_color=BORDE, text_color=TEXTO).pack(fill="x", padx=12, pady=1)

        seccion("Control")
        boton("✔  Verificar entorno", self.verificar_entorno)
        boton("📈  Estado de descargas", self.ver_estado_descargas)
        seccion("Resultados")
        boton("📊  Abrir Excel de incidencias", self.abrir_excel_vivo)
        boton("🧾  Generar reporte Excel", self.generar_reporte)
        boton("🗂  Abrir evidencias", lambda: os.startfile(RAIZ_EVIDENCIAS))
        boton("📜  Abrir logs (última corrida)", self.abrir_logs)
        boton("🗒  Abrir carpeta de incidencias", lambda: os.startfile(R.incidencias))
        boton("➕  Cargar incidencias nuevas…", self.cargar_incidencias, color=AZUL)
        boton("📥  Pasar lo nuevo al histórico", self.consolidar_incidencias)
        seccion("Mantenimiento")
        boton("🧹  Limpiar y ordenar", self.limpiar)
        boton("⬇  Actualizar desde GitHub", self.actualizar_proyecto)
        boton("📦  Exportar traspaso a otro PC", self.exportar_traspaso)
        boton("📥  Importar traspaso", self.importar_traspaso)

        pie = ctk.CTkFrame(lat, fg_color="transparent")
        pie.pack(side="bottom", fill="x", padx=18, pady=16)
        ctk.CTkLabel(pie, text="⚠ Mientras corre un histórico no muevas el mouse.", font=(FUENTE, 11), text_color=AMBAR,
                     wraplength=190, justify="left").pack(anchor="w", pady=(10, 0))

    def _principal(self, raiz) -> None:
        cuerpo = ctk.CTkFrame(raiz, fg_color="transparent")
        cuerpo.grid(row=0, column=1, sticky="nsew", padx=20, pady=16)
        cuerpo.grid_columnconfigure(0, weight=0, minsize=470)
        cuerpo.grid_columnconfigure(1, weight=1)
        cuerpo.grid_rowconfigure(1, weight=1)

        # encabezado: título, estado y tema claro/oscuro
        enc = ctk.CTkFrame(cuerpo, fg_color="transparent")
        enc.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        enc.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(enc, text="Panel de control", font=(FUENTE, 26, "bold"), text_color=TEXTO).grid(row=0, column=0, sticky="w")
        self.tema = ctk.CTkSegmentedButton(enc, values=["☀  Claro", "🌙  Oscuro"], command=self._cambiar_tema, font=(FUENTE, 12), height=30)
        self.tema.set("🌙  Oscuro")
        self.tema.grid(row=0, column=1, sticky="e", padx=(0, 14))
        self.estado = ctk.StringVar(value="Detenido")
        self.pastilla = ctk.CTkLabel(enc, textvariable=self.estado, font=(FUENTE, 13, "bold"), text_color="white", fg_color="#64748b",
                                     corner_radius=14, height=30, padx=16)
        self.pastilla.grid(row=0, column=2, sticky="e")
        self.aviso_modo = ctk.CTkLabel(enc, text="", font=(FUENTE, 13, "bold"), text_color="white", fg_color=VERDE, corner_radius=8, height=30,
                                       anchor="w", padx=14)      # franja que dice qué se está ejecutando (se muestra solo mientras corre)

        # columna izquierda: configuración + tarjetas
        izq = ctk.CTkScrollableFrame(cuerpo, fg_color="transparent", width=450)
        izq.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        izq.grid_columnconfigure((0, 1), weight=1, uniform="c")
        cfg = ctk.CTkFrame(izq, fg_color=TARJETA, corner_radius=14, border_width=1, border_color=BORDE)
        cfg.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        cfg.grid_columnconfigure((0, 1, 2), weight=1, uniform="f")

        def etiqueta(padre, titulo):
            ctk.CTkLabel(padre, text=titulo, font=(FUENTE, 10, "bold"), text_color=TENUE).pack(anchor="w")

        def bloque(fila, col, span=1):
            f = ctk.CTkFrame(cfg, fg_color="transparent")
            f.grid(row=fila, column=col, columnspan=span, sticky="ew", padx=14, pady=(10, 2))
            return f

        self.grupo = ctk.StringVar(value=self.cfg.whatsapp.grupos[0])
        f = bloque(0, 0, 3)
        etiqueta(f, "GRUPO")
        ctk.CTkOptionMenu(f, variable=self.grupo, values=[*self.cfg.whatsapp.grupos, TODOS], height=34, dynamic_resizing=False, width=420,
                          font=(FUENTE, 13), fg_color=AZUL, button_color=AZUL_H).pack(fill="x", pady=(3, 0))
        self.modo = ctk.StringVar(value=list(MODOS)[0])
        f = bloque(1, 0, 3)
        etiqueta(f, "MODO")
        ctk.CTkOptionMenu(f, variable=self.modo, values=list(MODOS), height=34, dynamic_resizing=False, width=420, font=(FUENTE, 13),
                          fg_color=AZUL, button_color=AZUL_H).pack(fill="x", pady=(3, 0))
        self.dias = ctk.StringVar(value="4")
        self.desde = ctk.StringVar(value="")
        self.minutos = ctk.StringVar(value="100")
        self.al_dia = ctk.BooleanVar(value=True)
        for col, (titulo, var) in enumerate((("HOY Y … DÍAS ANTES", self.dias), ("O DESDE (AAAA-MM-DD)", self.desde), ("TOPE POR GRUPO (MIN)", self.minutos))):
            f = bloque(2, col)
            etiqueta(f, titulo)
            ctk.CTkEntry(f, textvariable=var, height=32, font=(FUENTE, 13)).pack(fill="x", pady=(3, 0))
        ctk.CTkCheckBox(cfg, text="Vigilante: si hay hueco, subir con el mouse unos minutos", variable=self.al_dia, font=(FUENTE, 12),
                        text_color=TEXTO).grid(row=3, column=0, columnspan=3, sticky="w", padx=16, pady=(10, 4))
        self.btn = ctk.CTkButton(cfg, text="▶  INICIAR", command=self.alternar, height=48, corner_radius=12, font=(FUENTE, 17, "bold"),
                                 fg_color=VERDE, hover_color=VERDE_H)
        self.btn.grid(row=4, column=0, columnspan=3, sticky="ew", padx=14, pady=(6, 14))

        self.v = {k: ctk.StringVar(value="-") for k in ("grupo", "fase", "tandas", "tiempo", "indice", "antiguo", "cruce", "fotos")}
        tarjetas = [("grupo", "Grupo actual", 0, 0, 1, 84), ("fase", "Fase", 0, 1, 1, 84), ("tandas", "Tandas cargadas", 1, 0, 1, 70), ("tiempo", "Tiempo corrido", 1, 1, 1, 70),
                    ("indice", "Mensajes en el índice", 2, 0, 1, 70), ("antiguo", "Mensaje más antiguo", 2, 1, 1, 70),
                    ("fotos", "Descargas", 3, 0, 2, 96), ("cruce", "Cruce en vivo", 4, 0, 2, 112)]
        rejilla = ctk.CTkFrame(izq, fg_color="transparent")
        rejilla.grid(row=1, column=0, columnspan=2, sticky="nsew")
        rejilla.grid_columnconfigure((0, 1), weight=1, uniform="k")
        for clave, titulo, fila, col, span, alto in tarjetas:
            self._tarjeta(rejilla, fila, col, titulo, self.v[clave], span, alto=alto)
        self.barra = ctk.CTkProgressBar(izq, mode="indeterminate", height=6, progress_color=VERDE)
        self.barra.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.barra.set(0)

        # columna derecha: registro en vivo, alto y ancho
        reg = ctk.CTkFrame(cuerpo, fg_color=TARJETA, corner_radius=14, border_width=1, border_color=BORDE)
        reg.grid(row=1, column=1, sticky="nsew")
        reg.grid_columnconfigure(0, weight=1)
        reg.grid_rowconfigure(1, weight=1)
        cab = ctk.CTkFrame(reg, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        ctk.CTkLabel(cab, text="REGISTRO EN VIVO", font=(FUENTE, 11, "bold"), text_color=TENUE).pack(side="left")
        ctk.CTkButton(cab, text="Limpiar vista", width=96, height=24, font=(FUENTE, 11), fg_color="transparent", border_width=1,
                      border_color=BORDE, text_color=TEXTO, hover_color=BORDE, command=lambda: self.texto.delete("1.0", "end")).pack(side="right")
        self.texto = ctk.CTkTextbox(reg, font=("Consolas", 12), fg_color=("#f8fafc", "#0b1220"), text_color=("#0f172a", "#cbd5e1"), corner_radius=10, wrap="word")
        self.texto.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self._colores_log()

    def _colores_log(self) -> None:
        """Colores del registro según el tema (el texto de un tk.Text no admite pares claro/oscuro)."""
        oscuro = ctk.get_appearance_mode() == "Dark"
        paleta = ({"error": "#f87171", "aviso": "#fbbf24", "ok": "#4ade80", "info": "#38bdf8", "titulo": "#a5b4fc"} if oscuro else
                  {"error": "#b91c1c", "aviso": "#b45309", "ok": "#15803d", "info": "#0369a1", "titulo": "#4338ca"})
        t = self.texto._textbox
        for tag, color in paleta.items():
            t.tag_config(tag, foreground=color)
        t.tag_config("titulo", font=("Consolas", 12, "bold"))

    def _tarjeta(self, padre, fila, col, titulo, var, span, alto=92) -> None:
        f = ctk.CTkFrame(padre, fg_color=TARJETA, corner_radius=12, border_width=1, border_color=BORDE, height=alto)
        f.grid(row=fila, column=col, columnspan=span, sticky="nsew", padx=5, pady=5)
        f.grid_propagate(False)
        ctk.CTkLabel(f, text=titulo.upper(), font=(FUENTE, 10, "bold"), text_color=TENUE).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(f, textvariable=var, font=(FUENTE, 14, "bold"), text_color=TEXTO, anchor="w", justify="left",
                     wraplength=190 * span + 30 * (span - 1)).pack(anchor="w", padx=14, pady=(2, 8), fill="x")

    def _cambiar_tema(self, valor: str = "") -> None:
        ctk.set_appearance_mode("dark" if "Oscuro" in (valor or self.tema.get()) else "light")
        self._colores_log()
        self._colores_log()

    # --- control -----------------------------------------------------------------------------
    def _estado(self, texto: str, color: str = "#64748b") -> None:
        self.estado.set(texto)
        self.pastilla.configure(fg_color=color)

    def alternar(self) -> None:
        if self._corriendo():
            self.detener()
        else:
            self.iniciar()

    def _corriendo(self) -> bool:
        return self.btn.cget("text").endswith("DETENER")

    def _mostrar(self, texto: str) -> None:
        self.texto.delete("1.0", "end")
        self._escribir(texto)

    def _escribir(self, texto: str) -> None:
        t = self.texto._textbox
        for linea in texto.splitlines():
            up = linea.upper()
            tag = ("error" if ("ERROR" in up or "TRACEBACK" in up or "FALLÓ" in up) else "aviso" if ("WARNING" in up or "AVISO" in up or "OMITIDO" in up)
                   else "ok" if ("-> OK" in up or "[ OK" in up or "LISTO" in up) else "titulo" if ("#####" in linea or "=====" in linea)
                   else "info" if any(k in up for k in ("CRUCE EN VIVO", "DESCARGA", "EXCEL EN VIVO", "VUELTA", "IDENTIFICADA", "TANDA")) else None)
            t.insert("end", linea + "\n", tag)
        t.see("end")

    def verificar_entorno(self) -> bool:
        """Corre las revisiones previas y las muestra en el panel. True si se puede correr."""
        self._estado("Verificando…", AZUL)
        self.r.update_idletasks()
        res = verificar()
        self._mostrar(informe(res))
        ok = not hay_errores(res)
        self._estado("Listo para correr" if ok else "Hay errores: lee «QUÉ HACER»", VERDE if ok else ROJO)
        return ok

    def ver_estado_descargas(self) -> None:
        self._mostrar(resumen_descargas())

    def abrir_excel_vivo(self) -> None:
        """Abre el ÚNICO Excel de incidencias (hojas Histórico y Nuevas, con el estado del cruce que escribe el bot)."""
        ruta = Path(self.cfg.excel.ruta_archivo)
        ruta = ruta if ruta.is_absolute() else R.raiz / ruta
        if ruta.exists():
            os.startfile(ruta)
        else:
            self._estado("Aún no hay Excel de incidencias: importa un traspaso o crea la base", AMBAR)

    def abrir_logs(self) -> None:
        """Abre la carpeta de la corrida más reciente (o logs/ si todavía no hay ninguna)."""
        ultima = eventos.ultima_corrida(R.logs)
        os.startfile(ultima or R.logs)

    def incorporar_incidencias(self) -> None:
        """Mezcla en la base lo que hayas dejado en data/Incidencias/nuevas/ (el vigilante también lo hace solo)."""
        if self._corriendo():
            messagebox.showwarning("Incorporar incidencias", "Detén primero el bot (botón DETENER) y vuelve a intentar; el vigilante ya incorpora solo.")
            return
        self._estado("Incorporando incidencias…", AZUL)
        self.r.update_idletasks()
        p = self._ejecutar(["scripts/incidencias.py", "incorporar"])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Incidencias incorporadas" if p.returncode == 0 else "Error al incorporar incidencias", VERDE if p.returncode == 0 else ROJO)

    def cargar_incidencias(self) -> None:
        """LA forma fácil de cargar incidencias: elige uno o varios Excel y listo (se copian a data/Incidencias/nuevas/ y se incorporan a la base)."""
        archivos = filedialog.askopenfilenames(title="Elige el/los Excel con las incidencias nuevas", filetypes=[("Excel", "*.xlsx")])
        if not archivos:
            return
        self._estado("Cargando incidencias…", AZUL)
        self.r.update_idletasks()
        if self._corriendo():     # el vigilante ya incorpora lo que encuentre en nuevas/: solo se dejan los archivos
            from src.excel.incidencias import cargar_archivos

            r = cargar_archivos(R.incidencias, [Path(a) for a in archivos], incorporar=False)
            self._mostrar(f"Archivos dejados en data/Incidencias/nuevas/: {r['copiados']}\nEl vigilante los incorpora a la base en su próxima vuelta.")
            self._estado("Archivos dejados: el vigilante los incorpora solo", VERDE)
            return
        p = self._ejecutar(["scripts/incidencias.py", "cargar", *archivos])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Incidencias cargadas" if p.returncode == 0 else "Error al cargar incidencias", VERDE if p.returncode == 0 else ROJO)

    def consolidar_incidencias(self) -> None:
        """Pasa lo de la hoja «Nuevas» a «Histórico» cuando ya se procesó."""
        if self._corriendo():
            messagebox.showwarning("Pasar al histórico", "Detén primero el bot (botón DETENER) y vuelve a intentar.")
            return
        if not messagebox.askyesno("Pasar al histórico", "Esto mueve todas las incidencias de la hoja «Nuevas» a «Histórico» (se deja copia de la base).\n\n¿Continuar?"):
            return
        p = self._ejecutar(["scripts/incidencias.py", "consolidar"])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Hecho" if p.returncode == 0 else "Error al pasar al histórico", VERDE if p.returncode == 0 else ROJO)

    def _ejecutar(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=0x08000000)

    def limpiar(self) -> None:
        """Muestra qué se limpiaría (simulación), pregunta y aplica. Nunca borra evidencias, índice, sesión ni Excel."""
        if self._corriendo():
            messagebox.showwarning("Limpiar", "Detén primero el bot (botón DETENER) y vuelve a intentar.")
            return
        p = self._ejecutar(["scripts/limpiar.py", "--simular"])
        self._mostrar((p.stdout + p.stderr).strip())
        if p.returncode != 0:
            return
        if not messagebox.askyesno("Limpiar y ordenar", "Esto es lo que se hará (ver el registro).\nNada de evidencias, índice, sesión ni Excel se borra: "
                                   "lo viejo se archiva.\n\n¿Aplicar la limpieza?"):
            return
        reorg = messagebox.askyesno("Limpiar y ordenar", "¿También reorganizar lo ya descargado (renombrar y mover a las carpetas con aviso/incidencia)?")
        self._estado("Limpiando…", AZUL)
        self.r.update_idletasks()
        p = self._ejecutar(["scripts/limpiar.py", *(["--reorganizar"] if reorg else [])])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Limpieza terminada" if p.returncode == 0 else "La limpieza tuvo errores: lee el registro", VERDE if p.returncode == 0 else ROJO)

    def actualizar_proyecto(self) -> None:
        """Baja la versión nueva de GitHub con Actualizar_proyecto.bat (en otra ventana). Cierra la interfaz porque el código cambia."""
        if self._corriendo():
            messagebox.showwarning("Actualizar", "Detén primero el bot (botón DETENER) y vuelve a intentar.")
            return
        if not messagebox.askyesno("Actualizar desde GitHub", "Se cerrarán los procesos viejos, se bajará la versión nueva y se regenerará "
                                   "config.yaml (queda copia como config.yaml.respaldo).\nTus datos, evidencias y la sesión de WhatsApp NO se tocan.\n\n"
                                   "La interfaz se cerrará; vuelve a abrirla con Iniciar_interfaz.bat al terminar.\n\n¿Continuar?"):
            return
        subprocess.Popen(["cmd", "/c", "start", "Actualizar proyecto", str(RAIZ / "Actualizar_proyecto.bat")], cwd=RAIZ)
        self.r.after(500, self.r.destroy)

    def exportar_traspaso(self) -> None:
        """Crea un .zip con índice, evidencias y estado para continuar en otro PC (data/Traspasos/)."""
        self._estado("Creando traspaso…", AZUL)
        self.r.update_idletasks()
        p = self._ejecutar(["scripts/traspaso.py", "exportar"])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Traspaso listo (data/Traspasos)" if p.returncode == 0 else "Error al crear el traspaso", VERDE if p.returncode == 0 else ROJO)
        if p.returncode == 0:
            os.startfile(R.traspasos)

    def importar_traspaso(self) -> None:
        """Elige un .zip de traspaso y lo mezcla en este PC (índice, evidencias y rutas); respalda lo que había."""
        if self._corriendo():
            messagebox.showwarning("Importar traspaso", "Detén primero el bot (botón DETENER) y vuelve a intentar.")
            return
        ruta = filedialog.askopenfilename(title="Elige el .zip de traspaso", filetypes=[("Traspaso", "*.zip")])
        if not ruta:
            return
        con_excel = messagebox.askyesno("Importar traspaso", "¿Reemplazar también el Excel de incidencias por el del traspaso?\n(se deja copia del actual)")
        self._estado("Importando traspaso…", AZUL)
        self.r.update_idletasks()
        p = self._ejecutar(["scripts/traspaso.py", "importar", ruta, *(["--excel"] if con_excel else [])])
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Traspaso importado" if p.returncode == 0 else "Error al importar el traspaso", VERDE if p.returncode == 0 else ROJO)

    def generar_reporte(self) -> None:
        """Genera el reporte Excel con formato a partir de lo indexado y descargado (no abre WhatsApp)."""
        orden = ["scripts/generar_reporte.py", "--todos"]
        orden += ["--desde", self.desde.get().strip()] if self.desde.get().strip() else ["--dias", self.dias.get().strip() or "4"]
        self._estado("Generando reporte…", AZUL)
        self.r.update_idletasks()
        p = self._ejecutar(orden)
        self._mostrar((p.stdout + p.stderr).strip())
        self._estado("Reporte listo (data/Reportes/historial)" if p.returncode == 0 else "Error al generar el reporte", VERDE if p.returncode == 0 else ROJO)
        if p.returncode == 0:
            os.startfile(R.reportes_historial)

    def armar_comando(self) -> list[str]:
        script, fijas = MODOS[self.modo.get()]
        orden = [sys.executable, "-u", script, *fijas]
        if "vigilante" in script:
            orden += ["--todos"] if self.grupo.get() == TODOS else ["--grupo", self.grupo.get()]
            if not self.al_dia.get():
                orden += ["--sin-mouse"]
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
        self.btn.configure(text="■  DETENER", fg_color=ROJO, hover_color=ROJO_H)
        self._estado("Corriendo…", VERDE)
        self._anunciar_modo(True)
        self.barra.start()
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

    def _usa_mouse(self) -> bool:
        modo = self.modo.get()
        return ("cargar_historico" in MODOS[modo][0]) or ("vigilante" in MODOS[modo][0] and self.al_dia.get())

    def _franja_pantalla(self, activo: bool) -> None:
        """Franja siempre visible sobre TODAS las ventanas (también sobre el navegador del bot); el mouse la atraviesa."""
        if not activo:
            if getattr(self, "franja", None) is not None:
                try:
                    self.franja.destroy()
                except Exception:
                    pass
                self.franja = None
            return
        try:
            import tkinter as tk
            f = tk.Toplevel(self.r)
            f.overrideredirect(True)
            f.attributes("-topmost", True)
            f.attributes("-alpha", 0.9)
            f.configure(bg="#15803d")
            self.franja_txt = tk.StringVar()
            tk.Label(f, textvariable=self.franja_txt, bg="#15803d", fg="white", font=("Segoe UI", 12, "bold"), padx=18, pady=6).pack()
            f.update_idletasks()
            ancho = max(f.winfo_reqwidth(), 520)
            f.geometry(f"{ancho}x{f.winfo_reqheight()}+{(f.winfo_screenwidth() - ancho) // 2}+0")
            self.franja = f
            self._actualizar_franja()
            try:   # clic «a través»: no tapa nada ni recibe clics
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(f.winfo_id()) or f.winfo_id()
                estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo | 0x80000 | 0x20 | 0x80)
            except Exception:
                pass
        except Exception:
            self.franja = None

    def _actualizar_franja(self) -> None:
        f = getattr(self, "franja", None)
        if f is None:
            return
        grupo = self.v["grupo"].get()
        grupo = "" if grupo in ("", "-") else f" · {grupo}"
        mouse = "  ·  NO USES EL MOUSE" if self._usa_mouse() else ""
        self.franja_txt.set(f"🤖 BOT ACTIVO — {modo_corto(self.modo.get())}{grupo}{mouse}")
        color = "#b91c1c" if mouse else "#15803d"
        f.configure(bg=color)
        for w in f.winfo_children():
            w.configure(bg=color)

    def _anunciar_modo(self, activo: bool) -> None:
        """Franja en la ventana, título y franja sobre toda la pantalla con el modo y el grupo que se están ejecutando."""
        self._franja_pantalla(activo)
        if activo:
            texto = f"●  EN MARCHA — modo {modo_corto(self.modo.get())} · {'TODOS los grupos' if self.grupo.get() == TODOS else self.grupo.get()}"
            self.aviso_modo.configure(text=texto, fg_color=VERDE)
            self.aviso_modo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
            self.r.title(f"● {modo_corto(self.modo.get())} — Evidencias WhatsApp · Incidencias")
        else:
            self.aviso_modo.grid_remove()
            self.r.title("Evidencias WhatsApp · Incidencias")

    def detener(self) -> None:
        self.parar = True
        if self.proc and self.proc.poll() is None:
            # taskkill /T cierra también el navegador que abrió el proceso
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, creationflags=0x08000000)
        self._estado("Detenido por ti", "#64748b")
        self._anunciar_modo(False)

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
        if "IDENTIFICADA DESPUÉS" in linea or "REORGANIZADA" in linea:
            self.v["cruce"].set(linea.split(":", 3)[-1].strip()[:160])
        if "Histórico completo" in linea:
            self.v["fase"].set("Histórico completo: pasando a descargar")

    def refrescar(self) -> None:
        try:
            while True:
                linea = self.cola.get_nowait()
                if linea == "\0FIN":
                    cod = self.proc.returncode if self.proc else None
                    self.btn.configure(text="▶  INICIAR", fg_color=VERDE, hover_color=VERDE_H)
                    self.barra.stop()
                    self.barra.set(0)
                    self._anunciar_modo(False)
                    if self.estado.get() != "Detenido por ti":
                        self._estado("Terminado" if cod == 0 else f"Terminó con código {cod}", VERDE if cod == 0 else ROJO)
                    continue
                self._interpretar(linea)
                self._escribir(linea)
        except queue.Empty:
            pass
        if self.inicio and self._corriendo():
            self.v["tiempo"].set(str(datetime.now() - self.inicio).split(".")[0])
            self._actualizar_franja()
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
                n = sum(1 for p in RAIZ_EVIDENCIAS.rglob("*") if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4", ".mov"))
                self.v["fotos"].set(f"{n} archivos en data/Evidencias_WhatsApp")
        except Exception:  # noqa: BLE001 - el índice puede estar bloqueado un instante
            pass


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    raiz = ctk.CTk()
    Interfaz(raiz)
    raiz.mainloop()
