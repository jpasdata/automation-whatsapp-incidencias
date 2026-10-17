"""
Scroll "humano" para que WhatsApp Web pida mensajes antiguos al celular.

Se comprobó en vivo (2026-10-15) que la rueda sintética de Playwright casi nunca
dispara la carga, mientras que una rueda REAL del sistema operativo (cursor de
Windows sobre el chat + eventos de rueda) la dispara en segundos. Por eso:
  - `plan_humano()` genera un ritmo variable (ráfagas de muescas de 120 px, pausas,
    más muescas hacia arriba que hacia abajo) — lógica pura y testeable;
  - `rueda_real_windows()` lo ejecuta con SetCursorPos + mouse_event (solo Windows);
  - `rueda_playwright()` es el plan B (otros sistemas / si falla lo anterior).

IMPORTANTE: la rueda real mueve el cursor de verdad: mientras corre, no hay que usar
el mouse ni tapar la ventana de Chromium.
"""
from __future__ import annotations

import logging
import random
import sys
import time

logger = logging.getLogger("incidencias_wa")

MUESCA = 120  # una muesca de rueda de mouse


def plan_humano(
    rng: random.Random | None = None,
    muescas_abajo: tuple[int, int] = (25, 45),
    muescas_arriba: tuple[int, int] = (60, 110),
) -> list[tuple[int, float]]:
    """
    Lista de (delta, segundos_de_espera_despues). Primero baja (delta negativo en
    mouse_event de Windows = hacia abajo; aquí se usa +1/-1 como dirección: +1 abajo,
    -1 arriba), con ráfagas de 3 a 8 muescas, 20-45 ms entre muescas y pausas de
    0,1-0,3 s entre ráfagas; luego sube con más muescas.
    """
    rng = rng or random.Random()
    plan: list[tuple[int, float]] = []

    def tramo(direccion: int, total: int) -> None:
        hechas = 0
        while hechas < total:
            rafaga = min(rng.randint(3, 8), total - hechas)
            for k in range(rafaga):
                ultima = k == rafaga - 1
                espera = rng.uniform(0.1, 0.3) if ultima else rng.uniform(0.02, 0.045)
                plan.append((direccion, espera))
            hechas += rafaga

    tramo(+1, rng.randint(*muescas_abajo))
    plan.append((0, rng.uniform(0.2, 0.5)))  # breve pausa abajo, como quien mira
    tramo(-1, rng.randint(*muescas_arriba))
    return plan


_dpi_listo = False


def _preparar_dpi() -> None:
    global _dpi_listo
    if _dpi_listo:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001 - ya estaba configurado
        pass
    _dpi_listo = True


_JS_CENTRO_PANEL = """() => {
  const el = document.querySelector('[data-testid="conversation-panel-messages"]');
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2, sx: window.screenX, sy: window.screenY,
          dpr: window.devicePixelRatio, top: window.outerHeight - window.innerHeight,
          left: (window.outerWidth - window.innerWidth) / 2};
}"""


def rueda_real_windows(pagina, plan: list[tuple[int, float]] | None = None) -> bool:
    """Mueve el cursor de Windows sobre el chat y gira la rueda según `plan`. False si no se pudo."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        _preparar_dpi()
        info = pagina.evaluate(_JS_CENTRO_PANEL)
        if not info:
            return False
        user32 = ctypes.windll.user32
        x = int((info["sx"] + info["left"] + info["x"]) * info["dpr"])
        y = int((info["sy"] + info["top"] + info["y"]) * info["dpr"])

        # el cursor llega al chat "caminando", no de golpe
        ox, oy = x + random.randint(-120, 120), y + random.randint(-120, 120)
        for i in range(1, 9):
            user32.SetCursorPos(int(ox + (x - ox) * i / 8), int(oy + (y - oy) * i / 8))
            time.sleep(0.02)

        for direccion, espera in plan or plan_humano():
            if direccion != 0:
                # mouse_event: delta positivo = rueda hacia arriba (contenido sube); negativo = hacia abajo
                user32.mouse_event(0x0800, 0, 0, (-MUESCA * direccion) & 0xFFFFFFFF, 0)
            time.sleep(espera)
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("rueda_real_windows: %s", e)
        return False


def rueda_playwright(pagina, plan: list[tuple[int, float]] | None = None) -> None:
    """Plan B con el mismo ritmo humano, pero con la rueda sintética de Playwright."""
    try:
        pagina.locator('[data-testid="conversation-panel-messages"]').first.hover(timeout=3000)
        for direccion, espera in plan or plan_humano():
            if direccion != 0:
                pagina.mouse.wheel(0, MUESCA * direccion)
            pagina.wait_for_timeout(int(espera * 1000))
    except Exception as e:  # noqa: BLE001
        logger.debug("rueda_playwright: %s", e)


def sacudir_humano(pagina, rueda_real: bool = True, solo_subir: bool = False) -> str:
    """
    Hace el scroll humano; devuelve con qué método se hizo ('real' | 'playwright').
    `solo_subir=True` omite el tramo hacia abajo: se usa cuando acaba de llegar una tanda de
    mensajes y hay que seguir subiendo de inmediato.
    """
    plan = plan_humano(muescas_abajo=(0, 0), muescas_arriba=(40, 80)) if solo_subir else None
    if rueda_real and rueda_real_windows(pagina, plan):
        return "real"
    rueda_playwright(pagina, plan)
    return "playwright"


class PresionContinua:
    """
    Imita a la persona que, al llegar arriba y ver la ruedita de carga, SIGUE girando la rueda hacia
    arriba sin parar hasta que llegan los mensajes (observado a mano: así carga más rápido que
    quedándose quieto). Coloca el cursor una vez y luego da muescas sueltas a ritmo variable.
    """

    def __init__(self, pagina, rueda_real: bool = True):
        self.pagina = pagina
        self.real = rueda_real and sys.platform == "win32"
        self._user32 = None
        if self.real:
            try:
                import ctypes

                _preparar_dpi()
                info = pagina.evaluate(_JS_CENTRO_PANEL)
                if info:
                    self._user32 = ctypes.windll.user32
                    x = int((info["sx"] + info["left"] + info["x"]) * info["dpr"])
                    y = int((info["sy"] + info["top"] + info["y"]) * info["dpr"])
                    self._user32.SetCursorPos(x + random.randint(-30, 30), y + random.randint(-30, 30))
                else:
                    self.real = False
            except Exception as e:  # noqa: BLE001
                logger.debug("PresionContinua: %s", e)
                self.real = False

    def muesca_arriba(self) -> None:
        if self.real and self._user32 is not None:
            self._user32.mouse_event(0x0800, 0, 0, MUESCA, 0)  # delta positivo = rueda hacia arriba
        else:
            try:
                self.pagina.mouse.wheel(0, -MUESCA)
            except Exception:  # noqa: BLE001
                pass

    def recentrar(self) -> None:
        """Devuelve el cursor al centro del chat (por si algo lo movió)."""
        if self.real and self._user32 is not None:
            try:
                info = self.pagina.evaluate(_JS_CENTRO_PANEL)
                if info:
                    x = int((info["sx"] + info["left"] + info["x"]) * info["dpr"])
                    y = int((info["sy"] + info["top"] + info["y"]) * info["dpr"])
                    self._user32.SetCursorPos(x + random.randint(-30, 30), y + random.randint(-30, 30))
            except Exception:  # noqa: BLE001
                pass

    def muesca_abajo(self) -> None:
        if self.real and self._user32 is not None:
            self._user32.mouse_event(0x0800, 0, 0, (-MUESCA) & 0xFFFFFFFF, 0)
        else:
            try:
                self.pagina.mouse.wheel(0, MUESCA)
            except Exception:  # noqa: BLE001
                pass

    def rafaga_humana(self) -> None:
        """
        UNA ráfaga con el patrón medido en una persona real (grabación de 100 s, 2026-10-16):
        ~5 giros (3 a 8) con 14-50 ms entre giros y ~330 ms de pausa después; 89 % del tiempo hacia
        arriba, con una bajadita corta (4 a 8 giros) cada 12-20 s.
        """
        ahora = time.time()
        if not hasattr(self, "_proxima_bajada"):
            self._proxima_bajada = ahora + random.uniform(12, 20)
            self._proximo_recentrado = ahora + 30
        bajar = ahora >= self._proxima_bajada
        giro = self.muesca_abajo if bajar else self.muesca_arriba
        for _ in range(random.randint(4, 8) if bajar else random.randint(3, 8)):
            giro()
            time.sleep(random.uniform(0.014, 0.05))
        if bajar:
            self._proxima_bajada = time.time() + random.uniform(12, 20)
        if time.time() >= self._proximo_recentrado:
            self.recentrar()
            self._proximo_recentrado = time.time() + 30
        time.sleep(random.uniform(0.15, 0.6))

    def presionar(self, hasta_que, max_seg: float) -> bool:
        """Gira hacia arriba a ritmo humano hasta que `hasta_que()` sea True o pasen `max_seg`. True si se cumplió."""
        limite = time.time() + max_seg
        while time.time() < limite:
            for _ in range(random.randint(1, 4)):
                self.muesca_arriba()
                time.sleep(random.uniform(0.02, 0.05))
            if hasta_que():
                return True
            time.sleep(random.uniform(0.12, 0.35))
        return hasta_que()


def _girar(giro, muescas: int) -> None:
    """Gira `muescas` en ráfagas de 3-8 con el ritmo medido (14-50 ms entre giros, pausas de 150-450 ms)."""
    hechas = 0
    while hechas < muescas:
        rafaga = min(random.randint(3, 8), muescas - hechas)
        for _ in range(rafaga):
            giro()
            time.sleep(random.uniform(0.014, 0.05))
        hechas += rafaga
        time.sleep(random.uniform(0.15, 0.45))


def ciclo_bajar_y_subir(presion: "PresionContinua", bajar=(8, 14), subir=(26, 46)) -> None:
    """
    El gesto que dispara la carga (comprobado a mano: el círculo de carga solo aparece al BAJAR con la
    rueda y volver a subir): bajar unas 8-14 muescas (~1-2 pantallas), mirar un instante y volver a subir
    más de lo que se bajó hasta entrar de nuevo al tope.
    """
    _girar(presion.muesca_abajo, random.randint(*bajar))
    time.sleep(random.uniform(0.3, 0.9))
    _girar(presion.muesca_arriba, random.randint(*subir))
