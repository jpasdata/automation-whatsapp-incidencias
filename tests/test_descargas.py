from datetime import datetime
from pathlib import Path

from src.cruce import ResultadoCruce
from src.descargas import _slug, plan_descargas
from src.excel_manager import FilaIncidencia
from src.modelos import Mensaje, ResultadoMatch, TipoOrigenMatch


def _cruce(id_msg, n_adj, con_fila=True):
    m = Mensaje(remitente="+507 6000-0001", timestamp=datetime(2026, 10, 9, 14, 5), texto="", tiene_adjunto=n_adj > 0,
                tipo_adjunto="imagen", id_mensaje=id_msg, n_adjuntos=n_adj)
    r = ResultadoMatch(mensaje=m, codigo="12345678", origen=TipoOrigenMatch.MISMO_MENSAJE, candidatos=["12345678"])
    fila = FilaIncidencia(231, "12345678", None, None, None, None, None, None, "") if con_fila else None
    return ResultadoCruce(r, fila, None, "12345678", None)


def test_slug_quita_tildes_y_simbolos():
    assert _slug("CFFM_Coclé Sea/Central") == "CFFM-Cocle-Sea-Central"


def test_plan_organiza_por_dia_e_incidencia(tmp_path):
    plan = plan_descargas([_cruce("true_x_ABC12345", 2)], tmp_path, "Veraguas", set())
    t = plan["true_x_ABC12345"]
    assert t.carpeta == tmp_path / "Veraguas" / "2026-10-09" / "231_12345678"
    assert t.base.startswith("1405_") and t.n_esperadas == 2


def test_plan_omite_sin_fila_sin_adjunto_y_ya_descargadas(tmp_path):
    cruces = [_cruce("a", 1, con_fila=False), _cruce("b", 0), _cruce("c", 1)]
    assert plan_descargas(cruces, tmp_path, "G", {"c"}) == {}


def test_todo_incluye_lo_que_no_cruza_en_sin_incidencia(tmp_path):
    plan = plan_descargas([_cruce("a", 3, con_fila=False), _cruce("b", 0)], tmp_path, "G", set(), todo=True)
    assert list(plan) == ["a"] and plan["a"].carpeta.name == "_sin_incidencia" and plan["a"].estado == "sin_cruce"
