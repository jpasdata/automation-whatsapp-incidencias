"""Casos que explicó Henry: el supervisor manda las fotos y DESPUÉS escribe el número (a veces citando el paquete)."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.cruce.matcher import asociar_mensajes, extraer_candidatos, normalizar_candidato
from src.nucleo.modelos import Mensaje, TipoOrigenMatch

PATRON = r"\b\d{6,8}\b"
BASE = datetime(2026, 10, 15, 10, 0)


def _m(remitente, texto, adj=False, minutos=0, n=0, cita_autor=None, cita_texto=None):
    return Mensaje(
        remitente=remitente, timestamp=BASE + timedelta(minutes=minutos), texto=texto,
        tiene_adjunto=adj, tipo_adjunto="imagen" if adj else None,
        n_adjuntos=n or (1 if adj else 0), cita_autor=cita_autor, cita_texto=cita_texto,
    )


def test_fotos_primero_y_texto_despues_sin_citar():
    r = asociar_mensajes([_m("Juan", "", adj=True), _m("Juan", "Aviso:5644135", minutos=3)], PATRON)
    assert r[0].codigo == "5644135"
    assert r[0].origen == TipoOrigenMatch.MENSAJE_POSTERIOR


def test_respuesta_citando_el_paquete_gana_aunque_pase_mucho_tiempo():
    msgs = [
        _m("Juan", "", adj=True, minutos=0, n=6),
        _m("Pedro", "otra cosa", minutos=5),
        _m("Juan", "inc 1168222", minutos=120, cita_autor="Juan", cita_texto="6 fotos"),
    ]
    r = asociar_mensajes(msgs, PATRON)
    assert r[0].codigo == "1168222" and r[0].origen == TipoOrigenMatch.RESPUESTA


def test_respuesta_elige_el_paquete_con_la_misma_cantidad_de_fotos():
    msgs = [
        _m("Juan", "", adj=True, minutos=0, n=6),
        _m("Juan", "", adj=True, minutos=10, n=2),
        _m("Juan", "Aviso:5644135", minutos=30, cita_autor="Juan", cita_texto="6 fotos"),
    ]
    r = asociar_mensajes(msgs, PATRON)
    assert r[0].codigo == "5644135" and r[0].origen == TipoOrigenMatch.RESPUESTA
    assert r[1].codigo is None  # el de 2 fotos no se mezcla (queda fuera de la ventana de 15 min)


def test_respuesta_de_otro_paquete_no_contamina_a_las_fotos_cercanas():
    msgs = [
        _m("Juan", "", adj=True, minutos=0, n=3),
        _m("Juan", "Aviso:5640098", minutos=2, cita_autor="Pedro", cita_texto="video"),
        _m("Pedro", "", adj=True, minutos=-60, n=1),
    ]
    r = asociar_mensajes(msgs, PATRON)
    foto_juan = next(x for x in r if x.mensaje.remitente == "Juan")
    assert foto_juan.codigo is None
    foto_pedro = next(x for x in r if x.mensaje.remitente == "Pedro")
    assert foto_pedro.codigo == "5640098" and foto_pedro.origen == TipoOrigenMatch.RESPUESTA


def test_gana_el_texto_mas_cercano_antes_o_despues():
    msgs = [_m("Juan", "inc 1111111", minutos=-10), _m("Juan", "", adj=True), _m("Juan", "inc 2222222", minutos=2)]
    r = asociar_mensajes(msgs, PATRON)
    assert r[0].codigo == "2222222" and r[0].origen == TipoOrigenMatch.MENSAJE_POSTERIOR


def test_a_igual_distancia_gana_el_previo():
    msgs = [_m("Juan", "inc 1111111", minutos=-5), _m("Juan", "", adj=True), _m("Juan", "inc 2222222", minutos=5)]
    assert asociar_mensajes(msgs, PATRON)[0].codigo == "1111111"


def test_texto_posterior_fuera_de_ventana_no_se_asocia():
    r = asociar_mensajes([_m("Juan", "", adj=True), _m("Juan", "inc 1111111", minutos=40)], PATRON, ventana_minutos=15)
    assert r[0].origen == TipoOrigenMatch.SIN_CODIGO


def test_varios_numeros_en_un_mensaje_son_candidatos_en_orden():
    msgs = [_m("Juan", "Avisó# 5644241\n\nF-15966\n\nInc 1168222", adj=True)]
    r = asociar_mensajes(msgs, PATRON)[0]
    assert r.candidatos == ["5644241", "F15966", "1168222"]
    assert r.codigo == "5644241"


def test_formatos_de_elemento():
    pats = [PATRON, r"\bF[\s:\-#]?\d{3,6}\b"]
    assert extraer_candidatos("F:08976 F08977 y f-123", pats) == ["F08976", "F08977", "F123"]
    assert normalizar_candidato("F: 15966") == "F15966"
    assert extraer_candidatos("llegué a las 14:30", pats) == []


def test_respuesta_suma_candidatos_al_paquete_que_ya_tenia_numero():
    msgs = [
        _m("Juan", "Aviso 5644355", adj=True, minutos=0, n=3),
        _m("Juan", "Incidencia #1170921", minutos=20, cita_autor="Juan", cita_texto="3 fotos"),
    ]
    r = asociar_mensajes(msgs, PATRON)[0]
    assert r.candidatos == ["5644355", "1170921"] and r.origen == TipoOrigenMatch.MISMO_MENSAJE


def test_album_de_mas_de_4_fotos_coincide_con_la_cita_de_6():
    msgs = [
        _m("Juan", "", adj=True, minutos=0, n=4),   # álbum de 6 mostrado con 4 miniaturas
        _m("Juan", "", adj=True, minutos=1, n=1),
        _m("Juan", "Aviso 5644355", minutos=2, cita_autor="Juan", cita_texto="6 fotos"),
    ]
    r = asociar_mensajes(msgs, PATRON)
    assert r[0].origen == TipoOrigenMatch.RESPUESTA and r[0].codigo == "5644355"


def test_limpiar_cita():
    from src.whatsapp.reader import _limpiar_cita
    assert _limpiar_cita("ic-image3 fotos") == "3 fotos"
    assert _limpiar_cita("ic-location-onUbicación") == "Ubicación"
    assert _limpiar_cita(None) is None


def test_rafaga_de_fotos_sueltas_hereda_el_numero_de_la_que_lo_trae():
    msgs = [
        _m("Luis", "", adj=True, minutos=0), _m("Luis", "", adj=True, minutos=0),
        _m("Luis", "Aviso 5643706", adj=True, minutos=0), _m("Luis", "", adj=True, minutos=1),
    ]
    r = asociar_mensajes(msgs, PATRON)
    assert [x.codigo for x in r] == ["5643706"] * 4
    assert [x.origen.value for x in r].count("rafaga") == 3


def test_rafaga_no_cruza_remitentes_ni_ventana():
    msgs = [
        _m("Luis", "Aviso 5643706", adj=True, minutos=0),
        _m("Pedro", "", adj=True, minutos=0),     # otro remitente
        _m("Luis", "", adj=True, minutos=10),     # fuera de 2 min
    ]
    r = asociar_mensajes(msgs, PATRON)
    assert r[1].origen == TipoOrigenMatch.SIN_CODIGO and r[2].origen == TipoOrigenMatch.SIN_CODIGO
