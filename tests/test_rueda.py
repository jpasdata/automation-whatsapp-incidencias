from __future__ import annotations

import random

from src.rueda import MUESCA, plan_humano


def test_plan_humano_baja_pausa_y_sube_mas():
    plan = plan_humano(random.Random(1))
    dirs = [d for d, _ in plan]
    assert dirs[0] == +1 and dirs[-1] == -1 and 0 in dirs          # empieza bajando, termina subiendo, hay pausa
    assert dirs.count(-1) > dirs.count(+1) >= 25                    # sube más de lo que baja
    assert all(0.015 <= e <= 0.55 for _, e in plan)                 # ritmos humanos, sin ráfagas instantáneas


def test_plan_humano_es_variable_entre_corridas_pero_reproducible_con_semilla():
    assert plan_humano(random.Random(1)) == plan_humano(random.Random(1))
    assert plan_humano(random.Random(1)) != plan_humano(random.Random(2))


def test_muesca_estandar():
    assert MUESCA == 120


def test_rafaga_humana_ritmo_y_proporcion(monkeypatch):
    """La ráfaga reproduce el patrón medido: ~5 giros, casi siempre hacia arriba, con bajadas esporádicas."""
    import time as _t

    from src import rueda

    monkeypatch.setattr(_t, "sleep", lambda s: None)
    class P:  # página falsa: sin cursor real
        pass
    p = rueda.PresionContinua.__new__(rueda.PresionContinua)
    p.pagina, p.real, p._user32 = P(), False, None
    giros = []
    p.muesca_arriba = lambda: giros.append(-1)
    p.muesca_abajo = lambda: giros.append(+1)
    p.recentrar = lambda: None
    for _ in range(40):
        p.rafaga_humana()
    arriba, abajo = giros.count(-1), giros.count(+1)
    assert arriba >= 100 and 3 <= abajo + 0 or abajo == 0
    assert arriba / max(1, arriba + abajo) > 0.8


def test_calentamiento_hace_varios_ciclos_con_subidas_y_bajadas(monkeypatch):
    import random as _r
    import time as _t

    from src.whatsapp_reader import _calentar

    reloj = {"t": 0.0}
    monkeypatch.setattr(_t, "time", lambda: reloj["t"])
    monkeypatch.setattr(_t, "sleep", lambda s: reloj.__setitem__("t", reloj["t"] + s))
    _r.seed(3)

    class Pr:
        def __init__(self):
            self.rafagas, self.bajadas = 0, 0

        def rafaga_humana(self):
            self.rafagas += 1
            reloj["t"] += 0.35

        def muesca_abajo(self):
            self.bajadas += 1

    p = Pr()
    _calentar(p, ciclos=4)
    assert p.rafagas >= 4 * 3 and p.bajadas >= 4 * 3  # 4 ciclos: varias ráfagas arriba y bajadas cortas entre medio


def test_ciclo_bajar_y_subir_sube_mas_de_lo_que_baja(monkeypatch):
    import time as _t

    from src import rueda

    monkeypatch.setattr(_t, "sleep", lambda s: None)
    giros = []

    class Pr:
        def muesca_abajo(self):
            giros.append(+1)

        def muesca_arriba(self):
            giros.append(-1)

    rueda.ciclo_bajar_y_subir(Pr())
    assert giros.count(+1) >= 8 and giros.count(-1) >= 26
    assert giros.index(-1) > giros.index(+1)  # primero baja, luego sube
    assert giros.count(-1) > giros.count(+1)
