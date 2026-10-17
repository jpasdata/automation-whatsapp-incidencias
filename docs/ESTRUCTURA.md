# Estructura del proyecto

```
whatsapp_incidencias/
├── Iniciar_interfaz.bat · Crear_config.bat      accesos directos (Windows)
├── config/            config.example.yaml (plantilla) · config.yaml (real, no se sube a git)
├── data/
│   ├── RESULTADO_CREACION_INCIDENCIAS.xlsx      Excel de incidencias (entrada; nunca se modifica)
│   ├── indice/        indice.sqlite3 (mensajes leídos + estado de descarga) · respaldo/
│   ├── Evidencias_WhatsApp/   <Grupo>/<día>/<Inc-…_Aviso-…_fNN | _otras_incidencias/… | _sin_numero>/ + manifiesto_<día>.csv
│   └── Reportes/      Cruce_en_vivo.xlsx · RESULTADO_…_CRUZADO.xlsx (en vivo) · analisis/ · pruebas/
├── logs/              automatizacion.log · detalle.log · descargas_detalle.csv · eventos_bot.csv · archivo/ (pruebas)
├── scripts/           puntos de entrada (ver README) · diagnostico/ (pruebas en vivo repetibles)
├── src/               lógica (ver abajo)
├── tests/             pruebas automáticas (pytest)
├── sesion_whatsapp/   perfil de Chromium con el login de WhatsApp (no se sube a git)
└── docs/              esta documentación
```

## Módulos (`src/`)

| Módulo | Responsabilidad |
|---|---|
| `whatsapp_session.py` | Abre Chromium con sesión persistente, abre un chat por título, cierra avisos |
| `whatsapp_reader.py` | Lee mensajes del DOM, sube por el chat (`cargar_hacia_arriba`), `cosechar`, **descarga de fotos/álbumes/videos desde el visor** |
| `rueda.py` | Scroll «humano» con la rueda real del mouse (necesaria para que Web pida mensajes antiguos) |
| `indice.py` / `historico.py` | Índice SQLite local; carga del histórico en fases, con verificador |
| `matcher.py` | Asocia cada foto con su número: leyenda → respuesta citando → texto cercano (antes/después) → ráfaga |
| `excel_manager.py` | Lee el Excel (hoja principal + hojas adicionales), busca por código → elemento → aviso, filtra por provincia |
| `cruce.py` / `validacion_temporal.py` | Cruce con el Excel y ventana horaria (Fecha Detección → Fecha SR + 4 h) |
| `descargas.py` | Plan de descargas, carpetas con aviso/incidencia, recorrido y descarga, CSV de detalle |
| `vigilante.py` | Bot de todo el día: lee, cruza (48 h), baja, **reubica lo identificado tarde**, manifiestos |
| `excel_vivo.py` / `reporte_excel.py` | Excel en tiempo real y reporte con formato |
| `comportamiento.py` | Estadísticas de cómo reportan las personas en un grupo |
| `verificador.py` | Revisión previa del entorno con «qué hacer» |
| `logger.py` / `eventos.py` | Logs detallados y registros CSV |
| `bloqueo.py` | Candado para que dos procesos no usen la misma sesión |

## Flujo de datos

```
WhatsApp Web --leer--> indice.sqlite3 --cruzar (matcher + Excel)--> plan de descargas --descargar--> Evidencias_WhatsApp/
                                   |                                        |
                                   +--> Excel en vivo (Estado_Automatico, Ruta_Evidencia) <--+
```
