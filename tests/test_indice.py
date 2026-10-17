from __future__ import annotations

from datetime import date, datetime

from src.historico import tabla_por_dia, verificar_historico
from src.indice import Indice
from src.modelos import Mensaje


def _m(id_, ts, adj=0, texto=None, remitente="Juan", cita=None):
    return Mensaje(remitente=remitente, timestamp=ts, texto=texto, tiene_adjunto=adj > 0,
                   tipo_adjunto="imagen" if adj else None, id_mensaje=id_, n_adjuntos=adj,
                   cita_autor=cita, cita_texto="3 fotos" if cita else None)


def test_guardar_es_idempotente_y_conserva_estado_de_descarga(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        ms = [_m("A", datetime(2026, 10, 14, 9, 0), adj=2), _m("B", datetime(2026, 10, 14, 9, 5), texto="Aviso 5644135")]
        assert ix.guardar("G", ms) == 2
        ix.marcar_descarga("G", "A", "ok", "x.jpg")
        assert ix.guardar("G", ms + [_m("C", datetime(2026, 10, 15, 8, 0))]) == 1  # solo el nuevo
        assert ix.estado_descarga("G")["A"] == ("ok", "x.jpg")
        assert ix.contar("G") == 3 and ix.ids("G") == {"A", "B", "C"}


def test_mensajes_se_reconstruyen_en_orden_con_citas(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        ix.guardar("G", [_m("2", datetime(2026, 10, 14, 9, 5), texto="inc 1168222", cita="Juan"), _m("1", datetime(2026, 10, 14, 9, 0), adj=3)])
        ms = ix.mensajes("G")
        assert [m.id_mensaje for m in ms] == ["1", "2"]
        assert ms[0].tiene_adjunto and ms[0].n_adjuntos == 3
        assert ms[1].cita_autor == "Juan" and ms[1].cita_texto == "3 fotos"
        assert [m.id_mensaje for m in ix.mensajes("G", desde=datetime(2026, 10, 14, 9, 1))] == ["2"]


def test_resumen_por_dia_y_cobertura(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        ix.guardar("G", [
            _m("1", datetime(2026, 10, 13, 9, 0), adj=4), _m("2", datetime(2026, 10, 13, 9, 1)),
            _m("3", datetime(2026, 10, 15, 9, 0), adj=1),
        ])
        r = ix.resumen_por_dia("G")
        assert [(x.dia, x.mensajes, x.con_adjunto, x.fotos_videos) for x in r] == [
            (date(2026, 10, 13), 2, 1, 4), (date(2026, 10, 15), 1, 1, 1)]
        assert ix.cubre_desde("G", datetime(2026, 10, 13)) and not ix.cubre_desde("G", datetime(2026, 10, 1))
        assert ix.rango("G")[0] == datetime(2026, 10, 13, 9, 0)


def test_verificador_muestra_huecos_y_estado(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        assert "vacío" in verificar_historico(ix, "G", datetime(2026, 10, 1))
        ix.guardar("G", [_m("1", datetime(2026, 10, 13, 9, 0), adj=2)])
        txt = verificar_historico(ix, "G", datetime(2026, 10, 1), hoy=date(2026, 10, 15))
        assert "INCOMPLETO: faltan 12 día(s)" in txt
        assert "2026-10-01" in txt and "(sin datos cargados)" in txt
        ix.guardar("G", [_m("0", datetime(2026, 10, 1, 8, 0))])
        assert "COMPLETO" in verificar_historico(ix, "G", datetime(2026, 10, 1), hoy=date(2026, 10, 15))


def test_tabla_por_dia_incluye_todos_los_dias():
    txt = tabla_por_dia([], date(2026, 10, 1), date(2026, 10, 3))
    assert txt.count("(sin datos cargados)") == 3
