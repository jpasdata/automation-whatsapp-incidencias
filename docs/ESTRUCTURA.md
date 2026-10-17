# Estructura del proyecto

Todo está organizado por tema para encontrar rápido dónde está cada cosa. Las rutas de carpetas están en UN solo lugar: `src/nucleo/rutas.py`.

```
whatsapp_incidencias/
├── Iniciar_interfaz.bat · Crear_config.bat · Actualizar_proyecto.bat     accesos directos (Windows)
├── config/                  config.example.yaml (plantilla) · config.yaml (real, no se sube a git)
├── src/                     el código, por tema (ver abajo)
├── scripts/                 puntos de entrada (ver README) · diagnostico/ (pruebas en vivo repetibles)
├── tests/                   pruebas automáticas (pytest)
├── docs/                    esta documentación
├── data/
│   ├── Incidencias/         INCIDENCIAS_BASE.xlsx (la base, UNA hoja) · nuevas/ (aquí pones las nuevas) · procesadas/ · respaldo/ · original/
│   ├── indice/              indice.sqlite3 (mensajes leídos + estado de descarga) · respaldo/
│   ├── Evidencias_WhatsApp/ <Grupo>/<día>/<Inc-…_Aviso-… | _otras_incidencias/… | _sin_numero>/  + manifiesto_<día>.csv
│   ├── Reportes/            en_vivo/ (Excel que el bot reescribe solo) · historial/ (reportes con fecha) · analisis/
│   └── Traspasos/           .zip para pasar el avance a otro PC
├── logs/
│   ├── corridas/<AAAA-MM-DD>/<HHMMSS>_<modo>/    logs de CADA corrida: automatizacion_001.log, detalle_001.log (se parten por tamaño),
│   │                                             descargas_detalle.csv, descargas_pendientes.csv, eventos.csv
│   ├── estado/              vigilante_estado.json (dónde quedó cada grupo)
│   ├── archivo/             lo viejo y las pruebas (índice en LEEME.txt)
│   └── ultima_corrida.txt   ruta de la corrida más reciente
└── sesion_whatsapp/         perfil de Chromium con el login de WhatsApp (no se sube a git)
```

## Código (`src/`)

| Subpaquete | Módulo | Responsabilidad |
|---|---|---|
| **nucleo/** (base compartida) | `rutas.py` | Todas las rutas del proyecto |
| | `config.py` · `modelos.py` | Configuración (config.yaml) y modelos de datos (`Mensaje`, `ResultadoMatch`…) |
| | `logger.py` · `eventos.py` | Logs por corrida (partidos por tamaño) y registros CSV |
| | `bloqueo.py` · `verificador.py` | Candado de sesión y revisión previa del entorno con «qué hacer» |
| **whatsapp/** (todo lo de WhatsApp Web) | `session.py` | Chromium con sesión persistente, abrir chat, cerrar avisos |
| | `reader.py` | Leer mensajes del DOM, subir por el chat, **descargar fotos/álbumes/videos del visor** |
| | `rueda.py` · `grabacion.py` | Scroll «humano» con la rueda real del mouse; grabación de eventos |
| **cruce/** (asociar fotos con números) | `matcher.py` | Leyenda → respuesta citando → texto cercano → ráfaga → comentario de otra persona |
| | `cruce.py` · `busqueda.py` | Cruce con el Excel (ventana por grupo, pares aprendidos) |
| | `aprendizaje.py` · `validacion_temporal.py` · `comportamiento.py` | Pares aviso↔incidencia, ventana horaria, estadísticas de cómo reporta la gente |
| **excel/** | `manager.py` | Lee la base (una hoja), filtra por responsable y provincia, busca por código → elemento → aviso |
| | `unificar.py` · `incidencias.py` | Unificar el Excel original en una hoja; **incorporar las incidencias nuevas** a la base |
| | `reporte.py` · `en_vivo.py` | Reporte con formato y Excel en tiempo real |
| **datos/** | `indice.py` · `historico.py` | Índice SQLite local y carga del histórico |
| | `traspaso.py` · `estado_descargas.py` · `cobertura.py` | Pasar el avance a otro PC; qué se bajó y qué no; cobertura |
| **bot/** (los procesos que corren) | `vigilante.py` | Bot de todo el día: lee, cruza, baja, reubica lo identificado tarde, reanuda donde quedó |
| | `descargas.py` | Plan de descargas, carpetas con aviso/incidencia, recorrido y descarga |
| | `main.py` · `exploracion.py` · `notificador.py` | Flujos antiguos de exploración y notificación |

## Flujo de datos

```
data/Incidencias/nuevas/  ──incorporar──►  INCIDENCIAS_BASE.xlsx ──┐
                                                                   ├─ cruce ─► plan ─► descargar ─► Evidencias_WhatsApp/
WhatsApp Web ──leer──► indice.sqlite3 ─────────────────────────────┘                      │
                                   │                                                       └─► Excel en vivo (Estado_Automatico, Ruta_Evidencia)
                                   └─► logs/corridas/<fecha>/<hora>_<modo>/
```
