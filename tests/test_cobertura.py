from __future__ import annotations

from datetime import datetime

from src.datos.cobertura import cobertura, resumen_cobertura
from src.cruce.cruce import ResultadoCruce
from src.excel.manager import FilaIncidencia
from src.nucleo.modelos import CriterioBusqueda, Mensaje, ResultadoMatch, TipoOrigenMatch
from src.cruce.validacion_temporal import ResultadoValidacionTemporal


def _fila(n, det=datetime(2026, 10, 10, 8, 0)):
    return FilaIncidencia(n, f"0{n}", f"{n}", None, None, det, det, None, "sin_dato", "VERAGUAS")


def _cruce(fila, dentro=True, fotos=3):
    m = Mensaje("Juan", datetime(2026, 10, 10, 9, 0), "x", True, "imagen", n_adjuntos=fotos)
    r = ResultadoMatch(m, "1", TipoOrigenMatch.MISMO_MENSAJE, candidatos=["1"])
    return ResultadoCruce(r, fila, CriterioBusqueda.NUMERO_AVISO, "1", ResultadoValidacionTemporal(dentro, "ok"))


def test_cobertura_y_resumen():
    a, b, c = _fila(2), _fila(3), _fila(4, det=datetime(2026, 10, 12, 8, 0))
    cruces = [_cruce(a), _cruce(a, fotos=2), _cruce(b, dentro=False)]
    cob = {r["fila_excel"]: r for r in cobertura([a, b, c], cruces)}
    assert cob[2]["estado_evidencia"] == "con_evidencia" and cob[2]["paquetes"] == 2 and cob[2]["fotos_videos"] == 5
    assert cob[3]["estado_evidencia"] == "revisar_horario"
    assert cob[4]["estado_evidencia"] == "sin_evidencia" and "pedir evidencia" in cob[4]["observacion"]
    assert resumen_cobertura(list(cob.values())) == {"incidencias": 3, "con_evidencia": 1, "revisar_horario": 1, "sin_evidencia": 1}
    assert resumen_cobertura(list(cob.values()), datetime(2026, 10, 10), datetime(2026, 10, 10))["incidencias"] == 2
