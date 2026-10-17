from datetime import datetime

from src.cruce.validacion_temporal import verificar_ventana_horaria

FECHA_DETECCION = datetime(2026, 10, 4, 12, 52)
FECHA_SR = datetime(2026, 10, 4, 17, 17)


def test_evidencia_dentro_de_la_ventana_es_valida():
    timestamp = datetime(2026, 10, 4, 15, 0)  # entre deteccion y SR
    resultado = verificar_ventana_horaria(timestamp, FECHA_DETECCION, FECHA_SR, margen_horas=4)
    assert resultado.dentro_de_ventana is True


def test_evidencia_poco_despues_del_sr_es_valida_por_el_margen():
    timestamp = datetime(2026, 10, 4, 19, 0)  # 1h43 después del SR, margen de 4h
    resultado = verificar_ventana_horaria(timestamp, FECHA_DETECCION, FECHA_SR, margen_horas=4)
    assert resultado.dentro_de_ventana is True


def test_evidencia_mucho_despues_del_sr_mas_el_margen_no_es_valida():
    timestamp = datetime(2026, 10, 5, 10, 0)  # muy lejos del SR
    resultado = verificar_ventana_horaria(timestamp, FECHA_DETECCION, FECHA_SR, margen_horas=4)
    assert resultado.dentro_de_ventana is False
    assert "DESPUÉS" in resultado.motivo


def test_evidencia_antes_de_fecha_deteccion_no_es_valida():
    timestamp = datetime(2026, 10, 3, 8, 0)  # el día anterior, sospechoso
    resultado = verificar_ventana_horaria(timestamp, FECHA_DETECCION, FECHA_SR, margen_horas=4)
    assert resultado.dentro_de_ventana is False
    assert "ANTES" in resultado.motivo


def test_sin_fechas_en_el_excel_se_deja_pasar_con_advertencia():
    timestamp = datetime(2026, 10, 4, 15, 0)
    resultado = verificar_ventana_horaria(timestamp, None, None, margen_horas=4)
    assert resultado.dentro_de_ventana is True
    assert "no tiene Fecha" in resultado.motivo


def test_sin_timestamp_de_evidencia_no_es_valida():
    resultado = verificar_ventana_horaria(None, FECHA_DETECCION, FECHA_SR, margen_horas=4)
    assert resultado.dentro_de_ventana is False
