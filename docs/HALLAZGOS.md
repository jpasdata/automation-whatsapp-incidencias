# Hallazgos (lo que se descubrió probando en vivo)

## WhatsApp Web
- **Solo se mantienen pintados ~100 mensajes.** Lo demás se recorta; por eso se indexa por tandas mientras se sube.
- **Cada sesión nueva vuelve al final del chat** y hay que volver a subir (~20 min por lo ya conocido).
- **Los mensajes antiguos solo se piden con la rueda REAL del mouse** (bajar unas pantallas y volver a subir hasta el tope; el círculo
  de carga solo aparece así). La rueda sintética de Playwright casi nunca lo dispara.
- **El celular deja de entregar histórico** a cierta antigüedad: Oeste, Coclé y Azuero llegaron solo hasta el 9/10 aun con 100 min de intentos.
- Al **bajar de arriba abajo** Web vuelve a pintar lo viejo (≈90 % con pasos de 0,4 pantalla), por eso se descarga con un barrido.
- **Fotos**: se abren en el visor y se toma el original (`media-zoomable` listo). Mientras carga (`media-state-pending`) solo hay una
  miniatura borrosa: se espera y, si no carga en 20 s, se omite en vez de guardar una foto borrosa.
- **Álbumes**: el chat muestra 4 miniaturas pero pueden ser muchas más (se vio uno de 12); se recorren con «Siguiente» hasta que cambia el
  encabezado. El visor puede abrir en cualquier foto: se retrocede primero al inicio.
- **Cuántas fotos trae un álbum**: el número de miniaturas del chat (`n_adjuntos`) puede ser mayor que las fotos reales (se vio «4» en álbumes de 2). Se da por completo un álbum cuando el visor llega a otro mensaje; «parcial» solo si una foto de verdad falló.
- **Videos**: no son blobs sino un flujo `/stream/video` que responde por partes (206): se piden rangos sucesivos hasta completar. El visor no
  tiene botón «Descargar» para video. Resultado: `.mp4` válido (probado con 5,8 MB).
- **Rutas de Windows de 260 caracteres o más** hacen fallar mover/guardar: carpeta del grupo corta y nombres de archivo acotados (`MAX_RUTA`).

## Cómo reporta la gente (Veraguas, 1/10–16/10: 1.474 mensajes, 29 remitentes)
- El **número de aviso** (7 dígitos que empiezan en 56) es lo que más se usa (731 leyendas); la incidencia corta (11xxxxx) y el elemento (F…) mucho menos.
- 76 % de los adjuntos traen leyenda; el 86 % de los reportes tiene su número en el propio mensaje.
- Cuando el número va en un texto aparte: mismo remitente, mediana 2–3 min y hasta ~40 min; otra persona, hasta 90–135 min.
- Las **respuestas citando la foto** casi siempre las hace quien la subió: mediana 23 min, P90 73 min, **hasta 4,5 h**.
- Sin ventana de espera, 11 % de los reportes quedan sin número; esperando 24 h baja a 5 %. Por eso el vigilante espera 6 h antes de dar una foto por huérfana
  y sigue cruzando 48 h hacia atrás. (Reproducir: `python scripts/analizar_comportamiento.py`.)

## Excel
- El Excel trae **más hojas** con incidencias del mismo responsable (`OCTUBRE`, `c ya entregados sin correo`): se leen como hojas adicionales (335 en total).
- **`NUMERO AVISO` está vacío en la mayoría de filas** (Coclé 5/24, Oeste 62/145, Veraguas 24/73) y el chat identifica por aviso: es el principal
  límite del cruce. Solución pendiente: completar esa columna o un cruce aproximado por provincia/hora/descripción.
- Hay filas con provincia «SIN DATOS» (no se pueden asignar a un grupo) y «PANAMÁ OESTE» escrito con y sin tilde.
