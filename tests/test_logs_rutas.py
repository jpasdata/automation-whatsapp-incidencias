import logging
from pathlib import Path

from src.nucleo import eventos
from src.nucleo.logger import ArchivoPorTamano, nueva_carpeta_de_corrida
from src.nucleo.rutas import R, Rutas


def test_cada_corrida_tiene_su_carpeta_por_fecha_y_hora(tmp_path):
    d = nueva_carpeta_de_corrida(tmp_path, "vigilante")
    assert d.parent.parent == tmp_path / "corridas" and d.name.endswith("_vigilante") and d.is_dir()
    assert len(d.parent.name) == 10 and d.parent.name[4] == "-"            # AAAA-MM-DD


def test_el_log_no_crece_sin_limite_abre_el_siguiente_archivo(tmp_path):
    h = ArchivoPorTamano(tmp_path, "detalle", 300, logging.DEBUG, logging.Formatter("%(message)s"))
    log = logging.getLogger("prueba_tamano")
    log.setLevel(logging.DEBUG)
    log.addHandler(h)
    for i in range(30):
        log.info("linea numero %02d con relleno para ocupar espacio", i)
    h.close()
    log.removeHandler(h)
    partes = sorted(tmp_path.glob("detalle_*.log"))
    assert len(partes) >= 3 and partes[0].name == "detalle_001.log"
    assert all(p.stat().st_size <= 400 for p in partes)
    assert sum(p.read_text(encoding="utf-8").count("linea numero") for p in partes) == 30      # no se pierde ninguna línea


def test_los_csv_se_leen_de_todas_las_corridas_y_se_encuentra_la_ultima(tmp_path):
    for dia, hora, filas in (("2026-10-16", "100000_a", [{"id_mensaje": "m1", "resultado": "error"}]),
                             ("2026-10-17", "090000_b", [{"id_mensaje": "m1", "resultado": "ok"}, {"id_mensaje": "m2", "resultado": "ok"}])):
        carpeta = tmp_path / "corridas" / dia / hora
        carpeta.mkdir(parents=True)
        eventos.configurar(carpeta)
        for f in filas:
            eventos.registrar_csv("descargas_detalle.csv", f)
    todas = eventos.leer_todos("descargas_detalle.csv", tmp_path)
    assert [f["id_mensaje"] for f in todas] == ["m1", "m1", "m2"] and todas[0]["resultado"] == "error"
    assert eventos.ultima_corrida(tmp_path).name == "090000_b"
    assert eventos.ultima_corrida(tmp_path, "no_existe.csv") is None


def test_rutas_centrales_estan_donde_dice_la_documentacion(tmp_path):
    r = Rutas(tmp_path)
    assert r.incidencias_base == tmp_path / "data" / "Incidencias" / "INCIDENCIAS_BASE.xlsx"
    assert r.incidencias_nuevas == tmp_path / "data" / "Incidencias" / "nuevas"
    assert r.reportes_en_vivo == tmp_path / "data" / "Reportes" / "en_vivo" and r.estado_vigilante == tmp_path / "logs" / "estado" / "vigilante_estado.json"
    assert R.raiz == Path(__file__).resolve().parent.parent                # la raíz real del proyecto
