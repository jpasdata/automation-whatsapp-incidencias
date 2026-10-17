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
from src.nucleo.verificador import ERROR, OK, Resultado  # noqa: E402


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
    from src.nucleo.config import load_config

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
    for esperado in ("INICIAR", "Verificar entorno", "Estado de descargas", "Abrir Excel de incidencias", "Generar reporte Excel", "Abrir evidencias",
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
    from src.nucleo.rutas import Rutas

    monkeypatch.setattr(ui_mod, "R", Rutas(tmp_path))
    f = tmp_path / "base.xlsx"
    monkeypatch.setattr(ui.cfg.excel, "ruta_archivo", str(f))
    ui.abrir_excel_vivo()
    assert abiertos == [] and "Aún no hay Excel de incidencias" in ui.estado.get()
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


def test_abrir_logs_va_a_la_ultima_corrida_y_las_incidencias_se_incorporan(ui, monkeypatch, tmp_path):
    abiertos, llamadas = [], []
    monkeypatch.setattr(ui_mod.os, "startfile", lambda r: abiertos.append(Path(r)), raising=False)
    from src.nucleo.rutas import Rutas

    monkeypatch.setattr(ui_mod, "R", Rutas(tmp_path))
    ui.abrir_logs()                                                  # sin corridas: abre logs/
    (tmp_path / "logs" / "corridas" / "2026-10-17" / "083000_vigilante").mkdir(parents=True)
    (tmp_path / "logs" / "corridas" / "2026-10-17" / "091500_vigilante").mkdir(parents=True)
    ui.abrir_logs()
    assert abiertos[0] == tmp_path / "logs" and abiertos[1].name == "091500_vigilante"
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "Incorporado: 1 archivo(s)", ""))[1])
    ui.incorporar_incidencias()
    assert llamadas == [["scripts/incidencias.py", "incorporar"]] and ui.estado.get() == "Incidencias incorporadas"


def test_pasar_lo_nuevo_al_historico_pide_confirmacion(ui, monkeypatch):
    llamadas = []
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "3 incidencia(s) pasaron", ""))[1])
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: False)
    ui.consolidar_incidencias()
    assert llamadas == []
    monkeypatch.setattr(ui_mod.messagebox, "askyesno", lambda *a, **k: True)
    ui.consolidar_incidencias()
    assert llamadas == [["scripts/incidencias.py", "consolidar"]] and ui.estado.get() == "Hecho"


def test_cargar_incidencias_abre_selector_y_usa_el_comando_facil(ui, monkeypatch):
    llamadas = []
    monkeypatch.setattr(ui, "_ejecutar", lambda args: (llamadas.append(args), subprocess.CompletedProcess(args, 0, "Cargado: 1 archivo(s) -> 21 incidencias nuevas", ""))[1])
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilenames", lambda **k: ())
    ui.cargar_incidencias()
    assert llamadas == []                                                   # canceló: no hace nada
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilenames", lambda **k: ("C:/x/a.xlsx", "C:/x/b.xlsx"))
    ui.cargar_incidencias()
    assert llamadas == [["scripts/incidencias.py", "cargar", "C:/x/a.xlsx", "C:/x/b.xlsx"]] and ui.estado.get() == "Incidencias cargadas"


def test_cargar_incidencias_con_el_bot_corriendo_solo_deja_los_archivos(ui, monkeypatch, tmp_path):
    from src.nucleo.rutas import Rutas

    monkeypatch.setattr(ui_mod, "R", Rutas(tmp_path / "proyecto"))
    origen = tmp_path / "nuevas.xlsx"
    origen.write_bytes(b"x")
    monkeypatch.setattr(ui, "_ejecutar", lambda args: pytest.fail("con el bot corriendo no se incorpora a mano: lo hace el vigilante"))
    monkeypatch.setattr(ui_mod.filedialog, "askopenfilenames", lambda **k: (str(origen),))
    ui.btn.configure(text="■  DETENER")
    ui.cargar_incidencias()
    assert (tmp_path / "proyecto" / "data" / "Incidencias" / "nuevas" / "nuevas.xlsx").exists() and "vigilante" in ui.estado.get().lower()


def test_la_franja_de_pantalla_aparece_con_el_modo_y_desaparece(ui):
    ui.modo.set(next(m for m in ui_mod.MODOS if "VIGILANTE" in m))
    ui.al_dia.set(True)
    ui._anunciar_modo(True)
    assert ui.franja is not None
    assert "VIGILANTE" in ui.franja_txt.get() and "se pondrá ROJA" in ui.franja_txt.get()
    ui.al_dia.set(False)
    ui._actualizar_franja()
    assert "ROJA" not in ui.franja_txt.get()
    ui._anunciar_modo(False)
    assert ui.franja is None


def test_la_franja_se_ajusta_al_texto_y_cabe_en_pantalla(ui):
    ui.modo.set(next(m for m in ui_mod.MODOS if "descargar lo que cruza" in m))
    ui.v["grupo"].set("1/1: CFFM_Veraguas_Sea_Central-Reporte de videos")
    ui._anunciar_modo(True)
    ui.franja.update_idletasks()
    assert ui.franja.winfo_width() >= ui.franja.winfo_reqwidth() - 2        # el texto cabe completo
    assert ui.franja.winfo_width() <= ui.franja.winfo_screenwidth()
    ui._anunciar_modo(False)


def test_la_franja_explica_que_hace_que_no_se_puede_y_que_viene(ui):
    historico = next(m for m in ui_mod.MODOS if "descargar lo que cruza" in m)
    ui.modo.set(historico)
    ui.encadenar.set(True)
    ui.v["fase"].set("Ronda 2: subiendo el chat")
    texto, color = ui._texto_franja()
    assert "Ronda 2: subiendo el chat" in texto and "NO uses mouse ni teclado" in texto and "pasa solo a VIGILANTE" in texto and color == "#b91c1c"
    assert len(texto.splitlines()) == 2
    ui.encadenar.set(False)
    assert "se detiene" in ui._texto_franja()[0]
    ui.modo.set(next(m for m in ui_mod.MODOS if "VIGILANTE" in m))
    texto, color = ui._texto_franja()
    assert "puedes usar el PC" in texto and color == "#15803d"
    ui._interpretar("[Veraguas] CERRANDO EL HUECO: subiendo con el mouse hasta empalmar (no lo toques unos minutos).")
    texto, color = ui._texto_franja()
    assert "NO TOQUES EL MOUSE" in texto and color == "#b91c1c"
    ui._interpretar("[Veraguas] hueco cerrado: 12 mensajes recuperados")
    assert ui._texto_franja()[1] == "#15803d"


def test_al_terminar_el_historico_pasa_solo_a_vigilante(ui, monkeypatch):
    arrancados = []
    monkeypatch.setattr(ui, "iniciar", lambda: arrancados.append((ui.modo.get(), ui.grupo.get())))
    ui.modo.set(next(m for m in ui_mod.MODOS if "descargar lo que cruza" in m))
    ui._pasar_a_vigilante()
    assert arrancados and "VIGILANTE" in arrancados[0][0] and arrancados[0][1] == ui_mod.TODOS
    assert "VIGILANTE" in ui.nota_franja[0]


def test_el_grupo_se_muestra_con_su_nombre_corto(ui):
    assert ui._grupo_corto("1/4: CFFM_Veraguas_Sea_Central-Reporte de videos") == "Veraguas (1/4)"
    assert ui._grupo_corto("3/4: CFFM_Coclé_Sea_Central-Reporte de videos") == "Coclé (3/4)"
    assert ui._grupo_corto("2/4: Incidencias CFFM-MECOPT(Oeste)") == "Oeste (2/4)"


def test_los_intentos_se_pasan_al_historico(ui):
    ui.modo.set(next(m for m in ui_mod.MODOS if "descargar lo que cruza" in m))
    ui.intentos.set("9")
    assert ui.armar_comando()[-0:] and "--intentos" in ui.armar_comando() and ui.armar_comando()[ui.armar_comando().index("--intentos") + 1] == "9"
    ui.intentos.set("")
    assert "--intentos" not in ui.armar_comando()
