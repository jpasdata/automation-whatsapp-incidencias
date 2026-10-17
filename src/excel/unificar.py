"""
Unifica el Excel de incidencias en UNA sola hoja ("Incidencias") bien formateada, sin perder nada:

  * Una fila por incidencia. Las reasignaciones (la misma incidencia repetida en la hoja principal o en OCTUBRE) se funden en una
    fila: manda la última asignación y TODAS quedan en «Historial de asignaciones» (fecha, hoja, fila, notas y avisos de cada una).
  * Se integra lo de las demás hojas: `OCTUBRE`, `c ya entregados sin correo`, `TABLA EVIDENCIAS` (pendiente de evidencia, JT, aviso),
    `CIERRE DE INCIDENCIAS` (todas sus columnas), `C ENVIADOS` (enviado) y `Hoja1` (acciones sobre los PDFs).
  * Los nombres de las columnas que usa el bot (COD-INCIDENCIA, Incidencia, EVIDENCIA, NUMERO AVISO, Observaciones, Fecha Detección,
    Fecha SR, Provincia, Asignado a) se conservan tal cual, así que el bot lo lee igual que el original.
  * Las incidencias que solo aparecen en hojas auxiliares y no son de Henry (p. ej. de otro responsable) se incluyen, pero con su
    responsable en «Asignado a» para que el bot las ignore.
El archivo original NO se modifica: se escribe uno nuevo.
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HOJA_HISTORICO, HOJA_NUEVAS = "Histórico", "Nuevas"
NOMBRE_HOJA = HOJA_HISTORICO   # (compatibilidad) hoja principal
HOJAS_BASE = (HOJA_HISTORICO, HOJA_NUEVAS)
ALTO_FILA = 18                 # las filas NO crecen: el texto largo va en columnas anchas, sin ajustar
PRIORIDAD_HOJA = {"Asignacion- SEP": 0, "OCTUBRE": 1, "c ya entregados sin correo": 2}
BAND = {"ident": "1F3864", "fechas": "2E75B6", "causa": "7F6000", "evid": "375623", "anexos": "7030A0", "cierre": "833C0B", "acciones": "595959", "bot": "0B6E4F"}

# (clave interna, título de columna, grupo, ancho)
COLUMNAS = [
    ("Incidencia", "Incidencia", "ident", 12), ("COD-INCIDENCIA", "COD-INCIDENCIA", "ident", 16), ("Asignado a", "Asignado a", "ident", 12),
    ("zona", "zona", "ident", 10), ("Provincia", "Provincia", "ident", 14), ("Distrito", "Distrito", "ident", 14),
    ("Corregimiento", "Corregimiento", "ident", 16), ("Instalación", "Instalación", "ident", 20), ("Descripcion", "Descripcion", "ident", 34),
    ("ASIGNACION", "ASIGNACION", "fechas", 13), ("Fecha Detección", "Fecha Detección", "fechas", 17), ("Fecha SR", "Fecha SR", "fechas", 17),
    ("Duración SR", "Duración SR", "fechas", 12),
    ("Tipo de Causa", "Tipo de Causa", "causa", 16), ("Causa", "Causa", "causa", 18), ("causa_agrupadora", "causa_agrupadora", "causa", 22),
    ("estado", "estado", "causa", 10), ("excepcion", "excepcion", "causa", 11), ("Estado Actual", "Estado Actual", "causa", 14),
    ("Observaciones", "Observaciones", "causa", 46),
    ("NUMERO AVISO", "NUMERO AVISO", "evid", 14), ("Otros avisos", "Otros avisos", "evid", 16), ("EVIDENCIA", "EVIDENCIA", "evid", 36),
    ("Pendiente de evidencia", "Pendiente de evidencia (TABLA EVIDENCIAS)", "evid", 26), ("JT", "JT (TABLA EVIDENCIAS)", "evid", 22),
    ("Responsable tabla", "Responsable (TABLA EVIDENCIAS)", "evid", 16), ("Fecha tabla", "FECHA (TABLA EVIDENCIAS)", "evid", 14), ("TERRITORIO", "TERRITORIO (TABLA EVIDENCIAS)", "evid", 14),
    ("WINDY", "WINDY", "anexos", 10), ("IMHPA", "IMHPA", "anexos", 10), ("NOTICIA", "NOTICIA", "anexos", 10), ("ANEXO A", "ANEXO A", "anexos", 10),
    ("ANEXO B", "ANEXO B", "anexos", 10), ("ANEXO C", "ANEXO C", "anexos", 10), ("OT", "OT", "anexos", 10),
    ("anexo c enviados", "anexo c enviados", "anexos", 12), ("Anexo C enviado (C ENVIADOS)", "Enviado (hoja C ENVIADOS)", "anexos", 14),
    ("Cierre · ESTADO", "Cierre · ESTADO", "cierre", 12), ("Cierre · #", "Cierre · #", "cierre", 9), ("Cierre · Tipo", "Cierre · Tipo", "cierre", 18),
    ("Cierre · Estado", "Cierre · Estado", "cierre", 12), ("Cierre · Prioridad", "Cierre · Prioridad", "cierre", 11),
    ("Cierre · Asunto", "Cierre · Asunto", "cierre", 30), ("Cierre · Audito", "Cierre · Auditó", "cierre", 14),
    ("Cierre · Ficheros", "Cierre · Ficheros", "cierre", 30), ("Cierre · noticia", "Cierre · noticia", "cierre", 10),
    ("Cierre · imhpa", "Cierre · imhpa", "cierre", 10), ("Cierre · WINDY", "Cierre · WINDY", "cierre", 10),
    ("Cierre · ANEXO B", "Cierre · ANEXO B", "cierre", 10), ("Cierre · OBSERVACION", "Cierre · OBSERVACION", "cierre", 30),
    ("Cierre · X", "Cierre · X", "cierre", 8),
    ("Acciones · #", "Acciones PDF · #", "acciones", 8),
    ("Acciones · Causa / Detalle", "Acciones PDF · Causa / Detalle", "acciones", 26),
    ("Acciones · Otras pruebas en PDF Actual", "Acciones PDF · Otras pruebas en PDF actual", "acciones", 34),
    ("Acciones · Otras pruebas a Colocar (Propuesto)", "Acciones PDF · Otras pruebas a colocar (propuesto)", "acciones", 34),
    ("Acciones · Acción Aplicada", "Acciones PDF · Acción aplicada", "acciones", 28), ("Acciones · subido", "Acciones PDF · subido", "acciones", 10),
    ("Origen", "Origen (hojas del Excel original)", "bot", 26), ("N° de asignaciones", "N° de asignaciones", "bot", 12),
    ("Historial de asignaciones", "Historial de asignaciones", "bot", 60),
    ("Notas de consolidación", "Notas de consolidación (valores en conflicto entre hojas)", "bot", 40),
    ("Estado_Automatico", "Estado_Automatico", "bot", 34), ("Ruta_Evidencia", "Ruta_Evidencia", "bot", 40),
]
COLUMNAS_FECHA = {"ASIGNACION", "Fecha Detección", "Fecha SR", "Fecha tabla"}
COLUMNAS_USADAS: list[tuple] = []
RX_AVISO = re.compile(r"(?<!\d)(5[67]\d)-?(\d{4})(?!\d)")


def _inc(v) -> str | None:
    try:
        return str(int(float(str(v).strip())))
    except (TypeError, ValueError):
        return None


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _limpio(v):
    return v.strip() if isinstance(v, str) else v


def _leer_hoja(ws, con_encabezado: bool, encabezado_ref: list[str] | None = None, max_col: int = 40) -> list[tuple[int, dict]]:
    """[(fila_excel, {columna: valor})] con los encabezados repetidos numerados (zona, zona (2))."""
    filas = [(i, list(r)) for i, r in enumerate(ws.iter_rows(max_col=max_col, values_only=True), 1)]
    if con_encabezado:
        nombres, usados = [], defaultdict(int)
        for v in filas[0][1]:
            n = str(v).strip() if v is not None else ""
            usados[n] += 1
            nombres.append(n if usados[n] == 1 or not n else f"{n} ({usados[n]})")
        datos = filas[1:]
    else:
        nombres, datos = list(encabezado_ref or []), filas
    out = []
    for i, r in datos:
        d = {nombres[j]: _limpio(r[j]) for j in range(min(len(nombres), len(r))) if nombres[j] and not _vacio(r[j])}
        if d:
            out.append((i, d))
    return out


def leer_origen(ruta_original: Path, hoja_principal: str, hojas_extra: list[str]) -> dict:
    wb = load_workbook(ruta_original, data_only=True, read_only=True)
    principal = _leer_hoja(wb[hoja_principal], True)
    encabezado_principal = [str(c.value).strip() if c.value is not None else "" for c in next(wb[hoja_principal].iter_rows(min_row=1, max_row=1, max_col=40))]
    origen = {"asignaciones": [], "wb": wb}
    for hoja, filas in [(hoja_principal, principal)] + [
        (h, _leer_hoja(wb[h], con_encabezado=(h == "OCTUBRE"), encabezado_ref=encabezado_principal)) for h in hojas_extra if h in wb.sheetnames
    ]:
        for fila, d in filas:
            if _inc(d.get("Incidencia")):
                origen["asignaciones"].append((hoja, fila, d))
    return origen


def _poner(f: dict, col: str, valor, fuente: str) -> None:
    """Si la columna está vacía se llena; si ya trae OTRO valor, el de la hoja auxiliar no se pierde: va a «Notas de consolidación»."""
    if _vacio(valor):
        return
    if _vacio(f.get(col)):
        f[col] = valor
    elif str(f[col]).strip() != str(valor).strip():
        f.setdefault("_conflictos", []).append(f"{fuente}: {col} = {valor}")


def _aux(wb, nombre: str, **kw):
    return _leer_hoja(wb[nombre], **kw) if nombre in wb.sheetnames else []


def unificar(ruta_original: Path, ruta_salida: Path, hoja_principal: str = "Asignacion- SEP",
             hojas_extra: tuple[str, ...] = ("OCTUBRE", "c ya entregados sin correo")) -> dict:
    origen = leer_origen(ruta_original, hoja_principal, list(hojas_extra))
    wb = origen["wb"]
    por_inc: dict[str, list[tuple[str, int, dict]]] = defaultdict(list)
    for hoja, fila, d in origen["asignaciones"]:
        por_inc[_inc(d["Incidencia"])].append((hoja, fila, d))

    unificadas: OrderedDict[str, dict] = OrderedDict()
    for inc, filas in por_inc.items():
        filas.sort(key=lambda t: (t[2].get("ASIGNACION") if isinstance(t[2].get("ASIGNACION"), datetime) else datetime.min, PRIORIDAD_HOJA.get(t[0], 9), t[1]))
        base: dict = {}
        notas, avisos = [], []
        for hoja, fila, d in filas:                       # lo último no vacío gana
            base.update({k: v for k, v in d.items() if not _vacio(v)})
            if d.get("NUMERO AVISO"):
                texto = str(d["NUMERO AVISO"]).strip()
                sueltos = ["".join(m) for m in RX_AVISO.findall(texto)] or [texto]   # una celda puede traer varios avisos
                for a in sueltos:
                    if a not in avisos:
                        avisos.append(a)
            ev = d.get("EVIDENCIA")
            if ev and str(ev).strip() not in [n for _, n in notas]:
                notas.append((d.get("ASIGNACION"), str(ev).strip()))
        base["Incidencia"] = inc
        base["NUMERO AVISO"] = avisos[-1] if avisos else None
        base["Otros avisos"] = ", ".join(a for a in avisos[:-1]) or None
        if len(notas) > 1:                                 # varias notas distintas: se conservan todas con su fecha
            base["EVIDENCIA"] = "\n".join(f"{n[0]:%d/%m}: {n[1]}" if isinstance(n[0], datetime) else n[1] for n in notas)
        base["Origen"] = ", ".join(dict.fromkeys(h for h, _, _ in filas))
        base["N° de asignaciones"] = len(filas)
        if len(filas) > 1:
            lineas = []
            for hoja, fila, d in filas:
                fecha = d.get("ASIGNACION")
                partes = [f"{k}: {d[k]}" for k in d
                          if k not in ("ASIGNACION", "Incidencia") and not _vacio(d[k]) and str(d[k]).strip() != str(base.get(k, "")).strip()]
                lineas.append(f"{fecha:%d/%m/%Y}" if isinstance(fecha, datetime) else "(sin fecha)")
                lineas[-1] += f" [{hoja}, fila {fila}]" + (" · " + " | ".join(partes) if partes else "")
            base["Historial de asignaciones"] = "\n".join(lineas)
        unificadas[inc] = base

    def fila_de(inc: str, hoja_origen: str, **datos) -> dict:
        if inc not in unificadas:
            unificadas[inc] = {"Incidencia": inc, "Origen": hoja_origen, "N° de asignaciones": 0}
        return unificadas[inc]

    # TABLA EVIDENCIAS: dos bloques (CENTRAL: columnas A-K, OESTE: M-T)
    if "TABLA EVIDENCIAS" in wb.sheetnames:
        filas = [list(r) for r in wb["TABLA EVIDENCIAS"].iter_rows(max_col=24, values_only=True)]
        for r in filas[2:]:
            for ini, fin, territorio in ((0, 11, "CENTRAL"), (12, 20, "OESTE")):
                bloque = r[ini:fin]
                inc = _inc(bloque[1] if ini == 0 else bloque[0])
                if not inc:
                    continue
                if ini == 0:
                    resp, _, fdet, fsr, tcausa, causa, pend, jt, aviso, terr, fecha_tabla = [_limpio(x) for x in bloque]
                else:
                    resp, (fdet, fsr, tcausa, causa, pend, jt, aviso) = None, [_limpio(x) for x in bloque[1:8]]
                    terr, fecha_tabla = "OESTE", None
                f = fila_de(inc, "TABLA EVIDENCIAS")
                if resp and "Asignado a" not in f:
                    f["Asignado a"] = str(resp).title()
                for col, val in (("Fecha Detección", fdet), ("Fecha SR", fsr), ("Tipo de Causa", tcausa), ("Causa", causa)):
                    _poner(f, col, val, "TABLA EVIDENCIAS")
                if fecha_tabla:
                    _poner(f, "Fecha tabla", fecha_tabla, "TABLA EVIDENCIAS")
                for col, val in (("Pendiente de evidencia", pend), ("JT", jt), ("Responsable tabla", str(resp).title() if resp else None),
                                 ("TERRITORIO", terr or territorio)):
                    if _vacio(val):
                        continue
                    etiqueta = f"{territorio}: {val}"
                    if _vacio(f.get(col)):
                        f[col] = val
                    elif str(val).strip() not in str(f[col]):
                        f[col] = f"{f[col]}  |  {etiqueta}" if " | " in str(f[col]) or ":" in str(f[col])[:12] else f"{f[col]}  |  {etiqueta}"
                if aviso and str(aviso).strip():
                    av = str(aviso).strip()
                    if av != str(f.get("NUMERO AVISO") or "") and av not in str(f.get("Otros avisos") or ""):
                        f["Otros avisos"] = ", ".join(x for x in (f.get("Otros avisos"), av) if x)
                    if not f.get("NUMERO AVISO"):
                        f["NUMERO AVISO"], f["Otros avisos"] = av, (f.get("Otros avisos") or "").replace(av, "").strip(", ") or None
    # CIERRE DE INCIDENCIAS: todas sus columnas (menos las que ya existen en la fila base)
    for _, d in _aux(wb, "CIERRE DE INCIDENCIAS", con_encabezado=True):
        inc = _inc(d.get("Incidencia"))
        if not inc:
            continue
        f = fila_de(inc, "CIERRE DE INCIDENCIAS")
        for k, v in d.items():
            if k in ("Incidencia", "Causa", "Fecha Detección", "Fecha SR", "Provincia", "Distrito", "Corregimiento"):
                _poner(f, k, v, "CIERRE DE INCIDENCIAS")
            elif k == "Zona":
                _poner(f, "zona", v, "CIERRE DE INCIDENCIAS")
            else:
                f[f"Cierre · {k}"] = v
    # C ENVIADOS
    for _, d in _aux(wb, "C ENVIADOS", con_encabezado=True):
        inc = _inc(d.get("Incidencia"))
        if inc:
            f = fila_de(inc, "C ENVIADOS")
            f["Anexo C enviado (C ENVIADOS)"] = d.get("x", "enviado")
            for k in ("Fecha Detección", "Fecha SR", "Causa"):
                _poner(f, k, d.get(k), "C ENVIADOS")
    # Hoja1: una incidencia ("Radicado") con filas de continuación que traen la lista de pruebas
    if "Hoja1" in wb.sheetnames:
        actual = None
        for _, r in _leer_hoja(wb["Hoja1"], con_encabezado=True, max_col=12):
            inc = _inc(r.get("Radicado"))
            if inc:
                actual = fila_de(inc, "Hoja1")
                for k in ("#", "Causa / Detalle", "Otras pruebas en PDF Actual", "Otras pruebas a Colocar (Propuesto)", "Acción Aplicada", "subido"):
                    if r.get(k):
                        actual[f"Acciones · {k}"] = str(r[k])
            elif actual is not None:
                for k in ("Otras pruebas en PDF Actual", "Otras pruebas a Colocar (Propuesto)", "Acción Aplicada"):
                    if r.get(k):
                        clave = f"Acciones · {k}"
                        actual[clave] = (actual.get(clave) + "\n" if actual.get(clave) else "") + str(r[k])
    wb.close()  # libera el archivo original (en Windows queda bloqueado mientras esté abierto)
    return _escribir(unificadas, ruta_salida)


def _columnas_para(unificadas: dict) -> list[tuple]:
    """Las columnas previstas + cualquier columna extra que haya traído alguna hoja (se agrega al final de su grupo)."""
    previstas = {c[0] for c in COLUMNAS}
    extras = sorted({k for d in unificadas.values() for k in d if k not in previstas and not k.startswith("_")})
    cols = list(COLUMNAS)
    for k in extras:
        grupo = "cierre" if k.startswith("Cierre") else "acciones" if k.startswith("Acciones") else "anexos"
        pos = max(i for i, c in enumerate(cols) if c[2] == grupo) + 1
        cols.insert(pos, (k, k, grupo, 14))
    return cols


# Anchos para las columnas de texto largo (así cada registro ocupa UNA fila baja en vez de crecer hacia abajo)
ANCHO_TEXTO = {
    "Descripcion": 60, "Observaciones": 110, "EVIDENCIA": 75, "Historial de asignaciones": 130, "Notas de consolidación": 80,
    "Instalación": 32, "causa_agrupadora": 26, "Origen": 36, "Pendiente de evidencia": 36, "JT": 30, "Cierre · Asunto": 52,
    "Cierre · Ficheros": 52, "Cierre · OBSERVACION": 60, "Acciones · Causa / Detalle": 52, "Acciones · Otras pruebas en PDF Actual": 75,
    "Acciones · Otras pruebas a Colocar (Propuesto)": 75, "Acciones · Acción Aplicada": 52, "Estado_Automatico": 46, "Ruta_Evidencia": 80,
}


def _hoja_base(wb: Workbook, titulo: str, filas: dict, cols: list[tuple], color_pestana: str) -> None:
    ws = wb.create_sheet(titulo)
    ws.sheet_properties.tabColor = color_pestana
    fino = Side(style="thin", color="D9D9D9")
    for c, (clave, titulo_col, grupo, ancho) in enumerate(cols, 1):
        h = ws.cell(row=1, column=c, value=titulo_col)
        h.font, h.fill = Font(bold=True, color="FFFFFF", size=10), PatternFill("solid", fgColor=BAND[grupo])
        h.alignment, h.border = Alignment(horizontal="center", vertical="center", wrap_text=True), Border(bottom=Side(style="medium", color="FFFFFF"))
        ws.column_dimensions[get_column_letter(c)].width = max(ancho, ANCHO_TEXTO.get(clave, 0))
    ws.row_dimensions[1].height = 34

    def clave_orden(item):
        f = item[1].get("Fecha Detección")
        return (f if isinstance(f, datetime) else datetime.max, item[0])

    for r, (inc, d) in enumerate(sorted(filas.items(), key=clave_orden), 2):
        ws.row_dimensions[r].height = ALTO_FILA
        for c, (clave, titulo_col, grupo, ancho) in enumerate(cols, 1):
            v = d.get(clave)
            celda = ws.cell(row=r, column=c, value=(int(v) if clave == "Incidencia" and v is not None else v))
            celda.alignment = Alignment(vertical="center", wrap_text=False)   # sin ajustar texto: la fila no crece
            celda.border = Border(bottom=fino)
            if clave in COLUMNAS_FECHA:
                celda.number_format = "dd/mm/yyyy hh:mm" if clave != "ASIGNACION" else "dd/mm/yyyy"
            if r % 2 == 1:
                celda.fill = PatternFill("solid", fgColor="F7F9FC")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(filas), 1) + 1}"
    ws.sheet_view.zoomScale = 90
    for grupo in ("anexos", "cierre", "acciones"):   # grupos plegables ([-] / [+] arriba en Excel); quedan visibles
        idx = [c for c, col in enumerate(cols, 1) if col[2] == grupo]
        ws.column_dimensions.group(get_column_letter(idx[0]), get_column_letter(idx[-1]), outline_level=1, hidden=False)


def _escribir(unificadas: dict, ruta_salida: Path) -> dict:
    """Escribe el libro con DOS hojas: «Histórico» (todo lo procesado) y «Nuevas» (lo que va llegando). La fila lleva su hoja en `_hoja`."""
    global COLUMNAS_USADAS
    for d in unificadas.values():
        if d.get("_conflictos"):
            d["Notas de consolidación"] = "\n".join(d["_conflictos"])
    cols = COLUMNAS_USADAS = _columnas_para(unificadas)
    nuevas = {k: v for k, v in unificadas.items() if v.get("_hoja") == HOJA_NUEVAS}
    historico = {k: v for k, v in unificadas.items() if k not in nuevas}
    wb = Workbook()
    wb.remove(wb.active)
    _hoja_base(wb, HOJA_HISTORICO, historico, cols, "1F3864")
    _hoja_base(wb, HOJA_NUEVAS, nuevas, cols, "16A34A")
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta_salida.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    os.replace(tmp, ruta_salida)
    return {"incidencias": len(unificadas), "historico": len(historico), "nuevas": len(nuevas), "columnas": len(cols), "salida": str(ruta_salida)}
