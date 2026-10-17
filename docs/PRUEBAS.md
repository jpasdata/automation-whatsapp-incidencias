# Pruebas realizadas y cómo repetirlas

## Automáticas
`python -m pytest -q` — ≈140 pruebas (lectura del DOM con HTML simulado, cruce, Excel, índice, descargas, vigilante, verificador).

## En vivo (`scripts/diagnostico/`, abren WhatsApp Web; usar con la sesión ya iniciada y sin otro proceso activo)
Uso: `python scripts/diagnostico/<script>.py <ruta_del_proyecto>`

| Script | Qué comprobó |
|---|---|
| `abrir_login.py` | Abre WhatsApp Web para iniciar sesión / escanear el QR y la guarda |
| `ver_pantalla.py` | Estado de la pantalla de WhatsApp (QR, lista de chats) con captura |
| `spinner.py` | Cuándo aparece el círculo de carga al subir (solo al bajar y volver a subir con la rueda) |
| `probe_descarga.py` | Abre una foto en el visor y la extrae completa (864×1152, ~2 s) |
| `probe_video_album.py` · `probe_album_ultima.py` | Descarga de un álbum (12 fotos) y que funcione abriéndolo desde la última foto |
| `probe_borroso.py` | Por qué salían fotos borrosas (`media-state-pending`) y cómo esperar al original |
| `probe_v2.py` · `probe_solo_video.py` | El video es un flujo por rangos (no blob); descarga completa como `.mp4` |
| `probe_repinta.py` · `probe_repinta2.py` | Que al bajar Web vuelve a pintar mensajes viejos (cobertura ≈90 %) |

Salidas de las pruebas (capturas, JSON, textos): `logs/archivo/` (índice en `logs/archivo/LEEME.txt`).

## Corridas largas hechas
- Histórico de Veraguas hasta el 1/10 (1.509 mensajes) y de Oeste/Coclé/Azuero hasta el 9/10 (límite del celular).
- Vigilante en los 4 grupos: primera vuelta ≈ 27 min (bajó lo de las últimas 48 h); vueltas siguientes de 3–9 min por grupo.
- Reorganización de 168 archivos ya descargados a las carpetas con aviso/incidencia (`scripts/reorganizar_descargas.py`).
