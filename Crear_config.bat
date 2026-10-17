@echo off
REM Crea config\config.yaml a partir de config\config.example.yaml (con los 4 grupos ya puestos).
REM Si config\config.yaml ya existe NO lo pisa: borralo si quieres regenerarlo.
cd /d "%~dp0"
if exist "config\config.yaml" (
  echo config\config.yaml ya existe; no se modifica. Borralo si quieres regenerarlo.
  goto fin
)
if not exist "config\config.example.yaml" (
  echo ERROR: falta config\config.example.yaml. Ejecuta este archivo desde la carpeta del proyecto.
  goto fin
)
copy /Y "config\config.example.yaml" "config\config.yaml" >nul
if exist "config\config.yaml" (echo Listo: config\config.yaml creado con los 4 grupos: Veraguas, Oeste, Cocle y Azuero.) else (echo ERROR: no se pudo crear config\config.yaml)
:fin
echo.
echo Siguiente: copia el Excel a data\RESULTADO_CREACION_INCIDENCIAS.xlsx y ejecuta  python scripts\verificar_entorno.py
pause
