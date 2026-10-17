from datetime import datetime
from pathlib import Path

from src.cruce.cruce import ResultadoCruce
from src.bot.descargas import TareaDescarga
from src.excel.manager import FilaIncidencia
from src.datos.indice import Indice
from src.nucleo.modelos import Mensaje, ResultadoMatch, TipoOrigenMatch
from src.bot.vigilante import carpeta_sin_cruce, escribir_manifiestos, reubicar_identificadas


def _msg(id_, n=1):
    return Mensaje(remitente="+507 6000-0001", timestamp=datetime(2026, 10, 9, 14, 5), texto="Aviso 5600001", tiene_adjunto=True,
                   tipo_adjunto="imagen", id_mensaje=id_, n_adjuntos=n)


def test_foto_identificada_despues_se_mueve_a_la_carpeta_de_la_incidencia(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        ix.guardar("G", [_msg("m1")])
        viejo = tmp_path / "G" / "2026-10-09" / "_sin_numero"
        viejo.mkdir(parents=True)
        f = viejo / "1405_x_m1_1.jpg"
        f.write_bytes(b"jpg")
        ix.marcar_descarga("G", "m1", "ok", str(f))
        nueva = tmp_path / "G" / "2026-10-09" / "231_011600000001"
        destinos = {"m1": TareaDescarga("m1", nueva, "1405_x_m1", 1, "ok", {"dia": "2026-10-09", "hora": "14:05", "remitente": "x", "origen": "respuesta"})}
        assert reubicar_identificadas(ix, "G", destinos) == 1
        assert (nueva / "1405_x_m1_1.jpg").exists() and not f.exists() and not viejo.exists()
        assert str(nueva / "1405_x_m1_1.jpg") in ix.estado_descarga("G")["m1"][1]
        assert reubicar_identificadas(ix, "G", destinos) == 0  # ya está donde debe


def test_carpeta_para_lo_que_no_cruza():
    c = lambda estado: ResultadoCruce(ResultadoMatch(_msg("a"), None, TipoOrigenMatch.SIN_CODIGO), None, None, None, None)  # noqa: E731
    assert carpeta_sin_cruce(c("x")) == "_sin_numero"  # sin candidatos -> estado sin_numero


def test_manifiesto_por_dia(tmp_path):
    with Indice(tmp_path / "i.sqlite3") as ix:
        m = _msg("m1")
        ix.guardar("G", [m])
        fila = FilaIncidencia(231, "011600000001", "1160000", None, "5600001", None, None, None, "")
        cruce = ResultadoCruce(ResultadoMatch(m, "5600001", TipoOrigenMatch.MISMO_MENSAJE, candidatos=["5600001"]), fila, None, "5600001", None)
        assert escribir_manifiestos(ix, "G", [cruce], tmp_path, datetime(2026, 10, 1)) == 1
        csv_ = next(tmp_path.rglob("manifiesto_2026-10-09.csv")).read_text(encoding="utf-8-sig")
        assert "011600000001" in csv_ and "mismo_mensaje" in csv_ and "pendiente" in csv_


def test_hueco_se_detecta_solo_si_lo_leido_no_se_empalma_con_lo_conocido():
    from src.bot.vigilante import hay_hueco

    leidos = [_msg("n1"), _msg("n2")]
    assert hay_hueco(leidos, {"viejo1", "viejo2"}) is True            # nada conocido en pantalla: hubo un hueco
    assert hay_hueco(leidos, {"n2", "viejo"}) is False                # se empalma
    assert hay_hueco(leidos, set()) is False                          # primera vez: no hay con qué empalmar
    assert hay_hueco([], {"viejo"}) is False


def test_estado_guardado_permite_saber_donde_quedo(tmp_path):
    from types import SimpleNamespace

    from src.bot.vigilante import Vigilante

    cfg = SimpleNamespace(logging=SimpleNamespace(carpeta_logs=str(tmp_path)))
    v = Vigilante(cfg, ["G"], lambda: None, ruta_indice=tmp_path / "i.sqlite3")
    with Indice(tmp_path / "i.sqlite3") as ix:
        ix.guardar("G", [_msg("m1")])
        v._guardar_estado("G", ix, "nuevos=1 bajados=2", 3)
    import json

    e = json.loads((tmp_path / "estado" / "vigilante_estado.json").read_text(encoding="utf-8"))["G"]
    assert e["ultimo_mensaje_indexado"] == "2026-10-09T14:05" and e["mensajes_en_indice"] == 1 and e["pendientes_por_bajar"] == 3
