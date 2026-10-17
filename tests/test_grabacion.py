from __future__ import annotations

from src.whatsapp.grabacion import resumir


def test_resumir_rafagas_y_pausas():
    ev, t = [], 0
    for rafaga in range(3):                  # 3 ráfagas de 4 giros (cada 30 ms) y pausas de 500 ms
        for k in range(4):
            ev.append({"t": t, "tipo": "wheel", "trusted": True, "dy": -100}); t += 30
        t += 500
    ev.append({"t": t, "tipo": "scroll", "trusted": True, "top": 0})
    r = resumir(ev)
    assert r["wheel_total"] == 12 and r["wheel_arriba"] == 12 and r["wheel_abajo"] == 0
    assert r["rafagas_n"] == 3 and r["rafaga_muescas_mediana"] == 4
    assert 450 <= r["pausas_entre_rafagas_ms_mediana"] <= 650
    assert r["wheel_dy_frecuentes"] == [(100, 12)] and r["todos_trusted"] is True


def test_resumir_sin_eventos():
    r = resumir([])
    assert r["wheel_total"] == 0 and r["rafagas_n"] == 0 and r["todos_trusted"] is None
