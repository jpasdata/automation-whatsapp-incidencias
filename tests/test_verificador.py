from src.nucleo.verificador import ERROR, OK, AVISO, Resultado, hay_errores, informe, revisar_candado, revisar_carpetas, revisar_config


def test_config_inexistente_es_error_con_arreglo(tmp_path):
    res, cfg = revisar_config(tmp_path)
    assert cfg is None and res[0].nivel == ERROR and "config.example.yaml" in res[0].arreglo


def test_candado_de_proceso_muerto_no_bloquea(tmp_path):
    (tmp_path / "sesion_whatsapp.lock").write_text("999999999")
    assert revisar_candado(tmp_path).nivel == OK


def test_carpetas_se_crean_y_son_escribibles(tmp_path):
    assert revisar_carpetas(tmp_path).nivel == OK and (tmp_path / "data" / "indice").is_dir()


def test_informe_resume_y_dice_que_hacer():
    r = [Resultado(OK, "a"), Resultado(AVISO, "b", "x", "haz esto"), Resultado(ERROR, "c", "y", "arregla aquello")]
    t = informe(r)
    assert hay_errores(r) and "QUÉ HACER: arregla aquello" in t and "NO CORRER TODAVÍA: 1 error" in t
