---
title: Contexto general del proyecto — todo lo realizado hasta ahora
fecha_registro: 2026-10-15/16
---

# Contexto general: Automatización de Incidencias en WhatsApp

Este documento resume, de principio a fin, cómo se llegó al estado
actual del proyecto, para que cualquiera (incluyendo a Jeam Pi en el
futuro, o a quien retome esto) entienda el por qué de cada decisión
sin tener que releer toda la conversación original.

## 1. El problema original

Jeam Pi (Data/Analytics Engineer en Xuma Insurtech, soporte al equipo
comercial de Grupo Vanti) tiene un Excel de seguimiento de incidencias
de campo (`RESULTADO_CREACION_INCIDENCIAS.xlsx`, hoja `Asignacion-
SEP`, 240 filas reales al momento de armar esto). Los supervisores en
campo mandan evidencia (fotos/videos) de incidencias resueltas a un
grupo de WhatsApp. El problema:

- A veces escriben el código de la incidencia junto con la foto.
- A veces lo escriben en un mensaje separado, antes de la foto.
- A veces no escriben ningún código — solo mandan la foto.
- Bajar y organizar esas fotos a mano, y cruzarlas con el Excel, le
  toma tiempo. Un OCR sobre las fotos sería ideal pero no hay tiempo
  para desarrollarlo ahora.

**Idea inicial:** automatizar con Python + Playwright la lectura de
WhatsApp Web, bajar las fotos/videos, organizarlas en carpetas, y
cruzarlas con el Excel.

## 2. Primera iteración: research y especificación (antes de este chat)

En una sesión anterior (documentada en los HTML que Jeam adjuntó al
iniciar este chat) ya se había hecho un research inicial señalando
Playwright + sesión persistente (`launch_persistent_context`) como el
enfoque viable, y se había armado una primera especificación en
Markdown. **Dos de los repositorios de GitHub citados en esa
especificación anterior (`mukul007d-cole/whatsapp-auto-messager` y
`costaDario/playwright_whatsapp_automator`) no existen realmente** —
no aparecieron en ninguna búsqueda real durante esta sesión, así que
se marcaron como no confiables y no se usaron como referencia.

## 3. Búsqueda real de librerías (esta sesión)

Se investigó en PyPI/GitHub qué opciones reales existen:
- **WhatsPlay** (`markbus-ai/whatsplay`): wrapper Python sobre
  Playwright, mantenido activamente, soporta ES/EN.
- **open-wa / wa-automate-python**: wrapper Python sobre una librería
  Node.js, con descifrado de media probado en producción.
- **Playwright puro** (sin librería intermedia): más control fino
  sobre selectores — **esta fue la opción elegida por Jeam Pi**,
  porque da control total sobre la lógica de extracción específica
  que este caso necesita.

## 4. Excel real: lo que cambió los supuestos iniciales

Al revisar el Excel real (`RESULTADO_CREACION_INCIDENCIAS.xlsx`), se
encontraron varios hechos que invalidaron supuestos de la
especificación original:

- **No hay columna de teléfono** en ninguna parte del archivo.
- **`Asignado a` = "Henry" en las 240 filas**, sin excepción — no hay
  varios supervisores con su propio número ahí.
- El código tiene dos formas: `COD-INCIDENCIA` (12 dígitos, ej.
  `011682220001`) e `Incidencia` (número corto embebido, ej.
  `1168222`).
- La columna `EVIDENCIA` no es un estado limpio: es una nota libre que
  Henry/Jeam llenan a mano, con 30+ variantes de texto
  ("FOTO Y VIDEO OK", "PEDIR EVIDENCIAS", "CELULAR",
  "PENDIENTE VIDEO", etc.).
- El archivo tiene **7 hojas en total**, no solo la de incidencias
  (`Asignacion- SEP`, `c ya entregados sin correo`, `OCTUBRE`,
  `TABLA EVIDENCIAS`, `CIERRE DE INCIDENCIAS`, `C ENVIADOS`, `Hoja1`)
  — por eso el Excel se maneja con `openpyxl` directo y nunca con
  `pandas.to_excel`, que hubiera borrado las otras 6 hojas.
- De las 240 filas, solo **25 tienen un número de elemento explícito**
  en `Observaciones` (ej. "elemento F3092"); el resto solo menciona el
  TIPO de elemento ("fusible", "interruptor") sin número.
- **137 de 240 filas tienen `NUMERO AVISO`.**

Estos hechos fueron la base para diseñar la cascada de búsqueda que
pidió Henry (ver `requerimiento_henry.md`).

## 5. Decisiones tomadas en orden cronológico

1. **Alcance dividido en fases**, con una Fase 0 de exploración
   (solo lectura, sin tocar nada) antes de automatizar de verdad —
   para no construir sobre supuestos del formato real del código.
2. **Tres pendientes identificados** al no tener teléfonos ni
   destinatario claro: quién recibe el aviso, mapeo nombre→teléfono,
   formato real del código. Las dos primeras **se resolvieron solas**
   cuando Jeam confirmó que Henry notifica por correo, no por
   WhatsApp — eliminando la necesidad de esa fase completa.
3. **Henry dio su criterio real de búsqueda** (cascada código →
   elemento → aviso → "pedir evidencia") y de validación horaria
   (ver `requerimiento_henry.md`), que se implementó en
   `excel_manager.py` y el nuevo `validacion_temporal.py`.
4. **Se investigaron los Términos de Servicio de WhatsApp** antes de
   seguir, por pedido explícito de Jeam ("para tenerlo mapeado").
   Conclusión: no hay bloqueo técnico contra Playwright en sí, pero
   los Términos prohíben explícitamente "scrape data" y "usar clientes
   no oficiales" — esto SÍ aplica al proyecto, aunque el riesgo es
   menor que el de un bot de envío masivo porque esta automatización
   **no envía ningún mensaje**, solo lee y descarga. El detalle
   completo, con fuentes, está en el `README.md` del proyecto, sección
   "⚠️ Riesgo real".
5. **Pendiente explícito sobre el remitente**: `whatsapp_reader.py` ya
   captura quién mandó cada mensaje, pero hoy esa información solo se
   usa internamente (para el matching) y en el nombre de archivo de
   los casos "sin código" — **no se guarda en una columna del Excel
   para las incidencias que sí se encuentran.** Se le preguntó a Jeam
   si quiere que se agregue una columna `Remitente_WhatsApp`; quedó
   pendiente de respuesta cuando se le pidió este esquema visual en su
   lugar.

## 6. Qué construyó el proyecto (buenas prácticas pedidas por Jeam)

Jeam pidió explícitamente: buenas prácticas, log siempre, tests para
poder validar sin producción, librerías actualizadas, todo bien
verificado. Esto se hizo así:

- **Separación de capas**: lógica pura testeable (`matcher.py`,
  `excel_manager.py`, `validacion_temporal.py`, `config.py`) separada
  de la capa que depende de un navegador real (`whatsapp_session.py`,
  `whatsapp_reader.py`).
- **51 tests con pytest**, todos pasando, cubriendo los 3 casos de
  asociación código-foto, la cascada de búsqueda, la validación
  horaria, el manejo del Excel (sin dañar las otras 6 hojas, sin tocar
  la columna `EVIDENCIA` manual) y la carga de configuración.
- **Honestidad explícita sobre lo que NO se puede verificar desde
  aquí**: la capa que habla con WhatsApp Web real no tiene tests
  automáticos porque depende de una sesión viva — eso se valida
  corriendo `scripts/run_exploracion.py` contra el grupo real, no con
  pytest.
- **Logging**: archivo con rotación diaria (30 días) + consola, en
  todo el flujo (`src/logger.py`).
- **Dependencias fijas** (`playwright==1.64.0`, `pandas==2.3.3`,
  `openpyxl==3.1.5`, `PyYAML==6.0.3`) más
  `scripts/check_dependencies.py` para avisar de versiones nuevas sin
  actualizar solo.
- **Secretos fuera de git**: `config/config.yaml` (datos reales),
  `sesion_whatsapp/` (la sesión de WhatsApp), los `.xlsx` reales y los
  logs están en `.gitignore`.

## 7. Estado actual / qué falta

Ver la lista completa en `README.md`, sección "Qué falta para
considerar esto terminado". En resumen:
- [ ] Correr la Fase 0 (`run_exploracion.py`) contra el grupo real.
- [ ] Confirmar con ese reporte el formato real del
      código/elemento/aviso tal como se escribe en el chat.
- [ ] Ajustar `margen_horas_evidencia` (hoy 4h de punto de partida)
      con casos reales que Henry conozca.
- [ ] Conectar `descargar_adjunto()` con el locator real de cada
      burbuja en `main.py` (hoy preparado pero comentado, a la espera
      del recorrido real de mensajes).
- [ ] Decidir si se agrega la columna `Remitente_WhatsApp` al Excel.
- [ ] Validar con 2-3 corridas manuales antes de tarea programada.
- [ ] Decidir, antes de correr esto en serio, si se usa un número de
      WhatsApp secundario (recomendado) en vez del número principal de
      Jeam, por el riesgo de Términos de Servicio ya documentado.

## 8. Dónde está cada cosa

- Código: carpeta `src/` del proyecto.
- Configuración: `config/config.example.yaml` (copiar a
  `config/config.yaml` y llenar con datos reales).
- Tests: `tests/`.
- Este contexto: `context/` (esta carpeta).
- Esquema visual del flujo completo (para ver en el móvil):
  artifact publicado en Claude — pedir el link si se perdió, o
  regenerarlo pidiéndole a Claude "el esquema visual del flujo".
