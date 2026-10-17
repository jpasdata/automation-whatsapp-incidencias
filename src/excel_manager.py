"""
Lectura y escritura del Excel de incidencias.

Usa openpyxl directamente (NO pandas.to_excel) a propósito: el archivo
real (`RESULTADO_CREACION_INCIDENCIAS.xlsx`) tiene 7 hojas además de la
de incidencias ("c ya entregados sin correo", "OCTUBRE", "TABLA
EVIDENCIAS", "CIERRE DE INCIDENCIAS", "C ENVIADOS", "Hoja1"). Si se
reescribiera el archivo con pandas se perderían esas hojas y el
formato. Aquí solo se tocan las celdas necesarias de la hoja de
incidencias, dejando todo lo demás intacto.

Criterio de búsqueda en cascada (como lo hace Henry a mano):
  1. Por código de incidencia (corto o largo).
  2. Si no aparece, por número de elemento (mencionado dentro del texto
     libre de Observaciones, ej. "...apertura del elemento F3092...").
     Solo 25 de las 240 filas reales tienen un número de elemento
     explícito — la mayoría solo dice el TIPO de elemento ("fusible",
     "interruptor") sin número, y en esos casos este paso no aplica.
  3. Si tampoco, por número de aviso (columna NUMERO AVISO, 137/240 filas la tienen).
  4. Si ninguno de los tres aparece: no se encontró, hay que pedir evidencia.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import logging

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from .modelos import CriterioBusqueda, normalizar_texto


class ExcelManagerError(Exception):
    pass


# --- Análisis de la columna EVIDENCIA (notas manuales libres) ---------
#
# La columna EVIDENCIA no es un estado limpio; son notas que Jeam/Henry
# escriben a mano con decenas de variantes. Esta categorización es un
# punto de partida para discutir con el usuario qué agrupa qué — no es
# la palabra final. Ver README, sección "Pendientes".

PALABRAS_CON_EVIDENCIA = ("ok", "video ok", "foto y video", "si")
PALABRAS_PENDIENTE = ("pendiente", "pedir", "buscar", "debo", "sin foto", "sin video", "no lleva", "no aparece")
PALABRAS_NO_APLICA = ("no procede", "anulada", "n/a")

# "elemento F3092", "elemento 30350", "elemento F03152"... pero NO
# "elemento fusible" ni "elemento interruptor" (eso es el tipo, no un
# número identificable). Por eso se exige al menos un dígito.
PATRON_NUMERO_ELEMENTO = re.compile(r"elemento\s+([A-Za-z]{0,3}\d[A-Za-z0-9\-/]*)", re.IGNORECASE)


def categorizar_nota_evidencia(nota: str | None) -> str:
    """
    Clasifica una nota libre de la columna EVIDENCIA en un bucket.
    Devuelve: "con_evidencia" | "pendiente" | "no_aplica" | "sin_dato" | "revisar_manual"

    Esto es heurístico a propósito (string matching, no IA): el objetivo
    es dar un primer corte rápido para que el usuario revise los casos
    "revisar_manual" y así ir afinando las reglas con datos reales.
    """
    if nota is None:
        return "sin_dato"

    texto = str(nota).strip().lower()
    if not texto:
        return "sin_dato"

    if any(p in texto for p in PALABRAS_NO_APLICA):
        return "no_aplica"
    if any(p in texto for p in PALABRAS_PENDIENTE):
        return "pendiente"
    if any(p in texto for p in PALABRAS_CON_EVIDENCIA):
        return "con_evidencia"
    return "revisar_manual"


PATRON_AVISO_LIBRE = re.compile(r"(?<!\d)(5[67]\d)-?(\d{4})(?!\d)")


def extraer_avisos(*textos, excluir: str | None = None) -> tuple[str, ...]:
    """Números de aviso (7 dígitos que empiezan en 56/57) escritos en texto libre; sin repetir y sin el que ya está en NUMERO AVISO."""
    vistos: list[str] = []
    for t in textos:
        for a, b in PATRON_AVISO_LIBRE.findall(str(t or "")):
            n = a + b
            if n != excluir and n not in vistos:
                vistos.append(n)
    return tuple(vistos)


def extraer_numero_elemento(observaciones: str | None) -> str | None:
    """
    Busca un número de elemento dentro del texto libre de Observaciones.
    Devuelve None si Observaciones solo menciona el TIPO de elemento
    ("fusible", "interruptor") sin un código/número específico.
    """
    if not observaciones:
        return None
    match = PATRON_NUMERO_ELEMENTO.search(str(observaciones))
    return match.group(1) if match else None


logger = logging.getLogger("incidencias_wa")


@dataclass
class FilaIncidencia:
    fila_excel: int  # número de fila real en la hoja (1-indexed, incluye encabezado)
    codigo_largo: str | None
    codigo_corto: str | None
    numero_elemento: str | None
    numero_aviso: str | None
    fecha_deteccion: datetime | None
    fecha_sr: datetime | None
    nota_evidencia_manual: str | None
    categoria_nota_manual: str
    provincia: str | None = None  # normalizada (sin tildes, mayúsculas)
    avisos_extra: tuple[str, ...] = ()  # avisos escritos en Observaciones/Descripcion/EVIDENCIA (la columna NUMERO AVISO suele estar vacía)
    hoja: str = ""  # "" = hoja principal; si no, el nombre de la hoja adicional de donde salió la fila


class ExcelManager:
    def __init__(
        self,
        ruta_archivo: str,
        nombre_hoja: str,
        columna_codigo_largo: str,
        columna_codigo_corto: str,
        columna_evidencia_manual: str,
        columna_estado_automatico: str,
        columna_ruta_foto: str,
        columna_observaciones: str | None = "Observaciones",
        columna_numero_aviso: str | None = "NUMERO AVISO",
        columna_fecha_deteccion: str | None = "Fecha Detección",
        columna_fecha_sr: str | None = "Fecha SR",
        columna_provincia: str | None = None,
        hojas_extra: list[str] | None = None,
        asignado_a: str | None = None,
    ):
        self.asignado_a = asignado_a or None
        self.hojas_extra = list(hojas_extra or [])
        self._extra: dict[str, tuple] = {}  # hoja adicional -> (hoja de valores, índice de columnas)
        self.ruta_archivo = Path(ruta_archivo)
        self.nombre_hoja = nombre_hoja
        self.columna_codigo_largo = columna_codigo_largo
        self.columna_codigo_corto = columna_codigo_corto
        self.columna_evidencia_manual = columna_evidencia_manual
        self.columna_estado_automatico = columna_estado_automatico
        self.columna_ruta_foto = columna_ruta_foto
        # Estas cuatro son opcionales: si vienen vacías o no existen en
        # la hoja, simplemente se saltan esos pasos de la cascada en vez
        # de reventar — así el script sigue siendo útil aunque el Excel
        # cambie de columnas en el futuro.
        self.columna_observaciones = columna_observaciones or None
        self.columna_numero_aviso = columna_numero_aviso or None
        self.columna_fecha_deteccion = columna_fecha_deteccion or None
        self.columna_fecha_sr = columna_fecha_sr or None
        self.columna_provincia = columna_provincia or None

        self._wb = None
        self._ws: Worksheet | None = None
        self._ws_valores: Worksheet | None = None
        self._idx_por_nombre: dict[str, int] = {}
        self._filas_cache: list | None = None

    @classmethod
    def desde_config(cls, ruta_archivo: str, e) -> "ExcelManager":
        """Crea el manager con todo lo de la sección `excel` de config.yaml (incluidas las hojas adicionales)."""
        return cls(ruta_archivo, e.nombre_hoja, e.columna_codigo_largo, e.columna_codigo_corto, e.columna_evidencia_manual,
                   e.columna_estado_automatico, e.columna_ruta_foto, e.columna_observaciones, e.columna_numero_aviso,
                   e.columna_fecha_deteccion, e.columna_fecha_sr, e.columna_provincia, hojas_extra=getattr(e, "hojas_extra", None),
                   asignado_a=getattr(e, "asignado_a", None))

    def abrir(self) -> None:
        if not self.ruta_archivo.exists():
            raise ExcelManagerError(f"No existe el archivo: {self.ruta_archivo}")

        self._wb = openpyxl.load_workbook(self.ruta_archivo)
        if self.nombre_hoja not in self._wb.sheetnames:
            raise ExcelManagerError(
                f"La hoja '{self.nombre_hoja}' no existe. Hojas disponibles: {self._wb.sheetnames}"
            )
        self._ws = self._wb[self.nombre_hoja]
        # Hoja gemela con los valores calculados: columnas como COD-INCIDENCIA
        # son fórmulas, y sin data_only openpyxl devuelve el texto de la
        # fórmula. Solo se lee de aquí; las escrituras van a self._ws.
        wb_valores = openpyxl.load_workbook(self.ruta_archivo, data_only=True)
        self._ws_valores = wb_valores[self.nombre_hoja]
        self._mapear_columnas()
        self._asegurar_columnas_nuevas()
        self._abrir_hojas_extra(wb_valores)
        self._filas_cache = None

    def _abrir_hojas_extra(self, wb_valores) -> None:
        """
        Hojas adicionales con más incidencias del mismo responsable (p. ej. 'OCTUBRE', 'c ya entregados sin correo').
        Se usan columnas por nombre si la hoja tiene encabezado; si no lo tiene (la primera fila ya es un dato), se
        asume la misma disposición de columnas que la hoja principal. Solo se LEEN (el estado se escribe en la principal).
        """
        self._extra = {}
        for nombre in self.hojas_extra:
            if nombre not in wb_valores.sheetnames:
                logger.warning("La hoja adicional '%s' no existe en el Excel; se omite. Hojas: %s", nombre, wb_valores.sheetnames)
                continue
            ws = wb_valores[nombre]
            nombres = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
            if self.columna_codigo_largo in nombres:
                idx, primera = nombres, 2
            else:  # sin encabezado: misma disposición que la hoja principal
                idx, primera = dict(self._idx_por_nombre), 1
            self._extra[nombre] = (ws, idx, primera)
            logger.info("Hoja adicional '%s': %s", nombre, "con encabezado" if primera == 2 else "sin encabezado (columnas como la principal)")

    def _mapear_columnas(self) -> None:
        encabezado = self._ws[1]
        self._idx_por_nombre = {
            str(celda.value).strip(): celda.column
            for celda in encabezado
            if celda.value is not None
        }
        for requerida in (self.columna_codigo_largo, self.columna_codigo_corto, self.columna_evidencia_manual):
            if requerida not in self._idx_por_nombre:
                raise ExcelManagerError(
                    f"No se encontró la columna '{requerida}' en la fila de encabezados. "
                    f"Columnas encontradas: {list(self._idx_por_nombre.keys())}"
                )

        # Las columnas opcionales, si se configuraron con un nombre pero
        # ese nombre no existe en la hoja, sí deben avisar (probablemente
        # un typo en config.yaml) -- distinto de no haberlas configurado.
        for opcional in (
            self.columna_observaciones,
            self.columna_numero_aviso,
            self.columna_fecha_deteccion,
            self.columna_fecha_sr,
            self.columna_provincia,
        ):
            if opcional and opcional not in self._idx_por_nombre:
                raise ExcelManagerError(
                    f"No se encontró la columna opcional '{opcional}' en la hoja. "
                    f"Si no la necesitas, pon esa clave vacía ('') en config.yaml. "
                    f"Columnas encontradas: {list(self._idx_por_nombre.keys())}"
                )

    def _asegurar_columnas_nuevas(self) -> None:
        """Crea Estado_Automatico y Ruta_Evidencia al final si no existen aún."""
        for nombre_columna in (self.columna_estado_automatico, self.columna_ruta_foto):
            if nombre_columna not in self._idx_por_nombre:
                # NO usar ws.max_column: hojas con formato hasta el final reportan 16383.
                nueva_col_idx = max(self._idx_por_nombre.values()) + 1
                self._ws.cell(row=1, column=nueva_col_idx, value=nombre_columna)
                self._idx_por_nombre[nombre_columna] = nueva_col_idx

    def _valor(self, fila_num: int, nombre_columna: str | None):
        if not nombre_columna:
            return None
        col = self._idx_por_nombre.get(nombre_columna)
        if col is None:
            return None
        return self._ws_valores.cell(row=fila_num, column=col).value

    def leer_filas(self) -> list[FilaIncidencia]:
        """Devuelve todas las filas de datos ya normalizadas."""
        if self._ws is None:
            raise ExcelManagerError("Llama a abrir() antes de leer_filas().")
        if self._filas_cache is not None:  # leer el Excel celda por celda es lento y se pide muchas veces por cruce
            return self._filas_cache

        filas: list[FilaIncidencia] = []
        col_largo = self._idx_por_nombre[self.columna_codigo_largo]
        col_corto = self._idx_por_nombre[self.columna_codigo_corto]
        col_evid = self._idx_por_nombre[self.columna_evidencia_manual]

        for fila_num in range(2, self._ws.max_row + 1):
            codigo_largo = self._ws_valores.cell(row=fila_num, column=col_largo).value
            if codigo_largo is None:
                continue  # fila vacía, probablemente el final de los datos reales

            if not self._es_del_responsable(self._valor(fila_num, "Asignado a")):
                continue
            nota = self._ws_valores.cell(row=fila_num, column=col_evid).value
            observaciones = self._valor(fila_num, self.columna_observaciones)

            filas.append(
                FilaIncidencia(
                    fila_excel=fila_num,
                    codigo_largo=str(codigo_largo).strip(),
                    codigo_corto=str(self._ws_valores.cell(row=fila_num, column=col_corto).value or "").strip() or None,
                    numero_elemento=extraer_numero_elemento(observaciones),
                    numero_aviso=self._normalizar_identificador(self._valor(fila_num, self.columna_numero_aviso)),
                    fecha_deteccion=self._valor(fila_num, self.columna_fecha_deteccion),
                    fecha_sr=self._valor(fila_num, self.columna_fecha_sr),
                    nota_evidencia_manual=nota,
                    categoria_nota_manual=categorizar_nota_evidencia(nota),
                    provincia=normalizar_texto(self._valor(fila_num, self.columna_provincia)),
                    avisos_extra=extraer_avisos(observaciones, self._valor(fila_num, "Descripcion"), nota, self._valor(fila_num, "Otros avisos"),
                                                self._valor(fila_num, "Historial de asignaciones"),
                                                excluir=self._normalizar_identificador(self._valor(fila_num, self.columna_numero_aviso))),
                )
            )
        vistos = {f.codigo_largo for f in filas} | {f.codigo_corto for f in filas if f.codigo_corto}
        for nombre, (ws, idx, primera) in self._extra.items():
            def val(fila_num, col, ws=ws, idx=idx):
                c = idx.get(col) if col else None
                return ws.cell(row=fila_num, column=c).value if c else None
            for fila_num in range(primera, ws.max_row + 1):
                largo = val(fila_num, self.columna_codigo_largo)
                if largo is None or not str(largo).strip().isdigit():
                    continue  # vacía, encabezado o subtotal
                corto = str(val(fila_num, self.columna_codigo_corto) or "").strip() or None
                if str(largo).strip() in vistos or (corto and corto in vistos):
                    continue  # ya viene en la hoja principal
                vistos.add(str(largo).strip())
                if not self._es_del_responsable(val(fila_num, "Asignado a")):
                    continue
                nota = val(fila_num, self.columna_evidencia_manual)
                observaciones = val(fila_num, self.columna_observaciones)
                filas.append(FilaIncidencia(
                    fila_excel=fila_num, codigo_largo=str(largo).strip(), codigo_corto=corto,
                    numero_elemento=extraer_numero_elemento(observaciones),
                    numero_aviso=self._normalizar_identificador(val(fila_num, self.columna_numero_aviso)),
                    fecha_deteccion=val(fila_num, self.columna_fecha_deteccion), fecha_sr=val(fila_num, self.columna_fecha_sr),
                    nota_evidencia_manual=nota, categoria_nota_manual=categorizar_nota_evidencia(nota),
                    provincia=normalizar_texto(val(fila_num, self.columna_provincia)), hoja=nombre,
                    avisos_extra=extraer_avisos(observaciones, val(fila_num, "Descripcion"), nota,
                                                excluir=self._normalizar_identificador(val(fila_num, self.columna_numero_aviso))),
                ))
        for f in filas:
            self._separar_avisos_multiples(f)
        self._filas_cache = filas
        return filas

    @staticmethod
    def _separar_avisos_multiples(f: "FilaIncidencia") -> None:
        """Una celda NUMERO AVISO con varios avisos ("5628632, 5629719") no sirve para buscar: se separan; el primero queda como aviso."""
        nums = extraer_avisos(f.numero_aviso)
        if len(nums) >= 2:
            f.numero_aviso = nums[0]
            f.avisos_extra = tuple(dict.fromkeys((*nums[1:], *f.avisos_extra)))

    def _es_del_responsable(self, valor) -> bool:
        """Con `asignado_a` configurado (p. ej. "Henry"), solo cuentan las filas de ese responsable. Si no hay filtro, todas."""
        if not self.asignado_a:
            return True
        return (normalizar_texto(self.asignado_a) or "") in (normalizar_texto(valor) or "\0")

    @staticmethod
    def _normalizar_identificador(valor) -> str | None:
        if valor is None:
            return None
        texto = str(valor).strip()
        return texto or None

    def buscar_fila_por_codigo(self, codigo: str) -> FilaIncidencia | None:
        """Busca por código largo o corto, probando ambos."""
        codigo = codigo.strip()
        for fila in self.leer_filas():
            if fila.codigo_largo == codigo or fila.codigo_corto == codigo:
                return fila
        return None

    @staticmethod
    def _filtrar_por_provincias(filas: list["FilaIncidencia"], provincias: set[str] | None) -> list["FilaIncidencia"]:
        """
        Deja solo las filas de las provincias que atiende el grupo. Las filas sin
        provincia o con "SIN DATOS" se conservan: no se puede descartar lo que no se sabe.
        """
        if not provincias:
            return filas
        return [f for f in filas if f.provincia in (None, "SIN DATOS") or f.provincia in provincias]

    def resumen_por_provincia(self) -> dict[str, int]:
        """Cuántas incidencias hay por provincia (para saber cuántas se esperan de cada grupo)."""
        cuenta: dict[str, int] = {}
        for f in self.leer_filas():
            clave = f.provincia or "(sin provincia)"
            cuenta[clave] = cuenta.get(clave, 0) + 1
        return dict(sorted(cuenta.items(), key=lambda kv: -kv[1]))

    def buscar_fila_por_identificadores(
        self,
        codigo: str | None = None,
        numero_elemento: str | None = None,
        numero_aviso: str | None = None,
        provincias: set[str] | None = None,
    ) -> tuple[FilaIncidencia | None, CriterioBusqueda]:
        """
        Cascada de búsqueda tal como la hace Henry a mano:
          1. código de incidencia (corto o largo)
          2. número de elemento
          3. número de aviso
          4. nada -> NO_ENCONTRADO (hay que pedir evidencia)

        Devuelve la fila encontrada (o None) junto con el criterio que
        la encontró, para poder loguearlo y que quede claro por qué se
        asoció cada evidencia.
        """
        filas = self._filtrar_por_provincias(self.leer_filas(), provincias)

        if codigo:
            codigo = codigo.strip()
            for fila in filas:
                if fila.codigo_largo == codigo or fila.codigo_corto == codigo:
                    return fila, CriterioBusqueda.CODIGO

        if numero_elemento:
            numero_elemento = numero_elemento.strip()
            for fila in filas:
                if fila.numero_elemento and fila.numero_elemento.lower() == numero_elemento.lower():
                    return fila, CriterioBusqueda.NUMERO_ELEMENTO

        if numero_aviso:
            numero_aviso = numero_aviso.strip()
            for fila in filas:
                if (fila.numero_aviso and fila.numero_aviso == numero_aviso) or numero_aviso in fila.avisos_extra:
                    return fila, CriterioBusqueda.NUMERO_AVISO

        return None, CriterioBusqueda.NO_ENCONTRADO

    def buscar_fila_por_candidatos(
        self, candidatos: list[str], provincias: set[str] | None = None
    ) -> tuple[FilaIncidencia | None, CriterioBusqueda, str | None]:
        """
        Cascada de Henry aplicada a TODOS los números de un mensaje (que puede
        traer incidencia, elemento y aviso a la vez): primero se prueban todos
        como código; luego todos como elemento; luego todos como aviso.
        Devuelve (fila, criterio, número_que_acertó).
        """
        for criterio in (CriterioBusqueda.CODIGO, CriterioBusqueda.NUMERO_ELEMENTO, CriterioBusqueda.NUMERO_AVISO):
            for cand in candidatos:
                fila, encontrado = self.buscar_fila_por_identificadores(
                    codigo=cand if criterio == CriterioBusqueda.CODIGO else None,
                    numero_elemento=cand if criterio == CriterioBusqueda.NUMERO_ELEMENTO else None,
                    numero_aviso=cand if criterio == CriterioBusqueda.NUMERO_AVISO else None,
                    provincias=provincias,
                )
                if fila is not None:
                    return fila, encontrado, cand
        return None, CriterioBusqueda.NO_ENCONTRADO, None

    def actualizar_estado_automatico(self, fila_excel: int, estado: str, ruta_foto: str | None) -> None:
        """Escribe en las columnas NUEVAS (Estado_Automatico / Ruta_Evidencia).
        Nunca toca la columna EVIDENCIA original con las notas manuales."""
        if self._ws is None:
            raise ExcelManagerError("Llama a abrir() antes de actualizar.")
        col_estado = self._idx_por_nombre[self.columna_estado_automatico]
        col_ruta = self._idx_por_nombre[self.columna_ruta_foto]
        self._ws.cell(row=fila_excel, column=col_estado, value=estado)
        if ruta_foto:
            self._ws.cell(row=fila_excel, column=col_ruta, value=ruta_foto)

    def guardar(self) -> None:
        if self._wb is None:
            raise ExcelManagerError("Nada que guardar: llama a abrir() primero.")
        self._wb.save(self.ruta_archivo)

    def guardar_copia(self, ruta_destino: str) -> None:
        """Guarda en una ruta distinta — útil para no arriesgar el archivo
        original mientras se valida que todo funciona bien."""
        if self._wb is None:
            raise ExcelManagerError("Nada que guardar: llama a abrir() primero.")
        self._wb.save(ruta_destino)
