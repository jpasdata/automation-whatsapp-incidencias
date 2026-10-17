# Automatización de Incidencias en WhatsApp Web

Descarga fotos/videos de incidencias que mandan en un grupo de
WhatsApp, las organiza en carpetas, y las cruza con el Excel de
seguimiento marcando qué se encontró y qué no.

**Alcance actual: solo resolver el lado de WhatsApp.** No manda
ningún mensaje ni notificación. Henry (quien revisa lo que llega) avisa
por CORREO cuando falta evidencia, no por WhatsApp — así que esa parte
queda fuera de esta automatización. El resultado que necesita es el
Excel actualizado: con eso decide a quién pedirle qué, por el canal
que ya usa. `src/notificador.py` queda en el proyecto solo como una
idea para el futuro (ver más abajo), pero no se usa en el flujo.

## ⚠️ Riesgo real: esto no está cubierto por los Términos de Servicio de WhatsApp

Investigado directamente en las políticas oficiales de WhatsApp
(`whatsapp.com/legal/messaging-guidelines`) antes de automatizar nada
de verdad, para que quede mapeado:

**No existe una restricción técnica que bloquee usar Playwright en sí**
— esto no es como instalar un cliente modificado (WhatsApp+, GB
WhatsApp), que WhatsApp bloquea de forma explícita y agresiva hasta
que se desinstala. Aquí se controla el navegador real contra el
WhatsApp Web oficial (`web.whatsapp.com`), tal cual lo usaría una
persona.

**Pero sí hay una restricción explícita en los Términos de Servicio**
que aplica directamente a este proyecto. Bajo "no realizar
comportamiento adversario", WhatsApp prohíbe:
- "scrape data" (extraer datos mediante scraping) — esto es
  literalmente lo que hace `whatsapp_reader.py`.
- "use unofficial clients" (usar clientes no oficiales) — Playwright
  conduciendo el navegador para leer/descargar cae aquí.
- automatización que "undermine WhatsApp integrity systems" o
  "compromise user accounts".

También prohíbe mensajería masiva, auto-mensajería y auto-discado —
eso no aplica a este proyecto porque **no envía ningún mensaje** (la
fase de notificación se descartó, ver arriba), solo lee y descarga.
Eso reduce el riesgo frente a un bot que manda mensajes, pero no lo
elimina: scraping/lectura automatizada igual está prohibido en el
texto, aunque WhatsApp no publica qué tan agresivamente lo detecta
para este caso específico (cuenta personal, un solo grupo, sin enviar
nada).

**Consecuencias posibles si lo detectan:** advertencia, suspensión
temporal, o bloqueo permanente del número asociado a esa cuenta.

**Cómo reducir el riesgo (no lo elimina):**
- Si es posible, usa un número de WhatsApp secundario para esto, no tu
  número principal de trabajo/personal — así el número en riesgo no es
  el que usas todos los días.
- No corras esto con una frecuencia agresiva ni en paralelo con otras
  automatizaciones de WhatsApp sobre la misma cuenta.
- `headless: false` mientras validas (ya es el default en config) — un
  navegador real y visible, con pausas naturales, se parece más a un
  humano que una automatización 100% headless corriendo sin parar.

**Alternativa 100% compatible con los Términos de Servicio:** la
WhatsApp Business API oficial de Meta. No aplica bien a este caso
(está pensada para conversaciones iniciadas por un negocio hacia
clientes, con plantillas aprobadas y costo por conversación, no para
leer un grupo interno de supervisores) — se menciona aquí solo para
que quede claro que existe un camino oficial y por qué no es el que se
usó.

Fuentes consultadas: [Messaging Guidelines de WhatsApp](https://www.whatsapp.com/legal/messaging-guidelines), [WhatsApp API vs. Unofficial Tools — Risk/Reward Analysis](https://www.bot.space/blog/whatsapp-api-vs-unofficial-tools-a-complete-risk-reward-analysis-for-2025), [WhatsApp API and Automation 2026](https://zylos.ai/research/2026-01-26-whatsapp-api-automation), [TechCrunch — WhatsApp bloqueando clientes no oficiales](https://techcrunch.com/?p=1128480).

## Criterio de búsqueda (replica lo que hace Henry a mano)

Cuando un mensaje trae un número (sea código de incidencia, número de
elemento o número de aviso — no siempre se sabe cuál es a simple
vista), se busca en cascada:

1. **Código de incidencia** (corto o largo).
2. Si no aparece, **número de elemento** (sacado del texto libre de
   `Observaciones`, ej. "...apertura del elemento F3092..."). Ojo: de
   las 240 filas reales, solo 25 tienen un número de elemento
   explícito — el resto solo dice el TIPO ("fusible", "interruptor")
   sin número, así que este paso no siempre aplica.
3. Si tampoco, **número de aviso** (columna `NUMERO AVISO`, 137/240 filas la tienen).
4. Si ninguno de los tres aparece: se marca explícitamente **"no
   encontrada, pedir evidencia"** — ya no se pierde en un genérico
   "sin código".

Además, una vez identificada la fila, se valida que la evidencia se
haya enviado **dentro de la ventana horaria de esa incidencia**
(`Fecha Detección` → `Fecha SR` + un margen configurable,
`matching.margen_horas_evidencia`, 4 horas por defecto). Si cae fuera
de esa ventana, igual se guarda la foto (no se descarta evidencia) pero
queda marcada para revisión manual en vez de darse por buena sola.
Esto está en `src/validacion_temporal.py`, con tests en
`tests/test_validacion_temporal.py`.

**Pendiente de confirmar con datos reales (Fase 0):** el margen de 4
horas es un punto de partida razonable, no el número final — ajústalo
en `config.yaml` según lo que veas en la práctica.

## ⚠️ Antes de correr nada en serio: 1 cosa pendiente

1. **Formato real del código/elemento/aviso** que escriben en el chat
   (¿código corto `1168222`, largo `011682220001`, número de elemento,
   o varía?). Se deja un patrón candidato (6-8 dígitos), ajustable.

Por eso el proyecto viene dividido en dos pasos:

- **Fase 0 — Exploración** (`scripts/run_exploracion.py`): ya está
  completa y es segura de correr ahora mismo. Solo lee, no descarga,
  no modifica el Excel. Te da el reporte para confirmar el formato real
  con datos reales en vez de un supuesto.
- **Fases 1-2 — Descarga y cruce con Excel** (`scripts/run_automatizacion.py`):
  descarga/clasifica los adjuntos y actualiza el Excel. No hay Fase 3
  de notificación en el alcance actual (ver arriba).

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Para desarrollo (correr los tests):

```bash
pip install -r requirements-dev.txt
```

## Configuración

```bash
cp config/config.example.yaml config/config.yaml
```

Edita `config/config.yaml`:
- `whatsapp.grupos`: lista de grupos; basta con un fragmento del título (sin emojis). La clave antigua `nombre_grupo` sigue funcionando.
- `excel.ruta_archivo`: ruta a tu Excel real (`RESULTADO_CREACION_INCIDENCIAS.xlsx` o el que esté vigente).
- El resto puede quedar igual para la Fase 0.

`config/config.yaml` está en `.gitignore` a propósito — no se sube a ningún repositorio porque puede tener datos sensibles (números de teléfono, nombres).

## Paso 1: correr la exploración (hazlo primero, siempre)

```bash
python scripts/run_exploracion.py
```

La primera vez va a abrir una ventana de Chromium con el código QR de
WhatsApp Web — escanéalo con tu teléfono. Las siguientes veces entra
directo (la sesión queda guardada en `sesion_whatsapp/`, que tampoco
se sube a ningún repositorio).

Esto genera:
- Un log en `logs/automatizacion.log` con todo el detalle.
- Un reporte en `logs/reporte_exploracion_<fecha>.json` con:
  - la lista de participantes del grupo (nombre y, si no está guardado en tu agenda, el número),
  - los últimos mensajes con foto/video y qué código (si alguno) se detectó con el patrón actual.

Con ese reporte en mano, ajusta `matching.patron_codigo_regex` si el
formato real es distinto al que viene de ejemplo.

## Paso 2: descarga y cruce con Excel

```bash
python scripts/run_automatizacion.py
```

Descarga los adjuntos, los clasifica con la cascada código → elemento
→ aviso, valida la ventana horaria, y deja el Excel actualizado. No
envía nada a nadie — eso lo sigue haciendo Henry por correo con la
información que deja el Excel.

## Correr como tarea programada (cada hora)

**Linux/Mac (cron):**
```bash
crontab -e
# agrega esta línea (ajusta la ruta):
0 * * * * cd /ruta/a/whatsapp_incidencias && .venv/bin/python scripts/run_automatizacion.py >> logs/cron.log 2>&1
```

**Windows (Programador de tareas):**
Crear una tarea que ejecute cada hora:
```
C:\ruta\a\whatsapp_incidencias\.venv\Scripts\python.exe C:\ruta\a\whatsapp_incidencias\scripts\run_automatizacion.py
```

Nota: WhatsApp Web necesita que el teléfono vinculado tenga internet
(aunque sea de datos) para que la sesión no se caiga. Si usas
`headless: true` para que no abra ventana visible, pruébalo primero
en `headless: false` hasta confirmar que el flujo entero funciona.

## Tests

```bash
pytest
```

Los tests cubren toda la lógica que SÍ se puede probar sin un
navegador real: el matcher (los 3 casos de asociación código-foto) y
el manejo del Excel (categorización de evidencia, columnas nuevas,
que no se dañen las otras hojas del archivo). **La capa que habla con
WhatsApp Web (`whatsapp_session.py`, `whatsapp_reader.py`) no tiene
tests automáticos** porque depende del HTML real de una sesión viva;
esa parte se valida corriendo `run_exploracion.py` y revisando el log,
no con pytest. Si algún selector deja de funcionar (WhatsApp Web
cambia su interfaz de tanto en tanto), el log te va a decir en qué
paso exacto falló.

## Mantener las librerías al día

```bash
python scripts/check_dependencies.py
```

Te dice si hay versiones más nuevas de playwright/pandas/openpyxl
disponibles, sin actualizar nada solo. Las versiones están fijas
(pineadas) en `requirements.txt` a propósito — es mejor prueba
controlada que una sorpresa en una corrida automática a las 3am.
Para subir de versión: edita `requirements.txt` a mano, reinstala,
corre `pytest`, y solo después pruébalo contra el WhatsApp real.

## Estructura del proyecto

```
whatsapp_incidencias/
├── config/
│   └── config.example.yaml       # plantilla — copiar a config.yaml
├── src/
│   ├── config.py                 # carga y valida config.yaml
│   ├── logger.py                 # logging a archivo (rotación diaria) + consola
│   ├── modelos.py                # estructuras de datos (Mensaje, ResultadoMatch)
│   ├── matcher.py                # lógica pura: qué foto va con qué código (100% testeado)
│   ├── excel_manager.py          # lectura/escritura del Excel sin dañar otras hojas
│   ├── whatsapp_session.py       # login persistente de Playwright
│   ├── whatsapp_reader.py        # scraping de mensajes/participantes, descarga de adjuntos
│   ├── validacion_temporal.py    # valida que la evidencia caiga en la ventana horaria de la incidencia
│   ├── notificador.py            # FUERA DE ALCANCE -- idea a futuro, no se usa (Henry avisa por correo)
│   ├── exploracion.py            # Fase 0 (solo lectura)
│   └── main.py                   # orquestador Fases 1-2 (sin notificación)
├── scripts/
│   ├── run_exploracion.py
│   ├── run_automatizacion.py
│   └── check_dependencies.py
├── tests/
│   ├── test_matcher.py
│   ├── test_excel_manager.py
│   ├── test_validacion_temporal.py
│   └── test_config.py
├── data/Evidencias_WhatsApp/     # aquí se organizan las fotos descargadas
├── logs/                         # logs diarios + reportes de exploración
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## Qué falta para considerar esto "terminado"

- [ ] Correr Fase 0 contra el grupo real y revisar el reporte.
- [ ] Confirmar el formato del código/elemento/aviso y ajustar `matching.patron_codigo_regex` si hace falta.
- [ ] Ajustar `matching.margen_horas_evidencia` con casos reales (hoy 4h por defecto).
- [ ] Conectar `descargar_adjunto()` con el locator real de cada burbuja en `src/main.py` (hoy está preparado pero comentado, a la espera de ver el recorrido real de mensajes en Fase 0).
- [ ] Validar con 2-3 corridas manuales antes de dejarlo en tarea programada.

**No está en el alcance actual** (y no hace falta resolverlo para
terminar esto): notificaciones. Si en el futuro se decide automatizar
también el aviso cuando falta evidencia, sería por correo (el canal
que Henry ya usa), no por WhatsApp — `src/notificador.py` quedó
documentado como punto de partida para esa idea, pero no es parte de
este proyecto hoy.
