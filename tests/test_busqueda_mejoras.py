from datetime import datetime, timedelta
from types import SimpleNamespace

from src.aprendizaje import aprender_pares
from src.config import ventana_texto_de_grupo
from src.cruce import cruzar
from src.excel_manager import FilaIncidencia
from src.matcher import asociar_mensajes
from src.modelos import Mensaje, TipoOrigenMatch

T0 = datetime(2026, 10, 12, 10, 0)


def _m(min_, quien, texto=None, adj=False):
    return Mensaje(remitente=quien, timestamp=T0 + timedelta(minutes=min_), texto=texto, tiene_adjunto=adj,
                   tipo_adjunto="imagen" if adj else None, id_mensaje=f"{quien}{min_}", n_adjuntos=1 if adj else 0)


def test_par_en_el_mismo_mensaje():
    assert aprender_pares([_m(0, "A", "Aviso 5636582 Incidencia 1170118")]) == {"5636582": "1170118"}


def test_par_en_mensajes_pegados_del_mismo_remitente():
    ms = [_m(0, "A", "Se atendió el aviso 5636582 utira", adj=True), _m(1, "A", "Incidencia . 1170118")]
    assert aprender_pares(ms) == {"5636582": "1170118"}


def test_par_ambiguo_se_descarta():
    ms = [_m(0, "A", "aviso 5636582 incidencia 1170118"), _m(5, "B", "aviso 5636582 incidencia 1170999")]
    assert aprender_pares(ms) == {}


def test_cruce_usa_el_par_aprendido_cuando_el_excel_no_tiene_el_aviso():
    ms = [_m(0, "A", "Aviso 5636582", adj=True)]
    res = asociar_mensajes(ms, r"\b\d{6,8}\b")
    fila = FilaIncidencia(7, "011701180001", "1170118", None, None, T0 - timedelta(hours=1), T0 + timedelta(hours=1), None, "")
    excel = SimpleNamespace(buscar_fila_por_candidatos=lambda cands, prov: (fila, "numero_aviso", "1170118") if "1170118" in cands else (None, None, None))
    sin = cruzar(res, excel, 4)
    con = cruzar(res, excel, 4, pares={"5636582": "1170118"})
    assert sin[0].fila is None and con[0].fila is fila and con[0].aprendido


def test_comentario_de_otra_persona_es_probable_y_solo_si_esta_activado():
    ms = [_m(0, "A", adj=True), _m(5, "COORD", "Aviso 5636582")]
    apagado = asociar_mensajes(ms, r"\b\d{6,8}\b")
    prendido = asociar_mensajes(ms, r"\b\d{6,8}\b", ventana_ajena_minutos=20)
    assert apagado[0].origen == TipoOrigenMatch.SIN_CODIGO
    assert prendido[0].origen == TipoOrigenMatch.COMENTARIO_AJENO and prendido[0].candidatos == ["5636582"]
    fila = FilaIncidencia(7, "011701180001", "1170118", None, "5636582", T0 - timedelta(hours=1), T0 + timedelta(hours=1), None, "")
    excel = SimpleNamespace(buscar_fila_por_candidatos=lambda c, p: (fila, "numero_aviso", "5636582"))
    assert cruzar(prendido, excel, 4)[0].estado == "probable"


def test_comentario_ajeno_fuera_de_ventana_no_cuenta():
    ms = [_m(0, "A", adj=True), _m(60, "COORD", "Aviso 5636582")]
    assert asociar_mensajes(ms, r"\b\d{6,8}\b", ventana_ajena_minutos=20)[0].origen == TipoOrigenMatch.SIN_CODIGO


def test_ventana_propia_por_grupo():
    cfg = SimpleNamespace(matching=SimpleNamespace(ventana_minutos_por_grupo={"Oeste": 75}, ventana_minutos_mensaje_separado=45))
    assert ventana_texto_de_grupo(cfg, "Incidencias CFFM-MECOPT(Oeste)") == 75
    assert ventana_texto_de_grupo(cfg, "CFFM_Veraguas_Sea_Central-Reporte de videos") == 45
