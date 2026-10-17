"""Tests del lector: parseo de hora (puro) y lectura contra HTML simulado (Chromium real, sin WhatsApp)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.whatsapp_reader import (
    construir_mensajes,
    leer_mensajes_recientes,
    parsear_hora,
    parsear_pre_plain_text,
    resolver_fecha_separador,
)


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("[3:45 PM, 10/15/2026] Juan Perez: ", (datetime(2026, 10, 15, 15, 45), "Juan Perez")),
        ("[12:05 AM, 10/15/2026] Ana: ", (datetime(2026, 10, 15, 0, 5), "Ana")),
        ("[15:45, 15/10/2026] +57 300 1234567: ", (datetime(2026, 10, 15, 15, 45), "+57 300 1234567")),
        ("[9:03 p. m., 4/10/2026] Luis: ", (datetime(2026, 10, 4, 21, 3), "Luis")),
        ("[15:45, 2026-10-15] Ana: ", (datetime(2026, 10, 15, 15, 45), "Ana")),
        ("[15:45, 13/13/2026] Ana: ", (None, None)),
        ("basura", (None, None)),
        (None, (None, None)),
    ],
)
def test_parsear_pre_plain_text(valor, esperado):
    assert parsear_pre_plain_text(valor) == esperado


HTML = """
<html><body><div data-testid="conversation-panel-messages">
  <div role="row"><div><div>Ayer</div></div></div>
  <div role="row"><div data-testid="conv-msg-A1" data-id="A1"><div data-virtualized="false">
    <span data-icon="tail-in"></span>
    <span data-testid="author">~ ..</span><span data-testid="author">+507 6000-0002</span>
    <div data-testid="image-thumb"></div>
    <div data-testid="msg-meta">7:26 p.m.</div></div></div></div>
  <div role="row"><div data-testid="conv-msg-B2" data-id="B2"><div data-virtualized="false">
    <span data-icon="tail-in"></span><span data-testid="author">Juan</span>
    <div data-pre-plain-text="[11:22 PM, 10/14/2026] Juan: "><span class="selectable-text">Incidencia 1168222</span></div>
    <div data-testid="image-thumb"></div><div data-testid="video-content"></div>
    <div data-testid="msg-meta">11:22 p.m.</div></div></div></div>
  <div role="row"><div data-testid="conv-msg-C3" data-id="C3"><div data-virtualized="true"><div></div></div></div></div>
  <div role="row"><div>Hoy</div></div>
  <div role="row"><div data-testid="conv-msg-D4" data-id="D4"><div data-virtualized="false">
    <span data-icon="tail-out"></span><span class="selectable-text">ok recibido</span>
    <div data-testid="msg-meta">8:05 a.m.</div></div></div></div>
</div></body></html>
"""


@pytest.fixture
def pagina():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium no disponible: {e}")
        page = browser.new_page()
        page.set_content(HTML)
        yield page
        browser.close()


def test_leer_mensajes_contra_dom_simulado(pagina):
    mensajes = leer_mensajes_recientes(pagina, max_mensajes=10, intentos_tope=0)
    assert [m.id_mensaje for m in mensajes] == ["A1", "B2", "D4"]  # el virtualizado se omite
    m0, m1, m2 = mensajes
    ayer = (datetime.now() - timedelta(days=1)).date()
    assert m0.timestamp.date() == ayer and (m0.timestamp.hour, m0.timestamp.minute) == (19, 26)
    assert m0.remitente == "+507 6000-0002" and m0.tipo_adjunto == "imagen"
    assert m1.timestamp == datetime(2026, 10, 14, 23, 22)  # de data-pre-plain-text
    assert "1168222" in m1.texto and m1.tiene_adjunto
    assert m2.remitente == "yo" and not m2.tiene_adjunto
    assert m2.timestamp.date() == datetime.now().date()


def test_resolver_fecha_separador():
    hoy = date(2026, 10, 15)  # jueves
    assert resolver_fecha_separador("Hoy", hoy) == hoy
    assert resolver_fecha_separador("Ayer", hoy) == date(2026, 10, 14)
    assert resolver_fecha_separador("martes", hoy) == date(2026, 10, 13)
    assert resolver_fecha_separador("jueves", hoy) == date(2026, 10, 8)
    assert resolver_fecha_separador("10/14/2026", hoy) == date(2026, 10, 14)
    assert resolver_fecha_separador("14/10/2026", hoy) == date(2026, 10, 14)
    assert resolver_fecha_separador("blah", hoy) is None


@pytest.mark.parametrize("txt, esp", [("7:26 p.m.", (19, 26)), ("12:05 a. m.", (0, 5)), ("19:26", (19, 26)), ("12:30 PM", (12, 30)), ("x", None), (None, None)])
def test_parsear_hora(txt, esp):
    assert parsear_hora(txt) == esp


def test_construir_mensajes_sin_fecha_cae_a_ahora():
    ahora = datetime(2026, 10, 15, 12, 0)
    ms = construir_mensajes([{"tipo": "msg", "id": "X", "hora": "7:00 p.m.", "texto": "", "fotos": 0, "videos": 1}], ahora)
    assert ms[0].timestamp == ahora and ms[0].tipo_adjunto == "video"


HTML_MODAL = """
<html><body><div id="app">contenido</div>
<div role="dialog" id="m" style="position:fixed;inset:0;background:#fff">
  <h1>Novedades en WhatsApp Web</h1>
  <button onclick="document.getElementById('m').remove()">Continuar</button>
</div></body></html>
"""


def test_cerrar_avisos_pulsa_continuar(pagina):
    from src.whatsapp_session import SesionWhatsApp
    pagina.set_content(HTML_MODAL)
    sesion = SesionWhatsApp("x")
    sesion.pagina = pagina
    assert sesion.cerrar_avisos() == 1
    assert pagina.locator('[role="dialog"]').count() == 0


def test_cerrar_avisos_sin_modal_no_hace_nada(pagina):
    from src.whatsapp_session import SesionWhatsApp
    sesion = SesionWhatsApp("x")
    sesion.pagina = pagina
    assert sesion.cerrar_avisos() == 0


HTML_CITA = """
<html><body><div data-testid="conversation-panel-messages">
  <div role="row"><div>Hoy</div></div>
  <div role="row"><div data-testid="conv-msg-P1" data-id="P1"><div data-virtualized="false">
    <span data-icon="tail-in"></span><span data-testid="author">+507 6000-0003</span>
    <div data-testid="media-album"><div data-testid="image-thumb"></div><div data-testid="image-thumb"></div></div>
    <div data-testid="msg-meta">9:00 p.m.</div></div></div></div>
  <div role="row"><div data-testid="conv-msg-R2" data-id="R2"><div data-virtualized="false">
    <span data-icon="tail-in"></span><span data-testid="author">+507 6000-0003</span>
    <div data-testid="quoted-message"><div role="button">
      <span data-testid="author">~Jonathan~</span><span data-testid="author">+507 6000-0003</span>
      <span>2 fotos</span></div></div>
    <span class="selectable-text">Aviso:5643040</span>
    <div data-testid="msg-meta">9:10 p.m.</div></div></div></div>
</div></body></html>
"""


def test_respuesta_con_cita_se_lee_bien_y_se_asocia(pagina):
    from src.matcher import asociar_mensajes
    pagina.set_content(HTML_CITA)
    ms = leer_mensajes_recientes(pagina, intentos_tope=0)
    assert len(ms) == 2
    assert ms[0].n_adjuntos == 2
    resp = ms[1]
    assert resp.remitente == "+507 6000-0003"       # quien escribe, no el autor citado
    assert resp.cita_autor == "+507 6000-0003" and resp.cita_texto == "2 fotos"
    assert resp.texto == "Aviso:5643040"            # sin el texto de la cita
    res = asociar_mensajes(ms, r"\b\d{6,8}\b")
    assert res[0].codigo == "5643040" and res[0].origen.value == "respuesta"


HTML_DIALOGO_DESCONOCIDO = """
<html><body><div id="chat">chat abierto</div>
<div role="dialog"><p>Algo raro sin botones conocidos</p></div></body></html>
"""


def test_cerrar_avisos_no_pulsa_escape_con_dialogo_desconocido(pagina):
    from src.whatsapp_session import SesionWhatsApp
    pagina.set_content(HTML_DIALOGO_DESCONOCIDO)
    pagina.evaluate("window.__escape = false; document.addEventListener('keydown', e => { if (e.key === 'Escape') window.__escape = true; })")
    sesion = SesionWhatsApp("x")
    sesion.pagina = pagina
    assert sesion.cerrar_avisos() == 0
    assert pagina.evaluate("window.__escape") is False


def test_leer_con_desde_filtra_mensajes_anteriores(pagina):
    from datetime import time
    desde = datetime.combine(datetime.now().date(), time(0, 0))  # solo lo de hoy
    ms = leer_mensajes_recientes(pagina, desde=desde, intentos_tope=0)
    assert [m.id_mensaje for m in ms] == ["D4"]


def test_leer_con_desde_inalcanzable_avisa_historico_incompleto(pagina, caplog):
    with caplog.at_level("WARNING", logger="incidencias_wa"):
        ms = leer_mensajes_recientes(pagina, desde=datetime(2020, 1, 1), intentos_tope=0)
    assert len(ms) == 3
    assert "HISTÓRICO INCOMPLETO" in caplog.text


@pytest.mark.parametrize("texto, esperado", [
    ("Se pausó la sincronización. Abre WhatsApp en tu teléfono para reanudarla.", "pausada"),
    ("Se están sincronizando mensajes más antiguos. Haz clic para ver el progreso.", "sincronizando"),
    ("Mensaje normal", None),
])
def test_estado_sincronizacion(pagina, texto, esperado):
    from src.whatsapp_reader import estado_sincronizacion
    pagina.set_content(f"<html><body><div>{texto}</div></body></html>")
    assert estado_sincronizacion(pagina) == esperado


def test_en_el_tope_pide_mas_antes_de_rendirse(pagina, caplog):
    with caplog.at_level("INFO", logger="incidencias_wa"):
        leer_mensajes_recientes(pagina, intentos_tope=2, espera_tope_seg=0.2)
    assert "intento 1/2" in caplog.text and "intento 2/2" in caplog.text


def test_fusionar_orden_solapado_y_en_cualquier_direccion():
    from src.whatsapp_reader import fusionar_orden
    o = fusionar_orden([], ["c", "d", "e"])
    assert o == ["c", "d", "e"]
    o = fusionar_orden(o, ["a", "b", "c", "d"])      # al subir: lo nuevo va antes
    assert o == ["a", "b", "c", "d", "e"]
    o = fusionar_orden(o, ["d", "e", "f", "g"])      # al bajar: lo nuevo va después
    assert o == ["a", "b", "c", "d", "e", "f", "g"]
    assert fusionar_orden(o, ["b", "c", "x", "d"]) == ["a", "b", "c", "x", "d", "e", "f", "g"]  # en medio
    assert fusionar_orden(o, ["a", "b"]) == o        # nada nuevo: no cambia


HTML_SCROLL = """
<html><body style="margin:0"><div data-testid="conversation-panel-messages" style="height:300px;overflow-y:auto">
""" + "".join(
    f'<div role="row"><div data-testid="conv-msg-M{i}" data-id="M{i}"><div data-virtualized="false">'
    f'<span data-icon="tail-in"></span><span data-testid="author">Juan</span>'
    f'<span class="selectable-text">msg {i}</span><div data-testid="msg-meta">9:{i % 60:02d} a.m.</div>'
    f'<div style="height:120px"></div></div></div></div>' for i in range(40)
) + "</div></body></html>"


def test_cosechar_recorre_de_arriba_a_abajo_sin_repetir(pagina):
    from src.whatsapp_reader import cosechar
    pagina.set_content(HTML_SCROLL.replace('<div role="row"><div data-testid="conv-msg-M0"', '<div role="row"><div>Ayer</div></div><div role="row"><div data-testid="conv-msg-M0"', 1))
    ms = cosechar(pagina, espera_paso_ms=30)
    assert [m.id_mensaje for m in ms] == [f"M{i}" for i in range(40)]


def test_cosechar_se_detiene_en_lo_ya_conocido(pagina):
    from src.whatsapp_reader import cosechar
    pagina.set_content(HTML_SCROLL)
    conocidos = {f"M{i}" for i in range(40)}
    cosechar(pagina, espera_paso_ms=30, ids_conocidos=conocidos)
    sobra = pagina.evaluate(
        "() => { const e = document.querySelector('[data-testid=\"conversation-panel-messages\"]'); return e.scrollHeight - e.clientHeight - e.scrollTop; }")
    assert sobra > 500  # cortó antes de llegar al fondo


def test_cargar_hacia_arriba_termina_cuando_no_llegan_tandas(pagina):
    from src.whatsapp_reader import cargar_hacia_arriba
    pagina.set_content(HTML_SCROLL)
    r = cargar_hacia_arriba(pagina, max_seg=40, ciclos_por_intento=1, intentos_sin_tanda=1, espera_circulo_seg=1, rueda_real=False)
    assert r["tandas"] == 0 and r["llego_desde"] is False


def test_cosechar_descarta_el_arranque_sin_fecha(pagina):
    from src.whatsapp_reader import cosechar
    html = ('<html><body><div data-testid="conversation-panel-messages" style="height:300px;overflow-y:auto">'
            + "".join(f'<div role="row"><div data-testid="conv-msg-S{i}" data-id="S{i}"><div data-virtualized="false">'
                      f'<span data-testid="author">Juan</span><span class="selectable-text">sin fecha {i}</span>'
                      f'<div data-testid="msg-meta">9:0{i} a.m.</div></div></div></div>' for i in range(3))
            + '<div role="row"><div>Ayer</div></div>'
            + "".join(f'<div role="row"><div data-testid="conv-msg-T{i}" data-id="T{i}"><div data-virtualized="false">'
                      f'<span data-testid="author">Juan</span><span class="selectable-text">con fecha {i}</span>'
                      f'<div data-testid="msg-meta">10:0{i} a.m.</div></div></div></div>' for i in range(3))
            + "</div></body></html>")
    pagina.set_content(html)
    ids = [m.id_mensaje for m in cosechar(pagina, espera_paso_ms=30)]
    assert ids == ["T0", "T1", "T2"]  # los S* quedan fuera: no se sabe de qué día son
