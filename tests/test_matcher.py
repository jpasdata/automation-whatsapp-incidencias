from datetime import datetime, timedelta

from src.matcher import asociar_mensajes, extraer_codigo
from src.modelos import Mensaje, TipoOrigenMatch

PATRON = r"\b\d{6,8}\b"


def _msg(remitente, texto, tiene_adjunto, minutos_offset=0, tipo_adjunto=None):
    base = datetime(2026, 10, 15, 10, 0, 0)
    return Mensaje(
        remitente=remitente,
        timestamp=base + timedelta(minutes=minutos_offset),
        texto=texto,
        tiene_adjunto=tiene_adjunto,
        tipo_adjunto=tipo_adjunto,
    )


def test_extraer_codigo_encuentra_numero_en_texto():
    assert extraer_codigo("la incidencia es 1168222 ya revisada", PATRON) == "1168222"


def test_extraer_codigo_sin_texto_devuelve_none():
    assert extraer_codigo(None, PATRON) is None
    assert extraer_codigo("", PATRON) is None


def test_extraer_codigo_ignora_numeros_demasiado_cortos():
    # un número de 3 dígitos no debe confundirse con un código de incidencia
    assert extraer_codigo("llegué a las 14:30 hrs", PATRON) is None


def test_caso_1_codigo_en_el_mismo_mensaje_que_la_foto():
    mensajes = [_msg("Juan", "incidencia 1168222", tiene_adjunto=True)]
    resultados = asociar_mensajes(mensajes, PATRON)

    assert len(resultados) == 1
    assert resultados[0].codigo == "1168222"
    assert resultados[0].origen == TipoOrigenMatch.MISMO_MENSAJE


def test_caso_2_codigo_en_mensaje_de_texto_separado_antes_de_la_foto():
    mensajes = [
        _msg("Juan", "mira, esta es la incidencia 1166339", tiene_adjunto=False, minutos_offset=0),
        _msg("Juan", None, tiene_adjunto=True, minutos_offset=2),
    ]
    resultados = asociar_mensajes(mensajes, PATRON, ventana_minutos=15)

    assert len(resultados) == 1
    assert resultados[0].codigo == "1166339"
    assert resultados[0].origen == TipoOrigenMatch.MENSAJE_CERCANO


def test_caso_2_varias_fotos_seguidas_usan_el_mismo_codigo_de_texto_previo():
    mensajes = [
        _msg("Juan", "incidencia 1166339", tiene_adjunto=False, minutos_offset=0),
        _msg("Juan", None, tiene_adjunto=True, minutos_offset=1),
        _msg("Juan", None, tiene_adjunto=True, minutos_offset=2),
    ]
    resultados = asociar_mensajes(mensajes, PATRON)

    assert len(resultados) == 2
    assert all(r.codigo == "1166339" for r in resultados)
    assert all(r.origen == TipoOrigenMatch.MENSAJE_CERCANO for r in resultados)


def test_caso_3_foto_sin_ningun_codigo_cercano():
    mensajes = [_msg("Juan", None, tiene_adjunto=True)]
    resultados = asociar_mensajes(mensajes, PATRON)

    assert len(resultados) == 1
    assert resultados[0].codigo is None
    assert resultados[0].origen == TipoOrigenMatch.SIN_CODIGO


def test_mensaje_de_texto_fuera_de_la_ventana_de_tiempo_no_se_asocia():
    mensajes = [
        _msg("Juan", "incidencia 1166339", tiene_adjunto=False, minutos_offset=0),
        _msg("Juan", None, tiene_adjunto=True, minutos_offset=30),  # 30 min > ventana de 15
    ]
    resultados = asociar_mensajes(mensajes, PATRON, ventana_minutos=15)

    assert resultados[0].origen == TipoOrigenMatch.SIN_CODIGO


def test_mensaje_de_otro_remitente_no_se_asocia():
    mensajes = [
        _msg("Juan", "incidencia 1166339", tiene_adjunto=False, minutos_offset=0),
        _msg("Pedro", None, tiene_adjunto=True, minutos_offset=1),
    ]
    resultados = asociar_mensajes(mensajes, PATRON)

    assert resultados[0].origen == TipoOrigenMatch.SIN_CODIGO


def test_mensajes_sin_adjunto_se_ignoran_en_el_resultado():
    mensajes = [
        _msg("Juan", "hola buenas tardes", tiene_adjunto=False),
        _msg("Juan", "otro texto cualquiera", tiene_adjunto=False),
    ]
    resultados = asociar_mensajes(mensajes, PATRON)
    assert resultados == []


def test_orden_de_mensajes_no_cronologico_se_corrige_internamente():
    # El segundo mensaje llega "antes" en la lista pero es cronológicamente después
    mensajes = [
        _msg("Juan", None, tiene_adjunto=True, minutos_offset=5),
        _msg("Juan", "incidencia 1166339", tiene_adjunto=False, minutos_offset=0),
    ]
    resultados = asociar_mensajes(mensajes, PATRON)

    assert len(resultados) == 1
    assert resultados[0].codigo == "1166339"
