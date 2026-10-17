@echo off
REM Carga incidencias nuevas SIN buscar carpetas: arrastra uno o varios Excel (.xlsx) sobre este archivo y suéltalos.
REM (también sirve doble clic: te deja elegir el archivo en una ventana).
cd /d "%~dp0"
setlocal
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
if "%~1"=="" (
  for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'Excel (*.xlsx)|*.xlsx'; $d.Multiselect = $true; $d.Title = 'Elige el Excel con las incidencias nuevas'; if ($d.ShowDialog() -eq 'OK') { $d.FileNames -join '|' }"`) do set "ELEGIDOS=%%F"
  if not defined ELEGIDOS (
    echo No elegiste ningun archivo.
    pause
    exit /b
  )
  powershell -NoProfile -Command "& '%PY%' scripts\incidencias.py cargar ('%ELEGIDOS%' -split '\|')"
) else (
  "%PY%" scripts\incidencias.py cargar %*
)
echo.
pause
