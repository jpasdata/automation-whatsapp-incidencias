"""
Pruebas de la interfaz (CustomTkinter): cada botón se ACTIVA de verdad y se comprueba lo que debe pasar. Solo se simula lo externo
(abrir archivos, ventanas de confirmación y procesos largos). Si el PC no tiene pantalla/tkinter, se omiten.
"""
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ctk = pytest.importorskip("customtkinter")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import interfaz as ui_mod  # noqa: E402
from src.verificador import ERROR, OK, Resultado  # noqa: E402


@pytest.fixture(scope="module")
def raiz_tk():
    """Una sola ventana raíz para todo el módulo (crear y destruir muchas raíces de Tk falla de forma intermitente)."""
    try:
        raiz = ctk.CTk()
    except Exception as e:  # noqa: BLE001 - sin pantalla
        pytest.skip(f"sin pantalla: {e}")
    raiz.withdraw()
    yield raiz
    try:
        raiz.destroy()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def ui(raiz_tk):
    top = ctk.CTkToplevel(raiz_tk)
    top.withdraw()
    app = ui_mod.Interfaz(top)
    yield app
    try:
        top.destroy()
    except Exception:  # noqa: BLE001
        pass


def _cfg():
    from src.config import load_config

    return load_config()


def _esperar(cond, seg=15):
    fin = time.time() + seg
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.1)
    return False


def _texto(app) -> str:
    return app.texto.get("1.0", "end")


def test_arranca_con_todos_los_botones(ui):
    def botones(w):
        out = []
        for c in w.winfo_children():
            if c.winfo_class() == "Button" or c.__class__.__name__ == "CTkButton":
                out.append(c.cget("text"))
            out += botones(c)
        return out

    textos = " | ".join(botones(ui.r))
    for esperado in ("INICIAR", "Verificar entorno", "Estado de descargas", "Abrir Excel en vivo", "Generar reporte Excel", "Abrir evidencias",
                     "Abrir logs", "Limpiar y ordenar", "Actualizar desde GitHub", "Exportar traspaso a otro PC", "Importar traspaso", "Limpiar vista"):
        assert esperado in textos, esperado


def test_verificar_entorno_ok_y_con_errores(ui, monkeypatch):
    monkeypatch.setattr(ui_mod, "verificar", lambda: [Resultado(OK, "Python", "3.14")])
    assert ui.verificar_entorno() is True and ui.estado.get() == "Listo para correr" and "LISTO PARA CORRER" in _texto(ui)
    monkeypatch.setattr(ui_mod, "verificar", lambda: [Resultado(ERROR, "Excel", "no existe", "cópialo a data/")])
    assert ui.verificar_entorno() is False and "Hay errores" in ui.estado.get() and "QUÉ HACER: cópialo" in _texto(ui)


def test_estado_de_descargas_muestra_el_resumen(ui, monkeypatch):
    monkeypatch.setattr(ui_mod, "resumen_descargas", lambda: "=== ESTADO DE DESCARGAS ===\nTOTAL: 3 fotos, 1 videos.")
    ui.ver_estado_descargas()
    assert "TOTAL: 3 fotos, 1 videos." in _texto(ui)


def test_abrir_excel_en_vivo_existe_y_no_existe(ui, monkeypatch, tmp_path):
    abiertos = []
    monkeypatch.setattr(ui_mod.os, "startfile", lambda r: abiertos.append(Path(r)), raising=False)
    monkeypatch.setattr(ui_mod, "RAIZ", tmp_path)
    ui.abrir_excel_vivo()
    assert abiertos == [] and "Aún no hay Excel en vivo" in ui.estado.get()
    (tmp_path / "data" / "Reportes").mkdir(parents=True)
    f = tmp_path / "data" / "Reportes" / "RESULTADO_CREACION_INCIDENCIAS_CRUZADO.xlsx"
    f.write_bytes(b"x")
    ui.abrir_excel_vivo()
    assert abiertos == [f]


def test_generar_reporte_ok_y_error(ui, monkeypatch):
    abiertos, llamadas = [], []
    monkeypatch.setattr(ui_mod.os, "startfile", lambda r: abiertos.append(r), raising=False)
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "Reporte: data\\Reportes\\x.xlsx", ""))[1])
    ui.dias.set("7")
    ui.generar_reporte()
    assert llamadas[0][:2] == ["scripts/generar_reporte.py", "--todos"] and "--dias" in llamadas[0] and "7" in llamadas[0]
    assert "Reporte listo" in ui.estado.get() and abiertos
    ui.desde.set("2026-10-01")
    ui.generar_reporte()
    assert "--desde" in llamadas[1] and "2026-10-01" in llamadas[1]
    monkeypatch.setattr(ui, "_ejecutar", lambda args: subprocess.CompletedProcess(args, 1, "", "falló"))
    ui.generar_reporte()
    assert "Error al generar el reporte" in ui.estado.get()


def test_limpiar_pide_confirmacion_y_respeta_la_respuesta(ui, monkeypatch):
    llamadas = []
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "=== LIMPIEZA ===", ""))[1])
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: False)
    ui.limpiar()
    assert llamadas == [["scripts/limpiar.py", "--simular"]]            # solo simuló: el usuario dijo que no
    respuestas = iter([True, True])                                      # aplicar = sí, reorganizar = sí
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: next(respuestas))
    llamadas.clear()
    ui.limpiar()
    assert llamadas == [["scripts/limpiar.py", "--simular"], ["scripts/limpiar.py", "--reorganizar"]]
    assert ui.estado.get() == "Limpieza terminada"


def test_limpiar_y_actualizar_se_niegan_si_el_bot_corre(ui, monkeypatch):
    avisos = []
    monkeypatch.setattr(ui_mod.messagebox, "showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(ui, "_ejecutar", lambda args: pytest.fail("no debe ejecutar nada con el bot corriendo"))
    ui.btn.configure(text="■  DETENER")
    ui.limpiar()
    ui.actualizar_proyecto()
    assert len(avisos) == 2


def test_actualizar_desde_github_confirma_lanza_el_bat_y_cierra(ui, monkeypatch):
    lanzados = []
    monkeypatch.setattr(ui_mod.subprocess, "Popen", lambda cmd, **k: lanzados.append(cmd))
    cerrado = []
    monkeypatch.setattr(ui.r, "after", lambda ms, fn=None, *a: cerrado.append(fn))
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: False)
    ui.actualizar_proyecto()
    assert lanzados == [] and cerrado == []
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: True)
    ui.actualizar_proyecto()
    assert lanzados and lanzados[0][:2] == ["cmd", "/c"] and lanzados[0][-1].endswith("Actualizar_proyecto.bat") and cerrado


def test_armar_comando_de_cada_modo(ui):
    grupo = ui.cfg.whatsapp.grupos[0]
    ui.grupo.set(grupo)
    ui.minutos.set("60")
    ui.dias.set("4")
    ui.modo.set("Subir + cruzar + descargar lo que cruza")
    c = ui.armar_comando()
    assert "scripts/cargar_historico.py" in c and "--descargar" in c and "--todo" not in c and c[c.index("--grupo") + 1] == grupo
    assert c[c.index("--minutos") + 1] == "60" and c[c.index("--dias") + 1] == "4"
    ui.modo.set("Subir + cruzar + descargar TODO (cruce o no)")
    assert "--todo" in ui.armar_comando()
    ui.modo.set("Solo subir e indexar (sin descargar)")
    assert "--descargar" not in ui.armar_comando()
    ui.modo.set("Solo actualizar lo nuevo (rápido, todos los grupos)")
    assert "scripts/actualizar.py" in ui.armar_comando()
    ui.grupo.set(ui_mod.TODOS)
    ui.desde.set("2026-10-01")
    ui.modo.set("Subir + cruzar + descargar lo que cruza")
    c = ui.armar_comando()
    assert "--todos" in c and "--desde" in c and "--dias" not in c
    ui.modo.set("VIGILANTE: bajar todo lo que llega, todo el día")
    ui.al_dia.set(True)
    c = ui.armar_comando()
    assert "scripts/vigilante.py" in c and "--todos" in c and "--sin-mouse" not in c
    ui.al_dia.set(False)
    assert "--sin-mouse" in ui.armar_comando()


def test_iniciar_corre_el_proceso_muestra_el_registro_y_termina(ui, monkeypatch):
    monkeypatch.setattr(ui, "verificar_entorno", lambda: True)
    monkeypatch.setattr(ui, "armar_comando", lambda: [sys.executable, "-u", "-c",
                        "print('##### Grupo 1/4: Veraguas #####'); print('TANDA 1'); print('CRUCE EN VIVO: 10 paquetes -> 3 cruzan')"])
    ui.iniciar()
    assert "DETENER" in ui.btn.cget("text") and "Corriendo" in ui.estado.get()
    assert _esperar(lambda: (ui.refrescar() or True) and "INICIAR" in ui.btn.cget("text"))
    assert "Terminado" in ui.estado.get()
    assert "TANDA 1" in _texto(ui) and ui.v["grupo"].get().startswith("1/4") and "3 cruzan" in ui.v["cruce"].get()


def test_detener_corta_un_proceso_largo(ui, monkeypatch):
    monkeypatch.setattr(ui, "verificar_entorno", lambda: True)
    monkeypatch.setattr(ui, "armar_comando", lambda: [sys.executable, "-u", "-c", "import time; print('listo', flush=True); time.sleep(60)"])
    ui.iniciar()
    assert _esperar(lambda: (ui.refrescar() or True) and "listo" in _texto(ui))
    ui.alternar()                                                        # el mismo botón ahora detiene
    assert ui.estado.get() == "Detenido por ti"
    assert _esperar(lambda: (ui.refrescar() or True) and "INICIAR" in ui.btn.cget("text"))


def test_no_inicia_si_el_entorno_tiene_errores(ui, monkeypatch):
    monkeypatch.setattr(ui, "verificar_entorno", lambda: False)
    monkeypatch.setattr(ui_mod.threading, "Thread", lambda *a, **k: pytest.fail("no debe lanzar el bot"))
    ui.iniciar()
    assert "INICIAR" in ui.btn.cget("text")


def test_las_tarjetas_se_llenan_con_lo_que_dice_el_registro(ui):
    for linea in ("##### Grupo 2/4: Incidencias CFFM-MECOPT(Oeste) #####", "Ronda 1 - fase 1: cargando hacia arriba",
                  "  tandas: 7 | burbujas: 94 | ciclos: 30 | intentos sin tanda: 0 | 400s", "DESCARGA (pasada 1/3): 12 mensajes por bajar",
                  "[Veraguas] VUELTA: nuevos=3 bajados=7", "  IDENTIFICADA DESPUÉS: 2026-10-15 10:57 -> Aviso-5643479"):
        ui._interpretar(linea)
    assert ui.v["grupo"].get().startswith("2/4") and ui.v["tandas"].get().startswith("7") and "bajados=7" in ui.v["fotos"].get()
    assert "IDENTIFICADA" in ui.v["cruce"].get() or "Aviso-5643479" in ui.v["cruce"].get()


def test_el_registro_colorea_errores_avisos_y_exitos(ui):
    ui._escribir("2026-10-17 | ERROR | algo falló\n2026-10-17 | WARNING | ojo\n    -> ok: 4 archivo(s)\nCRUCE EN VIVO: 1")
    t = ui.texto._textbox
    assert t.tag_ranges("error") and t.tag_ranges("aviso") and t.tag_ranges("ok") and t.tag_ranges("info")


def test_cambio_de_tema_claro_oscuro(ui):
    ui.tema.set("☀  Claro")
    ui._cambiar_tema("☀  Claro")
    assert ctk.get_appearance_mode() == "Light"
    claro = ui.texto._textbox.tag_cget("error", "foreground")
    ui._cambiar_tema("🌙  Oscuro")
    assert ctk.get_appearance_mode() == "Dark" and ui.texto._textbox.tag_cget("error", "foreground") != claro


def test_exportar_traspaso_llama_al_script_y_abre_la_carpeta(ui, monkeypatch):
    llamadas, abiertos = [], []
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "Traspaso creado: x.zip", ""))[1])
    monkeypatch.setattr(ui_mod.os, "startfile", lambda r: abiertos.append(r), raising=False)
    ui.exportar_traspaso()
    assert llamadas == [["scripts/traspaso.py", "exportar"]] and "Traspaso listo" in ui.estado.get() and abiertos
    monkeypatch.setattr(ui, "_ejecutar", lambda args: subprocess.CompletedProcess(args, 1, "", "falló"))
    ui.exportar_traspaso()
    assert "Error al crear el traspaso" in ui.estado.get()


def test_importar_traspaso_pide_archivo_y_respeta_la_respuesta_del_excel(ui, monkeypatch):
    llamadas = []
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "Traspaso importado:", ""))[1])
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilename", lambda **k: "")
    ui.importar_traspaso()
    assert llamadas == []                                                    # canceló el selector: no hace nada
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilename", lambda **k: "C:/x/Traspaso.zip")
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: False)
    ui.importar_traspaso()
    assert llamadas[-1] == ["scripts/traspaso.py", "importar", "C:/x/Traspaso.zip"]
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: True)
    ui.importar_traspaso()
    assert llamadas[-1][-1] == "--excel" and ui.estado.get() == "Traspaso importado"


def test_importar_se_niega_si_el_bot_corre(ui, monkeypatch):
    avisos = []
    monkeypatch.setattr(ui_mod.messagebox, "showwarning", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilename", lambda **k: pytest.fail("no debe pedir archivo con el bot corriendo"))
    ui.btn.configure(text="■  DETENER")
    ui.importar_traspaso()
    assert len(avisos) == 1
