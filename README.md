# Evidencias WhatsApp → Incidencias (Henry)

Bot que lee los grupos de WhatsApp Web donde se reportan incidencias (Veraguas, Oeste, Coclé, Azuero), **descarga las
fotos y videos** (organizados por día y por aviso/incidencia), **los cruza contra el Excel** de incidencias asignadas y
**mantiene un Excel actualizado en tiempo real** con el estado de cada incidencia. Nunca envía mensajes por WhatsApp.

## Inicio rápido

1. Instalar Python 3.10+ y las dependencias: `pip install -r requirements.txt` y `python -m playwright install chromium`
2. `Crear_config.bat` (crea `config/config.yaml` con los 4 grupos) y poner la base de incidencias en `data/Incidencias/INCIDENCIAS_BASE.xlsx` (o importar un traspaso)
3. `python scripts/verificar_entorno.py` — revisa todo y dice **qué hacer** si algo falla (también corre solo antes de iniciar)
4. `Iniciar_interfaz.bat` — interfaz con botón INICIAR/DETENER, modos, grupo, tiempo («hoy y N días antes») y panel en vivo
5. La primera vez se abre WhatsApp Web: escanear el QR y **no cerrar la ventana** hasta ver los chats

## Qué hace cada modo

| Modo | Comando | Cuándo usarlo |
|---|---|---|
| **Vigilante** (todo el día) | `python scripts/vigilante.py --todos` | Lo normal: sesión siempre abierta, baja todo lo que llega, reubica fotos identificadas horas después. **Si se detiene y se vuelve a activar, reanuda donde quedó** (índice + `logs/vigilante_estado.json`); si llegaron más mensajes de los que caben en pantalla mientras estuvo apagado, sube unos minutos con el mouse para cerrar el hueco (`--sin-mouse` lo evita). |
| Histórico | `python scripts/cargar_historico.py --todos --desde 2026-10-01 --descargar` | Una vez, para traer lo anterior. **Usa el mouse real** (no tocarlo). |
| Solo actualizar lo nuevo | `python scripts/actualizar.py` | Lectura rápida de lo último, sin descargar. |
| Reorganizar lo ya bajado | `python scripts/reorganizar_descargas.py` | Tras cambiar el Excel o las reglas; no abre WhatsApp. |
| Reporte Excel | `python scripts/generar_reporte.py --desde 2026-10-01 --todos` | Genera un reporte a demanda (el bot ya lo hace solo). |
| Estado de descargas | `python scripts/estado_descargas.py` | Qué se bajó, qué falló y por qué. |
| Pasar el avance a otro PC | botones «Exportar/Importar traspaso» de la interfaz, o `python scripts/traspaso.py exportar` y `python scripts/traspaso.py importar Traspaso_xxx.zip` | Crea un `.zip` con índice + evidencias + estado; al importar **mezcla** (no pisa), reapunta las rutas al PC nuevo y respalda lo que había. Se puede ir y volver. **No correr el bot en los dos PCs a la vez.** La sesión de WhatsApp no se traspasa: en el otro PC se escanea el QR. |
| Limpiar y ordenar | botón en la interfaz, o `python scripts/limpiar.py --simular` / `python scripts/limpiar.py --reorganizar` | Archiva logs de prueba, quita cachés y carpetas vacías, respalda el índice. **Nunca borra evidencias, índice, sesión ni Excel.** |
| Actualizar este PC | `Actualizar_proyecto.bat` (o botón «Actualizar desde GitHub») | Baja la versión nueva, quita residuos del proceso anterior, regenera `config.yaml` (deja `config.yaml.respaldo`) y verifica. No toca `data/` ni la sesión. |
| Comportamiento del grupo | `python scripts/analizar_comportamiento.py` | Estadísticas de cómo reporta la gente (guía las ventanas de espera). |

## Base de incidencias (`data/Incidencias/`)

- **`INCIDENCIAS_BASE.xlsx`**: una sola hoja, una fila por incidencia, con todo lo del Excel original (7 hojas) y el historial de reasignaciones.
- **Incidencias nuevas**: deja el Excel (el formato de asignación de siempre) en **`data/Incidencias/nuevas/`**. El vigilante lo detecta y lo
  incorpora solo; también con el botón «Incorporar incidencias nuevas» o `python scripts/incidencias.py incorporar`. La incidencia nueva se agrega;
  si ya existía, manda la última asignación y las anteriores quedan en «Historial de asignaciones». Soltar el mismo archivo dos veces no duplica nada.
  El archivo pasa a `procesadas/` y antes de cada cambio se guarda una copia en `respaldo/`.
- Crear la base desde el Excel original de varias hojas (una sola vez): `python scripts/incidencias.py crear`. El original queda intacto en `original/`.

## Resultados

- **Excel en tiempo real** (se reescribe solo con cada novedad): `data/Reportes/en_vivo/`
  - `RESULTADO_CREACION_INCIDENCIAS_CRUZADO.xlsx` — copia de tu Excel con `Estado_Automatico` y `Ruta_Evidencia` en cada fila (verde/ámbar/rojo)
  - `Cruce_en_vivo.xlsx` — resumen, por incidencia, por día, descargas, sin cruce
  - El Excel original **nunca se modifica**. Si lo tienes abierto, el archivo queda bloqueado y se reintenta en la siguiente actualización.
- **Evidencias**: `data/Evidencias_WhatsApp/<Grupo>/<día>/`
  - `Inc-1168222_Aviso-5620125_f230/` — cruza con el Excel (`f` = fila del Excel)
  - `_otras_incidencias/Aviso-5633273/` — el chat trae un número que no está en el Excel
  - `_sin_numero/` — aún sin número (se espera el comentario; si llega horas después, el bot mueve los archivos)
  - `manifiesto_<día>.csv` — cada archivo con su remitente, leyenda, número que lo identificó y cómo
- **Logs organizados por corrida** (`logs/corridas/<fecha>/<hora>_<modo>/`): `automatizacion_001.log` (lo importante), `detalle_001.log` (todo, con función y
  línea; sirve para ubicar fallas), `descargas_detalle.csv` (un registro por descarga, con el motivo si falló), `eventos.csv` (hitos). Los logs se parten por
  tamaño (`_002`, `_003`…) en vez de crecer sin fin. El botón «Abrir logs» va a la última corrida; `logs/estado/` guarda dónde quedó el vigilante;
  lo viejo y las pruebas están en `logs/archivo/`.

## Más documentación (`docs/`)

- [docs/ESTRUCTURA.md](docs/ESTRUCTURA.md) — mapa de carpetas y módulos, flujo de datos
- [docs/HALLAZGOS.md](docs/HALLAZGOS.md) — lo aprendido de WhatsApp Web, de los grupos y del Excel (límites reales)
- [docs/PRUEBAS.md](docs/PRUEBAS.md) — pruebas en vivo realizadas y cómo repetirlas (`scripts/diagnostico/`)
- `docs/contexto/` — requerimiento original de Henry · `docs/README_anterior.md` — README previo (fases de diseño)

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


## Tests

`python -m pytest -q` (≈140 pruebas; las de lectura tardan unos minutos por esperas simuladas).
