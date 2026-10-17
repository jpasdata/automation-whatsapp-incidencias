"""
Lectura de mensajes, participantes y descarga de adjuntos desde la
página de WhatsApp Web ya abierta (ver whatsapp_session.py).

La estructura del DOM usada aquí se verificó en vivo el 2026-10-15
(burbujas `conv-msg-*`, `author`, `image-thumb`, `msg-meta`, separadores
de fecha). WhatsApp Web cambia su HTML de vez en cuando: si deja de
funcionar, el primer sospechoso es un cambio de interfaz, y el log dice
en qué paso falló. La lógica de interpretación (horas, fechas, armado de
mensajes) es pura y está cubierta por tests; solo `_JS_LEER_CHAT` y los
selectores dependen del HTML real.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from playwright.sync_api import Locator, Page

from .modelos import Mensaje
from .whatsapp_session import SELECTORES

logger = logging.getLogger("incidencias_wa")


def listar_participantes(pagina: Page) -> list[dict[str, str]]:
    """
    Abre el panel de datos del grupo y devuelve [{"nombre": ..., "telefono_o_dato": ...}, ...].

    Limitación real de WhatsApp Web (no de este script): si el contacto
    ya está guardado en la agenda del teléfono vinculado, WhatsApp Web
    muestra el NOMBRE guardado, no el número. Si no está guardado,
    muestra el número. Por eso el campo se llama "telefono_o_dato": hay
    que revisar a mano cuál de las dos cosas salió para cada persona.
    """
    logger.info("Abriendo panel de participantes del grupo...")
    pagina.locator(SELECTORES["boton_menu_grupo"]).first.click()
    pagina.wait_for_selector(SELECTORES["lista_participantes"], timeout=10_000)

    participantes = []
    filas = pagina.locator(SELECTORES["lista_participantes"]).all()
    logger.info("Se encontraron %d filas en el panel de participantes.", len(filas))

    for fila in filas:
        texto = fila.inner_text().strip()
        if not texto:
            continue
        primera_linea = texto.splitlines()[0]
        participantes.append({"nombre": primera_linea, "texto_completo": texto})

    return participantes


# --- Interpretación de horas y fechas (lógica pura) --------------------

_PATRON_PRE_PLAIN = re.compile(
    r"\[(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp])?\.?\s*[Mm]?\.?,\s*(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})\]\s*(.*?):\s*$"
)
_PATRON_HORA = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp])?\.?\s*[Mm]?\.?")
_DIAS_SEMANA = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}


def _fecha_numerica(a: int, b: int, c: int) -> date | None:
    """a/b/c en aaaa-mm-dd, dd/mm/aaaa o mm/dd/aaaa. Si es ambiguo se asume día/mes (es-CO)."""
    if a > 31:
        anio, mes, dia = a, b, c
    else:
        anio = c + 2000 if c < 100 else c
        dia, mes = (b, a) if (a <= 12 and b > 12) else (a, b)
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def parsear_pre_plain_text(valor: str | None) -> tuple[datetime | None, str | None]:
    """
    Interpreta el atributo `data-pre-plain-text` que WhatsApp Web pone en
    el texto de un mensaje, p. ej. "[3:45 PM, 10/15/2026] Juan Perez: "
    o "[15:45, 15/10/2026] Juan: ". Devuelve (hora_de_envio, remitente);
    None en lo que no se pueda leer.
    """
    if not valor:
        return None, None
    m = _PATRON_PRE_PLAIN.search(valor.strip())
    if not m:
        return None, None
    hora, minuto, ampm, a, b, c, remitente = m.groups()
    hora, minuto = int(hora), int(minuto)
    if ampm:
        hora = hora % 12 + (12 if ampm.lower() == "p" else 0)
    fecha = _fecha_numerica(int(a), int(b), int(c))
    if fecha is None or hora > 23 or minuto > 59:
        return None, None
    return datetime(fecha.year, fecha.month, fecha.day, hora, minuto), (remitente.strip() or None)


def resolver_fecha_separador(texto: str, hoy: date | None = None) -> date | None:
    """Convierte un separador de fecha ("Hoy", "Ayer", "miércoles", "10/14/2026") en date."""
    hoy = hoy or datetime.now().date()
    t = (texto or "").strip().lower()
    if t in ("hoy", "today"):
        return hoy
    if t in ("ayer", "yesterday"):
        return hoy - timedelta(days=1)
    if t in _DIAS_SEMANA:  # WhatsApp solo usa el nombre del día dentro de la última semana
        atras = (hoy.weekday() - _DIAS_SEMANA[t]) % 7 or 7
        return hoy - timedelta(days=atras)
    m = re.fullmatch(r"(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})", t)
    return _fecha_numerica(*(int(x) for x in m.groups())) if m else None


def parsear_hora(texto: str | None) -> tuple[int, int] | None:
    """"7:26 p.m." / "19:26" -> (19, 26); None si no se entiende."""
    if not texto:
        return None
    m = _PATRON_HORA.search(texto)
    if not m:
        return None
    h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if ampm:
        h = h % 12 + (12 if ampm.lower() == "p" else 0)
    return (h, mi) if h < 24 and mi < 60 else None


def _limpiar_cita(texto: str | None) -> str | None:
    """Quita los nombres de ícono que se cuelan en el texto de la cita ("ic-image3 fotos" -> "3 fotos")."""
    if not texto:
        return None
    return re.sub(r"\bic-[a-z\-]+", " ", texto).strip() or None


def construir_mensajes(items: list[dict], ahora: datetime | None = None) -> list[Mensaje]:
    """
    Convierte lo que devuelve _JS_LEER_CHAT (separadores de fecha y burbujas,
    en orden) en Mensajes. La hora sale de data-pre-plain-text si existe
    (trae fecha completa); si no, de la hora "7:26 p.m." de la burbuja más el
    último separador de fecha visto.
    """
    ahora = ahora or datetime.now()
    mensajes: list[Mensaje] = []
    fecha_actual: date | None = None

    for it in items:
        if it["tipo"] == "fecha":
            fecha_actual = resolver_fecha_separador(it["texto"], ahora.date()) or fecha_actual
            continue

        if it.get("fecha"):  # fecha propia de la burbuja; si no hay, se arrastra la del mensaje anterior
            fecha_actual = resolver_fecha_separador(it["fecha"], ahora.date()) or fecha_actual

        ts, remitente_pre = parsear_pre_plain_text(it.get("pre"))
        if ts is None:
            hm = parsear_hora(it.get("hora"))
            if hm and fecha_actual:
                ts = datetime(fecha_actual.year, fecha_actual.month, fecha_actual.day, hm[0], hm[1])
        if ts is None:
            logger.warning("Mensaje %s sin hora determinable; se usa la hora actual.", it.get("id"))

        fotos, videos = it.get("fotos") or 0, it.get("videos") or 0
        tipo = None
        if fotos or videos:
            tipo = "video" if videos and not fotos else "imagen"
        remitente = "yo" if it.get("saliente") else (it.get("autor") or remitente_pre or "desconocido")
        mensajes.append(
            Mensaje(
                remitente=remitente,
                timestamp=ts or ahora,
                texto=it.get("texto") or None,
                tiene_adjunto=tipo is not None,
                tipo_adjunto=tipo,
                id_mensaje=it.get("id"),
                n_adjuntos=fotos + videos,
                cita_autor=it.get("citaAutor"),
                cita_texto=_limpiar_cita(it.get("citaTexto")),
            )
        )
    return mensajes


# --- Lectura del chat abierto (depende del HTML real) -------------------

# Una sola llamada al navegador: devuelve, en orden de aparición, los separadores
# de fecha ("Hoy", "Ayer", "miércoles", "10/14/2026") y las burbujas YA renderizadas.
# WhatsApp Web virtualiza la lista (solo pinta lo visible), por eso se salta lo
# marcado data-virtualized="true".
_JS_LEER_CHAT = r"""() => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return [];
  const RX = /^(hoy|ayer|today|yesterday|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4})$/i;
  const items = [];
  for (const el of panel.querySelectorAll('div,span')) {
    if (el.children.length === 0 && RX.test((el.textContent || '').trim()) && !el.closest('[data-testid^="conv-msg-"]')) {
      items.push({el, tipo: 'fecha', texto: el.textContent.trim()});
    }
  }
  for (const el of panel.querySelectorAll('[data-testid^="conv-msg-"]')) {
    if (el.querySelector('[data-virtualized="true"]')) continue;
    // La cita ("quoted-message") trae su propio autor y texto: se separa para no
    // confundirlos con los del mensaje que escribe la respuesta.
    const cita = el.querySelector('[data-testid="quoted-message"]');
    const fuera = e => !cita || !cita.contains(e);
    const autores = [...el.querySelectorAll('[data-testid="author"]')].filter(fuera).map(e => e.innerText.trim()).filter(Boolean);
    let citaAutor = null, citaTexto = null;
    if (cita) {
      const aut = [...cita.querySelectorAll('[data-testid="author"]')].map(e => e.innerText.trim()).filter(Boolean);
      citaAutor = aut.length ? aut[aut.length - 1] : null;
      const copia = cita.cloneNode(true);
      copia.querySelectorAll('[data-testid="author"]').forEach(n => n.remove());
      citaTexto = copia.textContent.replace(/\s+/g, ' ').trim() || null;
    }
    const pre = el.querySelector('[data-pre-plain-text]');
    const meta = el.querySelector('[data-testid="msg-meta"]');
    // Fecha propia: último separador que PRECEDE a esta burbuja en el DOM (los
    // separadores también se virtualizan, así que no se puede depender de ellos aparte).
    const previos = items.filter(i => i.tipo === 'fecha' && (i.el.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
    const fecha = previos.length ? previos[previos.length - 1].texto : null;
    items.push({
      el, tipo: 'msg', id: el.dataset.id, fecha,
      saliente: !!el.querySelector('[data-icon="tail-out"]'),
      autor: autores.length ? autores[autores.length - 1] : null,
      hora: meta ? meta.innerText : null,
      pre: pre ? pre.getAttribute('data-pre-plain-text') : null,
      texto: [...el.querySelectorAll('span.selectable-text, [data-testid="selectable-text"]')].filter(fuera).map(e => e.innerText).join('\n').trim(),
      citaAutor, citaTexto,
      fotos: el.querySelectorAll('[data-testid="image-thumb"]').length,
      videos: el.querySelectorAll('[data-testid="video-thumb"], [data-testid="video-content"]').length,
    });
  }
  items.sort((a, b) => (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
  return items.map(({el, ...resto}) => resto);
}"""


# Sube el panel de mensajes un tramo (80 % de su alto). Devuelve si ya está arriba del todo.
_JS_SCROLL_ARRIBA = r"""() => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return true;
  const candidatos = [panel, ...panel.querySelectorAll('div'), ...(() => { const a = []; let p = panel.parentElement; while (p) { a.push(p); p = p.parentElement; } return a; })()];
  const esScroll = e => e.scrollHeight > e.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(e).overflowY);
  const el = candidatos.filter(esScroll).sort((a, b) => b.clientHeight - a.clientHeight)[0];
  if (!el) return true;
  el.scrollTop = Math.max(0, el.scrollTop - el.clientHeight * 0.8);
  return el.scrollTop <= 1;
}"""


# Al llegar arriba WhatsApp pide al celular los mensajes anteriores, pero solo si el scroll
# "toca" el tope de nuevo: se baja un poco y se vuelve a subir.
_JS_SACUDIR_TOPE = r"""() => {
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return false;
  const candidatos = [panel, ...panel.querySelectorAll('div'), ...(() => { const a = []; let p = panel.parentElement; while (p) { a.push(p); p = p.parentElement; } return a; })()];
  const esScroll = e => e.scrollHeight > e.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(e).overflowY);
  const el = candidatos.filter(esScroll).sort((a, b) => b.clientHeight - a.clientHeight)[0];
  if (!el) return false;
  el.scrollTop = Math.min(el.scrollHeight, 400);
  return true;
}"""


_JS_CONTAR_BURBUJAS = """() => document.querySelectorAll('[data-testid^="conv-msg-"]').length"""


def _esperar_burbujas_nuevas(pagina: Page, antes: int, max_seg: float) -> bool:
    """Sondea cada 0,5 s si aparecieron más burbujas que `antes`; corta apenas llegan. True si llegaron."""
    limite = time.time() + max_seg
    while time.time() < limite:
        pagina.wait_for_timeout(500)
        try:
            if pagina.evaluate(_JS_CONTAR_BURBUJAS) > antes:
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


def _sacudir_con_rueda(pagina: Page, rueda_real: bool = True, solo_subir: bool = False) -> None:
    """
    Scroll humano para que WhatsApp pida más mensajes al celular (ver src/rueda.py): rueda real
    del sistema operativo si se puede, o la de Playwright como plan B.
    """
    from .rueda import sacudir_humano

    metodo = sacudir_humano(pagina, rueda_real, solo_subir)
    logger.debug("sacudida hecha con rueda %s", metodo)


# Encuentra el contenedor que scrollea y lo mueve: arriba del todo / un tramo hacia abajo.
_JS_SCROLLER = r"""
  const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!panel) return null;
  const candidatos = [panel, ...panel.querySelectorAll('div'), ...(() => { const a = []; let p = panel.parentElement; while (p) { a.push(p); p = p.parentElement; } return a; })()];
  const esScroll = e => e.scrollHeight > e.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(e).overflowY);
  const el = candidatos.filter(esScroll).sort((a, b) => b.clientHeight - a.clientHeight)[0];
  if (!el) return null;
"""
_JS_IR_ARRIBA = "() => {" + _JS_SCROLLER + " el.scrollTop = 0; return true; }"
# baja un tramo (80 % de la pantalla); devuelve true si ya está abajo del todo
# sube 2,5 pantallas por paso (subida RÁPIDA hasta el tope); devuelve true si ya está arriba del todo
_JS_SUBIR_TRAMO = "(f) => {" + _JS_SCROLLER + " el.scrollTop = Math.max(0, el.scrollTop - el.clientHeight * f); return el.scrollTop <= 1; }"
_JS_BAJAR_TRAMO = "() => {" + _JS_SCROLLER + " el.scrollTop += el.clientHeight * 0.8; return el.scrollTop + el.clientHeight >= el.scrollHeight - 4; }"


def _subir_rapido_al_tope(pagina: Page, max_pasos: int = 300) -> None:
    """
    Sube hasta el tope con eventos de scroll reales, a velocidad y pausas VARIABLES (1,2 a 2,6 pantallas
    por paso, 70-260 ms entre pasos, con alguna pausa de "mirar"), para que no se vea mecánico.
    """
    for _ in range(max_pasos):
        try:
            if pagina.evaluate(_JS_SUBIR_TRAMO, random.uniform(1.2, 2.6)):
                return
        except Exception:  # noqa: BLE001
            return
        pagina.wait_for_timeout(int(random.uniform(70, 260)))
        if random.random() < 0.06:
            pagina.wait_for_timeout(int(random.uniform(300, 900)))


def _calentar(presion, ciclos: int | None = None) -> None:
    """
    Calentamiento inicial como el de una persona que mueve el scroll varias veces para ver el
    chat: empuja hacia arriba unos segundos, mira, baja un poco, sube otra vez...
    """
    for _ in range(ciclos or random.randint(3, 5)):
        fin = time.time() + random.uniform(1.5, 4.0)
        while time.time() < fin:
            presion.rafaga_humana()
        time.sleep(random.uniform(0.4, 1.2))
        for _ in range(random.randint(3, 8)):
            presion.muesca_abajo()
            time.sleep(random.uniform(0.02, 0.06))
        time.sleep(random.uniform(0.3, 0.9))


_JS_HAY_CIRCULO = """() => !!document.querySelector('[data-testid="conversation-panel-messages"] [data-testid="loading-spinner"]')"""


def cargar_hacia_arriba(
    pagina: Page,
    desde: datetime | None = None,
    max_seg: float = 600,
    ciclos_por_intento: int = 8,
    intentos_sin_tanda: int = 3,
    espera_circulo_seg: float = 8,
    rueda_real: bool = True,
    al_progreso: Callable[[dict], None] | None = None,
    al_tanda: Callable[[], None] | None = None,
) -> dict:
    """
    FASE 1 (sin leer). Hace lo que una persona (grabación real + prueba a mano): el círculo de carga solo
    sale al BAJAR con la rueda y volver a subir, así que en vez de esperar quieto arriba se repite
    activamente el ciclo "bajar ~1-2 pantallas, volver a subir al tope":
      - si tras un ciclo aparece el círculo (`loading-spinner`), se espera mientras gira (hasta
        `espera_circulo_seg`) a que lleguen las burbujas;
      - si llegan burbujas nuevas (una tanda), se sube rápido al nuevo tope y se sigue;
      - si no pasa nada, se repite el ciclo de inmediato (sin esperas de 25 s).
    Un "intento" son `ciclos_por_intento` ciclos sin tanda; tras `intentos_sin_tanda` intentos
    seguidos sin tanda se da por terminado. Para al llegar a `desde` o al agotar `max_seg`.
    Devuelve {"llego_desde", "burbujas", "segundos", "tandas", "ciclos"}.
    """
    from .rueda import PresionContinua, ciclo_bajar_y_subir

    t0 = time.time()
    ahora = datetime.now()
    tandas = ciclos = sin_tanda = 0
    llego = False
    presion = PresionContinua(pagina, rueda_real)
    _calentar(presion)

    def conteo() -> int:
        return pagina.evaluate(_JS_CONTAR_BURBUJAS)

    def salida() -> dict:
        try:
            n = conteo()
        except Exception:  # noqa: BLE001
            n = 0
        try:  # hasta qué día subió: el primer mensaje con fecha de lo que hay pintado en el tope
            pagina.evaluate(_JS_IR_ARRIBA)
            pagina.wait_for_timeout(500)
            tope = next((i for i in leer_instantanea(pagina) if i.get("fecha")), None)
            mas_antigua = str(resolver_fecha_separador(tope["fecha"], ahora.date())) if tope else None
        except Exception:  # noqa: BLE001
            mas_antigua = None
        return {"llego_desde": llego, "burbujas": n, "segundos": round(time.time() - t0), "tandas": tandas,
                "ciclos": ciclos, "mas_antigua_en_tope": mas_antigua}

    try:
        while time.time() - t0 < max_seg and sin_tanda < intentos_sin_tanda:
            _subir_rapido_al_tope(pagina)
            antes = conteo()
            llegó = False
            for _ in range(ciclos_por_intento):
                if time.time() - t0 >= max_seg:
                    break
                ciclo_bajar_y_subir(presion)
                ciclos += 1
                _subir_rapido_al_tope(pagina)  # por si la rueda no alcanzó el tope exacto
                # ¿giró el círculo o ya hay burbujas nuevas? esperar solo mientras gira
                limite = time.time() + 1.5
                while time.time() < limite and conteo() <= antes and not pagina.evaluate(_JS_HAY_CIRCULO):
                    pagina.wait_for_timeout(250)
                if pagina.evaluate(_JS_HAY_CIRCULO) and conteo() <= antes:
                    limite = time.time() + espera_circulo_seg
                    while time.time() < limite and conteo() <= antes:
                        pagina.wait_for_timeout(250)
                if conteo() > antes:
                    llegó = True
                    break
            if llegó:
                tandas += 1
                sin_tanda = 0
                if al_tanda:  # Web solo conserva ~100 mensajes pintados: guardar cada tanda al llegar
                    try:
                        al_tanda()
                    except Exception as e:  # noqa: BLE001
                        if "closed" in str(e).lower():
                            raise
                        logger.warning("No se pudo cosechar la tanda: %s", e)
                if desde is not None:
                    items = leer_instantanea(pagina)
                    fecha = next((resolver_fecha_separador(i["fecha"], ahora.date()) for i in items if i.get("fecha")), None)
                    if fecha is not None and fecha < desde.date():
                        llego = True
                        break
            else:
                sin_tanda += 1
            if al_progreso:
                al_progreso({"tandas": tandas, "burbujas": conteo(), "sin_tanda": sin_tanda, "ciclos": ciclos,
                             "segundos": round(time.time() - t0)})
    except Exception as e:  # noqa: BLE001 - ventana cerrada durante la carga
        if "closed" not in str(e).lower():
            raise
    return salida()


def cosechar(
    pagina: Page,
    max_pasos: int = 4000,
    espera_paso_ms: int = 450,
    al_progreso: Callable[[dict], None] | None = None,
    ids_conocidos: set[str] | None = None,
) -> list[Mensaje]:
    """
    FASE 2: con todo ya cargado, recorre el chat de ARRIBA hacia ABAJO una sola vez leyendo lo
    que se va pintando (la lista es virtual: solo se pinta lo visible). Devuelve los mensajes
    en orden cronológico, sin repetir.
    """
    acumulado: dict[str, dict] = {}
    orden: list[str] = []
    pagina.evaluate(_JS_IR_ARRIBA)
    pagina.wait_for_timeout(800)
    for paso in range(1, max_pasos + 1):
        items = leer_instantanea(pagina)
        for it in items:
            previo = acumulado.get(it["id"])
            if previo is None:
                acumulado[it["id"]] = it
            elif not previo.get("fecha") and it.get("fecha"):
                previo["fecha"] = it["fecha"]
        orden = fusionar_orden(orden, [it["id"] for it in items])
        if al_progreso and paso % 25 == 0:
            al_progreso({"paso": paso, "leidos": len(orden)})
        if ids_conocidos and items and paso > 3 and all(it["id"] in ids_conocidos for it in items):
            break  # de aquí hacia abajo ya está todo indexado
        abajo = pagina.evaluate(_JS_BAJAR_TRAMO)
        pagina.wait_for_timeout(espera_paso_ms)
        if abajo:
            for it in leer_instantanea(pagina):  # última pantalla
                acumulado.setdefault(it["id"], it)
            orden = fusionar_orden(orden, [it["id"] for it in leer_instantanea(pagina)])
            break
    # Los primeros mensajes sin fecha conocida se descartan (usar la hora actual los dataría mal):
    # su separador de día aparece al cargarse lo anterior y entonces se cosechan bien.
    primero = next((k for k, i in enumerate(orden) if acumulado[i].get("fecha")), None)
    if primero is None:
        return []
    return construir_mensajes([acumulado[i] for i in orden[primero:]])


def _esperar_conteo_estable(pagina: Page, max_segundos: int = 12) -> None:
    """Espera a que deje de cambiar la cantidad de burbujas pintadas (el chat sigue cargando)."""
    anterior = -1
    for _ in range(max_segundos):
        actual = pagina.locator('[data-testid^="conv-msg-"] [data-virtualized="false"]').count()
        if actual == anterior and actual > 0:
            return
        anterior = actual
        pagina.wait_for_timeout(1000)


_RX_SINCRONIZACION = (
    "text=/sincronizando mensajes|syncing older messages|"
    "se paus[oó] la sincronizaci[oó]n|sync(hronization)? (was )?paused/i"
)


def estado_sincronizacion(pagina: Page) -> str | None:
    """
    Qué dice WhatsApp sobre el histórico: "sincronizando" (bajándolo desde el
    celular), "pausada" (el celular tiene que abrir WhatsApp para reanudarla)
    o None si no muestra ningún aviso.
    """
    try:
        loc = pagina.locator(_RX_SINCRONIZACION)
        if loc.count() == 0:
            return None
        texto = (loc.first.inner_text(timeout=1000) or "").lower()
    except Exception:  # noqa: BLE001
        return None
    return "pausada" if ("paus" in texto) else "sincronizando"


def fusionar_orden(orden: list[str], snapshot: list[str]) -> list[str]:
    """
    Mete en `orden` (cronológico) los ids de una instantánea (también cronológica) que aún no
    estén, colocándolos junto a sus vecinos de esa instantánea. Sirve cuando el chat se recorre
    en cualquier dirección (arriba/abajo a mano) y las instantáneas se solapan.
    """
    orden = list(orden)
    pos = {i: k for k, i in enumerate(orden)}
    previo: str | None = None
    for id_ in snapshot:
        if id_ not in pos:
            if previo is not None:
                idx = pos[previo] + 1
            else:
                # sin vecino anterior: va antes del primer conocido de la instantánea (o al final si no hay ninguno)
                siguiente = next((x for x in snapshot if x in pos), None)
                idx = pos[siguiente] if siguiente is not None else len(orden)
            orden.insert(idx, id_)
            pos = {i: k for k, i in enumerate(orden)}
        previo = id_
    return orden


def leer_instantanea(pagina: Page) -> list[dict]:
    """Burbujas renderizadas ahora mismo (en orden de pantalla), sin mover el scroll."""
    return [it for it in pagina.evaluate(_JS_LEER_CHAT) if it["tipo"] == "msg"]


def _historial_sincronizando(pagina: Page) -> bool:
    """True si hay algún aviso de sincronización (en curso o pausada)."""
    return estado_sincronizacion(pagina) is not None


def _fecha_mas_antigua(acumulado: dict[str, dict], orden: list[str], ahora: datetime) -> date | None:
    for id_ in orden[:5]:
        f = acumulado[id_].get("fecha")
        if f:
            return resolver_fecha_separador(f, ahora.date())
    return None


def leer_mensajes_recientes(
    pagina: Page,
    max_mensajes: int = 5000,
    max_pasos: int = 400,
    desde: datetime | None = None,
    espera_sync_seg: int = 15,
    intentos_tope: int = 4,
    espera_tope_seg: float = 25,
    rueda_real: bool = True,
    ids_conocidos: set[str] | None = None,
    al_progreso: Callable[[dict], None] | None = None,
    al_lote: Callable[[list[Mensaje]], None] | None = None,
    cada_lote: int = 20,
) -> list[Mensaje]:
    """
    Lee el chat abierto subiendo hasta `desde` (p. ej. el 1 de octubre), hasta
    juntar `max_mensajes`, llegar al principio o dejar de aparecer mensajes.

    WhatsApp Web solo pinta lo visible (lista virtualizada), así que se
    sube de a tramos acumulando las burbujas por id. IMPORTANTE: en un
    dispositivo vinculado hace poco, el histórico se baja desde el celular
    poco a poco ("Se están sincronizando mensajes más antiguos"). Si se
    llega arriba y ese aviso sigue, se espera hasta `espera_sync_seg`
    segundos a que llegue más; si aun así no se alcanza `desde`, se avisa
    en el log que el histórico está INCOMPLETO (hay que volver a correr
    cuando termine de sincronizar, con el celular conectado a internet).

    Paciencia en el tope: WhatsApp Web trae los mensajes anteriores a pedido
    (cuando el scroll llega arriba) y el celular tarda en contestar. Al llegar
    arriba sin novedades se "sacude" el scroll y se espera `espera_tope_seg`,
    hasta `intentos_tope` veces seguidas, antes de darlo por terminado.

    Carga incremental: si se pasa `ids_conocidos` (los ya indexados) y una
    pantalla entera de mensajes ya es conocida, se deja de subir: no hay
    nada más nuevo por leer. Solo usarlo cuando el índice ya cubre `desde`.
    `al_progreso(info)` se llama en cada paso (para mostrar avance) y
    `al_lote(mensajes)` cada `cada_lote` pasos para ir guardando lo leído.
    """
    ahora = datetime.now()
    try:  # el chat recién abierto tarda en pintar las burbujas; sin esto a veces se lee 0
        pagina.wait_for_selector('[data-testid^="conv-msg-"] [data-virtualized="false"]', timeout=8_000)
    except Exception:  # noqa: BLE001 - chat vacío o aún sincronizando: se lee lo que haya
        logger.warning("No aparecieron mensajes renderizados en 8 s; puede ser un chat vacío o aún sincronizando.")

    _esperar_conteo_estable(pagina)

    acumulado: dict[str, dict] = {}
    orden: list[str] = []  # cronológico: lo que aparece al subir se antepone
    pasos_sin_nuevos = 0
    espera_acum = 0
    intentos_usados = 0
    alcanzo_desde = False
    for paso in range(1, max_pasos + 1):
        nuevos: list[str] = []
        visibles: list[str] = []
        for it in pagina.evaluate(_JS_LEER_CHAT):
            if it["tipo"] != "msg":
                continue
            visibles.append(it["id"])
            if it["id"] in acumulado:
                if not acumulado[it["id"]].get("fecha") and it.get("fecha"):
                    acumulado[it["id"]]["fecha"] = it["fecha"]  # ahora sí se vio su separador
            else:
                acumulado[it["id"]] = it
                nuevos.append(it["id"])
        orden = nuevos + orden
        if nuevos:
            intentos_usados = 0
        if al_progreso:
            al_progreso({
                "paso": paso, "acumulados": len(orden), "nuevos": len(nuevos), "espera": espera_acum,
                "mas_antigua": _fecha_mas_antigua(acumulado, orden, ahora),
            })
        if al_lote and paso % cada_lote == 0:
            al_lote(construir_mensajes([acumulado[i] for i in orden]))
        if ids_conocidos and visibles and all(i in ids_conocidos for i in visibles):
            alcanzo_desde = True  # ya está todo indexado de aquí hacia atrás
            logger.info("Se llegó a mensajes ya indexados; no hay más nuevos que leer.")
            break
        if len(orden) >= max_mensajes:
            break
        if desde is not None:
            antigua = _fecha_mas_antigua(acumulado, orden, ahora)
            if antigua is not None and antigua < desde.date():
                alcanzo_desde = True
                break
        arriba = pagina.evaluate(_JS_SCROLL_ARRIBA)
        pagina.wait_for_timeout(900)  # deja que WhatsApp pinte lo nuevo
        pasos_sin_nuevos = 0 if nuevos else pasos_sin_nuevos + 1
        if pasos_sin_nuevos >= 2 or (arriba and not nuevos):
            if _historial_sincronizando(pagina) and espera_acum < espera_sync_seg:
                if estado_sincronizacion(pagina) == "pausada":
                    logger.warning("La sincronización está PAUSADA: abre WhatsApp en el teléfono (con internet) para reanudarla. (%ds/%ds)", espera_acum, espera_sync_seg)
                else:
                    logger.info("Esperando que WhatsApp termine de sincronizar el histórico (%ds/%ds)...", espera_acum, espera_sync_seg)
                pagina.wait_for_timeout(3000)
                espera_acum += 3
                pasos_sin_nuevos = 0
                continue
            if intentos_usados < intentos_tope:
                intentos_usados += 1
                logger.info("En el tope sin mensajes nuevos: pido más al celular (intento %d/%d)...", intentos_usados, intentos_tope)
                antes = pagina.evaluate(_JS_CONTAR_BURBUJAS)
                _sacudir_con_rueda(pagina, rueda_real)
                pagina.evaluate(_JS_SCROLL_ARRIBA)
                _esperar_burbujas_nuevas(pagina, antes, espera_tope_seg)
                pasos_sin_nuevos = 0
                continue
            break

    mensajes = construir_mensajes([acumulado[i] for i in orden[-max_mensajes:]])
    if desde is not None:
        mensajes = [m for m in mensajes if m.timestamp >= desde]
        if not alcanzo_desde:
            primero = min((m.timestamp for m in mensajes), default=None)
            logger.warning(
                "HISTÓRICO INCOMPLETO: solo se cargó desde %s y se pedía desde %s. "
                "WhatsApp Web aún no tiene los mensajes más antiguos (se bajan desde el celular; "
                "mantenlo con internet y vuelve a correr cuando termine de sincronizar).",
                primero or "(ningún mensaje)", desde,
            )
    logger.info("Leyendo %d mensajes del chat.", len(mensajes))
    return mensajes


_JS_VISOR_PRINCIPAL = """() => {
  // Elemento grande del visor (foto o video); las miniaturas de la tira inferior son pequeñas.
  const cands = [...document.querySelectorAll('img, video')].map(e => {
    const r = e.getBoundingClientRect();
    return {e, area: r.width * r.height, src: e.currentSrc || e.src || ''};
  }).filter(c => c.src.startsWith('blob:') && c.area > 60000);
  cands.sort((x, y) => y.area - x.area);
  return cands.length ? {src: cands[0].src, tag: cands[0].e.tagName} : null;
}"""

_JS_BAJAR_BLOB = """async (src) => {
  const b = await (await fetch(src)).blob(); const u = new Uint8Array(await b.arrayBuffer());
  let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return {tipo: b.type, b64: btoa(s)};
}"""


_JS_CABECERA_VISOR = r"""() => {
  // Texto de fecha/hora del encabezado del visor ("Hoy a la(s) 7:21 a.m."): cambia al pasar a otro mensaje.
  const e = [...document.querySelectorAll('div,span')].find(x => x.children.length === 0
    && /\d{1,2}:\d{2}/.test(x.textContent || '') && x.getBoundingClientRect().top < 90);
  return e ? e.textContent.trim() : null;
}"""

_BOTON_SIGUIENTE = 'button[aria-label="Siguiente"], button[aria-label="Next"]'
_BOTON_DESCARGAR = 'button[aria-label="Descargar"], button[aria-label="Download"]'
_BOTON_CERRAR = 'button[aria-label="Cerrar"], button[aria-label="Close"]'


def _bajar_elemento_actual(pagina: Page, carpeta: Path, base: str) -> Path | None:
    """Guarda el elemento que muestra el visor ahora. Foto: por su blob. Video: botón Descargar del visor
    (da el archivo original); si falla, por el blob del <video>."""
    import base64
    import mimetypes

    principal = None
    for _ in range(14):  # hasta ~7 s a que el visor cargue el elemento completo
        pagina.wait_for_timeout(500)
        principal = pagina.evaluate(_JS_VISOR_PRINCIPAL)
        if principal:
            break
    if not principal:
        return None
    if principal["tag"] == "VIDEO":
        try:
            with pagina.expect_download(timeout=45_000) as info:
                pagina.locator(_BOTON_DESCARGAR).first.click(timeout=4_000)
            d = info.value
            ruta = carpeta / f"{base}{Path(d.suggested_filename).suffix or '.mp4'}"
            d.save_as(ruta)
            return ruta
        except Exception as e:  # noqa: BLE001
            if "closed" in str(e).lower():
                raise
            logger.warning("Botón Descargar falló para el video '%s' (%s); se intenta por blob.", base, str(e)[:80])
    datos = pagina.evaluate(_JS_BAJAR_BLOB, principal["src"])
    ext = mimetypes.guess_extension(datos["tipo"].split(";")[0]) or (".mp4" if principal["tag"] == "VIDEO" else ".jpg")
    ext = ".jpg" if ext in (".jpe", ".jpeg") else ext
    ruta = carpeta / f"{base}{ext}"
    ruta.write_bytes(base64.b64decode(datos["b64"]))
    return ruta


def descargar_adjunto(
    pagina: Page, miniatura: Locator, carpeta_destino: Path, nombre_base: str, todo_el_album: bool = False, max_album: int = 60,
) -> list[Path]:
    """
    Descarga el adjunto de una miniatura abriendo el visor de WhatsApp Web (foto verificada en vivo: 864x1152
    en ~2 s; video por el botón Descargar del visor). Con `todo_el_album` pasa con "Siguiente" por todos los
    elementos del mismo mensaje (misma fecha/hora en el encabezado), sea cual sea su cantidad, y guarda
    `<nombre_base>_1`, `_2`... Sin álbum guarda uno solo con `<nombre_base>`. Devuelve las rutas guardadas.
    El visor siempre se cierra con su botón "Cerrar".
    """
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    rutas: list[Path] = []
    try:
        miniatura.scroll_into_view_if_needed(timeout=5_000)
        pagina.wait_for_timeout(random.randint(300, 800))
        miniatura.click(timeout=8_000)
        pagina.wait_for_timeout(700)
        cabecera = pagina.evaluate(_JS_CABECERA_VISOR)
        vistos: set[int] = set()
        for n in range(1, (max_album if todo_el_album else 1) + 1):
            ruta = _bajar_elemento_actual(pagina, carpeta_destino, f"{nombre_base}_{n}" if todo_el_album else nombre_base)
            if ruta is not None:
                firma = hash(ruta.read_bytes()[:4096]) ^ ruta.stat().st_size
                if firma in vistos:  # el visor no avanzó: mismo archivo otra vez
                    ruta.unlink()
                    break
                vistos.add(firma)
                rutas.append(ruta)
            if not todo_el_album:
                break
            sig = pagina.locator(_BOTON_SIGUIENTE).first
            if sig.count() == 0 or not sig.is_enabled() or sig.get_attribute("aria-disabled") == "true":
                break
            pagina.wait_for_timeout(random.randint(500, 1400))
            sig.click(timeout=4_000)
            pagina.wait_for_timeout(700)
            if pagina.evaluate(_JS_CABECERA_VISOR) != cabecera:  # ya es otro mensaje
                break
    except Exception as e:  # noqa: BLE001
        if "closed" in str(e).lower():
            raise
        logger.error("No se pudo descargar el adjunto '%s': %s", nombre_base, e)
    finally:
        try:
            pagina.locator(_BOTON_CERRAR).first.click(timeout=3_000)
            pagina.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            pass
    return rutas
