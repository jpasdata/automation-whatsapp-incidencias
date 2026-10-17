"""Fixtures compartidas por los tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

PATRON_REGEX_DEFAULT = r"\b\d{6,8}\b"


@pytest.fixture
def excel_temporal(tmp_path: Path) -> Path:
    """
    Crea un .xlsx mínimo con la misma estructura real del Excel del
    usuario (mismas columnas relevantes, más una hoja extra para
    confirmar que no se destruye al guardar).
    """
    ruta = tmp_path / "incidencias_test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Asignacion- SEP"
    ws.append([
        "COD-INCIDENCIA", "Asignado a", "Incidencia", "EVIDENCIA",
        "Observaciones", "NUMERO AVISO", "Fecha Detección", "Fecha SR",
    ])
    ws.append([
        "011682220001", "Henry", "1168222", "PEDIR EVIDENCIAS",
        "Se encontró el elemento F3092 abierto por falla", 5604168,
        datetime(2026, 10, 4, 12, 52), datetime(2026, 10, 4, 17, 17),
    ])
    ws.append([
        "011663390001", "Henry", "1166339", "FOTO Y VIDEO OK",
        "Apertura del fusible de conversión", 5604912,
        datetime(2026, 9, 24, 16, 22), datetime(2026, 9, 24, 19, 1),
    ])
    ws.append([
        "011664070001", "Henry", "1166407", None,
        "Sin detalle de elemento", None,
        datetime(2026, 9, 25, 1, 32), datetime(2026, 9, 25, 2, 6),
    ])
    ws.append([
        "011664090001", "Henry", "1166409", "video ok",
        "elemento 30350 revisado", 5604627,
        datetime(2026, 9, 24, 23, 35), datetime(2026, 9, 25, 1, 44),
    ])

    otra_hoja = wb.create_sheet("OCTUBRE")
    otra_hoja["A1"] = "esta hoja no debe desaparecer"

    wb.save(ruta)
    return ruta
