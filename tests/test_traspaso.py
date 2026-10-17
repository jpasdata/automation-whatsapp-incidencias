from datetime import datetime
from pathlib import Path

from src.indice import Indice
from src.modelos import Mensaje
from src.traspaso import exportar, importar


def _msg(id_, minuto=0):
    return Mensaje(remitente="+507 6000-0001", timestamp=datetime(2026, 10, 9, 14, minuto), texto="Aviso 5600001", tiene_adjunto=True,
                   tipo_adjunto="imagen", id_mensaje=id_, n_adjuntos=1)


def _pc(raiz: Path, mensajes, descargados: dict[str, str] | None = None):
    """Un 'PC' de prueba: índice con mensajes y archivos descargados con rutas completas de ESE PC."""
    (raiz / "data" / "indice").mkdir(parents=True)
    ev = raiz / "data" / "Evidencias_WhatsApp"
    with Indice(raiz / "data" / "indice" / "indice.sqlite3") as ix:
        ix.guardar("G", mensajes)
        for id_, rel in (descargados or {}).items():
            f = ev / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"jpg")
            ix.marcar_descarga("G", id_, "ok", str(f))
    return ev


def test_rebasar_rutas_reapunta_a_la_carpeta_del_otro_pc(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        ix.guardar("G", [_msg("a")])
        ix.marcar_descarga("G", "a", "ok", r"C:\02_Extras\proyecto\data\Evidencias_WhatsApp\Veraguas\2026-10-09\Inc-1\x_1.jpg;"
                                           r"C:\02_Extras\proyecto\data\Evidencias_WhatsApp\Veraguas\2026-10-09\Inc-1\x_2.jpg")
        assert ix.rebasar_rutas(tmp_path / "otro" / "Evidencias_WhatsApp") == 1
        ruta = ix.estado_descarga("G")["a"][1]
        assert ruta.count(";") == 1 and all(str(tmp_path / "otro" / "Evidencias_WhatsApp") in r for r in ruta.split(";"))
        assert ix.rebasar_rutas(tmp_path / "otro" / "Evidencias_WhatsApp") == 0   # idempotente


def test_fusionar_agrega_lo_que_falta_y_no_pisa_lo_que_ya_hay(tmp_path):
    with Indice(tmp_path / "a.sqlite3") as a, Indice(tmp_path / "b.sqlite3") as b:
        a.guardar("G", [_msg("m1"), _msg("m2", 1)])
        a.marcar_descarga("G", "m1", "ok", "ruta_a")
        b.guardar("G", [_msg("m2", 1), _msg("m3", 2)])
        b.marcar_descarga("G", "m1", "ok", "ruta_b")      # m1 no está en b (no se inserta de nuevo)
        b.marcar_descarga("G", "m2", "ok", "ruta_b2")     # a no lo tenía descargado: lo toma
        b.marcar_descarga("G", "m3", "ok", "ruta_b3")
    with Indice(tmp_path / "a.sqlite3") as a:
        r = a.fusionar(tmp_path / "b.sqlite3")
        est = a.estado_descarga("G")
        assert r["mensajes_nuevos"] == 1
        assert est["m1"] == ("ok", "ruta_a") and est["m2"] == ("ok", "ruta_b2") and est["m3"] == ("ok", "ruta_b3")


def test_exportar_e_importar_en_otro_pc_conserva_todo_y_reapunta_las_rutas(tmp_path):
    pc1, pc2 = tmp_path / "pc1", tmp_path / "pc2"
    _pc(pc1, [_msg("m1"), _msg("m2", 1)], {"m1": "Veraguas/2026-10-09/Inc-1/a_1.jpg", "m2": "Veraguas/2026-10-09/_sin_numero/b_1.jpg"})
    (pc1 / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx").write_bytes(b"excel")
    zip_ = exportar(pc1, tmp_path / "t.zip")
    assert zip_.exists()
    # el otro PC ya había avanzado por su cuenta con otro mensaje
    _pc(pc2, [_msg("m3", 2)], {"m3": "Veraguas/2026-10-09/Inc-3/c_1.jpg"})
    resumen = importar(pc2, zip_)
    assert resumen["evidencias_copiadas"] == 2 and resumen["mensajes_nuevos"] == 2
    with Indice(pc2 / "data" / "indice" / "indice.sqlite3") as ix:
        est = ix.estado_descarga("G")
        assert set(est) == {"m1", "m2", "m3"}
        for _, ruta in est.values():
            assert Path(ruta).exists() and str(pc2) in ruta          # todas las rutas apuntan a ESTE PC y existen
    assert list((pc2 / "data" / "indice" / "respaldo").glob("indice_antes_de_importar_*.sqlite3"))
    # sin --excel no se toca el Excel local
    assert not (pc2 / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx").exists()
    # importar otra vez no duplica ni falla
    otra = importar(pc2, zip_)
    assert otra["evidencias_copiadas"] == 0 and otra["evidencias_ya_existian"] == 2 and otra["mensajes_nuevos"] == 0


def test_importar_con_excel_deja_copia_del_anterior(tmp_path):
    pc1, pc2 = tmp_path / "pc1", tmp_path / "pc2"
    _pc(pc1, [_msg("m1")])
    (pc1 / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx").write_bytes(b"nuevo")
    _pc(pc2, [])
    (pc2 / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx").write_bytes(b"viejo")
    importar(pc2, exportar(pc1, tmp_path / "t.zip"), con_excel=True)
    assert (pc2 / "data" / "RESULTADO_CREACION_INCIDENCIAS.xlsx").read_bytes() == b"nuevo"
    assert any(f.read_bytes() == b"viejo" for f in (pc2 / "data").glob("RESULTADO_CREACION_INCIDENCIAS_antes_*.xlsx"))
