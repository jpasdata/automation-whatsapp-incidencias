import pytest

from src.nucleo.config import ConfigError, load_config


def test_load_config_falla_claro_si_no_existe_el_archivo(tmp_path):
    with pytest.raises(ConfigError, match="No existe"):
        load_config(tmp_path / "config_inexistente.yaml")


def test_load_config_falla_si_falta_una_seccion(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text("whatsapp:\n  nombre_grupo: X\n  carpeta_sesion: ./s\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="excel"):
        load_config(ruta)


def test_load_config_carga_correctamente_un_archivo_valido(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        """
whatsapp:
  nombre_grupo: "Grupo Incidencias"
  carpeta_sesion: "./sesion_whatsapp"
  headless: false
excel:
  ruta_archivo: "./data/x.xlsx"
  nombre_hoja: "Asignacion- SEP"
  columna_codigo_largo: "COD-INCIDENCIA"
  columna_codigo_corto: "Incidencia"
  columna_evidencia_manual: "EVIDENCIA"
  columna_estado_automatico: "Estado_Automatico"
  columna_ruta_foto: "Ruta_Evidencia"
matching:
  patron_codigo_regex: '\\b\\d{6,8}\\b'
  ventana_minutos_mensaje_separado: 15
notificaciones:
  activas: false
  mapeo_nombre_telefono: {}
  plantilla_mensaje: "hola {nombre} {codigo}"
rutas:
  carpeta_evidencias: "./data/Evidencias_WhatsApp"
  carpeta_identificadas: "Incidencias_Identificadas"
  carpeta_sin_codigo: "Sin_Codigo_Asignado"
logging:
  carpeta_logs: "./logs"
  nivel: "INFO"
""",
        encoding="utf-8",
    )
    cfg = load_config(ruta)
    assert cfg.whatsapp.grupos == ["Grupo Incidencias"]
    assert cfg.notificaciones.activas is False
    assert cfg.matching.ventana_minutos_mensaje_separado == 15


def test_load_config_acepta_lista_de_grupos(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        'whatsapp:\n  grupos: ["A", "B"]\n  carpeta_sesion: ./s\n'
        'excel: {ruta_archivo: x, nombre_hoja: h, columna_codigo_largo: a, columna_codigo_corto: b, '
        'columna_evidencia_manual: c, columna_estado_automatico: d, columna_ruta_foto: e}\n'
        'matching: {patron_codigo_regex: "x", ventana_minutos_mensaje_separado: 5}\n'
        'notificaciones: {activas: false}\n'
        'rutas: {carpeta_evidencias: a, carpeta_identificadas: b, carpeta_sin_codigo: c}\n'
        'logging: {carpeta_logs: l, nivel: INFO}\n',
        encoding="utf-8",
    )
    assert load_config(ruta).whatsapp.grupos == ["A", "B"]


def test_load_config_sin_grupos_falla(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text("whatsapp:\n  grupos: []\n  carpeta_sesion: ./s\n"
                    "excel: {}\nmatching: {}\nnotificaciones: {}\nrutas: {}\nlogging: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="grupos"):
        load_config(ruta)


def test_resolver_cargar_desde():
    from datetime import datetime
    from src.nucleo.config import resolver_cargar_desde
    hoy = datetime(2026, 10, 15, 22, 0)
    assert resolver_cargar_desde("mes_actual", hoy) == datetime(2026, 10, 1)
    assert resolver_cargar_desde("2026-09-20", hoy) == datetime(2026, 9, 20)
    assert resolver_cargar_desde("", hoy) is None
    with pytest.raises(ConfigError):
        resolver_cargar_desde("ayer-mismo", hoy)
