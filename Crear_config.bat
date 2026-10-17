@echo off
REM Crea config\config.yaml a partir de config\config.example.yaml con el grupo de WhatsApp ya puesto.
REM Uso: doble clic, o  Crear_config.bat "parte del titulo del grupo"
REM Si config\config.yaml ya existe NO lo pisa.
cd /d "%~dp0"
set "GRUPO=%~1"
if "%GRUPO%"=="" set "GRUPO=CFFM_Veraguas_Sea_Central-Reporte de videos"
if exist "config\config.yaml" (
  echo config\config.yaml ya existe; no se modifica. Borralo si quieres regenerarlo.
  goto fin
)
if not exist "config\config.example.yaml" (
  echo ERROR: falta config\config.example.yaml. Ejecuta este archivo desde la carpeta del proyecto.
  goto fin
)
powershell -NoProfile -Command "$t=[IO.File]::ReadAllText(\"config\config.example.yaml\",[Text.Encoding]::UTF8).Replace(\"NOMBRE_EXACTO_DEL_GRUPO\",$env:GRUPO); [IO.File]::WriteAllText(\"config\config.yaml\",$t,(New-Object Text.UTF8Encoding $false))"
if exist "config\config.yaml" (echo Listo: config\config.yaml creado para el grupo "%GRUPO%".) else (echo ERROR: no se pudo crear config\config.yaml)
:fin
echo.
echo Siguiente: copia el Excel a data\RESULTADO_CREACION_INCIDENCIAS.xlsx y ejecuta  python scripts\verificar_entorno.py
pause
