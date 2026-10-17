---
title: Requerimiento de Henry (criterio real de búsqueda)
fecha_registro: 2026-10-15
quien_lo_dio: Jeam Pi, transmitiendo el criterio que usa Henry al revisar las evidencias
---

# Requerimiento de Henry

Henry es quien revisa lo que llega al grupo de WhatsApp y decide si una
incidencia tiene evidencia válida o no. Este es el criterio que él usa
a mano, transmitido textualmente por Jeam Pi el 2026-10-15:

## 1. Cascada de búsqueda (en este orden)

> "1 buscar evidencia por código de incidencia, sino con el número del
> elemento que está en la observación, sino con el número del aviso y
> si no sé encuentra [sic] PS no está y que diga para pedirla"

Es decir:
1. Buscar primero por **código de incidencia**.
2. Si no aparece, buscar por **número del elemento** (el dato está
   dentro del texto libre de la columna `Observaciones`, ej. "...se
   encontró el elemento F3092...").
3. Si tampoco, buscar por **número de aviso** (columna `NUMERO AVISO`).
4. Si ninguno de los tres aparece: **marcar explícitamente que no se
   encontró, para pedir la evidencia** (no dejarlo en un estado
   ambiguo o genérico).

## 2. Validación de horario

> "2 una vez identificado el mensaje que contiene las evidencias hay
> que ver si la evidencia fueron tomadas dentro de las horas"

Es decir: encontrar la fila del Excel no es suficiente — hay que
confirmar que la foto/video se envió dentro de la ventana de tiempo en
que ocurrió/se resolvió esa incidencia específica (entre `Fecha
Detección` y `Fecha SR`, con algo de margen porque en campo la
evidencia normalmente se manda un rato después de terminar). Si la
evidencia cae fuera de esa ventana, es sospechosa de pertenecer a otra
incidencia y debe marcarse para revisión manual, no darse por buena
automáticamente.

## 3. Canal de notificación (aclarado el mismo día)

> "Henry hace es quien revisa lo que llega, y me dice que por WhatsApp
> no se pide la evidencia sino por correo"

Henry **no** pide evidencia faltante por WhatsApp — lo hace por
correo. Por eso la automatización NO envía ningún mensaje de WhatsApp;
su trabajo termina en dejar el Excel actualizado (qué se encontró, por
cuál criterio, y si la ventana horaria es válida) para que Henry decida
a quién escribirle, por el canal que él ya usa.

## Dónde quedó implementado esto en el código

- Cascada de búsqueda: `src/excel_manager.py` →
  `ExcelManager.buscar_fila_por_identificadores()` y
  `extraer_numero_elemento()`.
- Validación de horario: `src/validacion_temporal.py` →
  `verificar_ventana_horaria()` (margen configurable en
  `config.yaml` → `matching.margen_horas_evidencia`, 4 horas por
  defecto — **pendiente de confirmar con Henry si ese número es
  correcto en la práctica**).
- Orquestación de ambos: `src/main.py` → `_procesar_resultados()`.
- Sin envío por WhatsApp: `src/main.py` ya no llama a ninguna fase de
  notificación; `src/notificador.py` quedó sin usar, documentado como
  idea a futuro (sería integración de correo, no de WhatsApp).

Tests que cubren este criterio: `tests/test_excel_manager.py`
(cascada) y `tests/test_validacion_temporal.py` (ventana horaria).
