@echo off
REM Deja este PC con la version mas nueva del proyecto (sin tocar tus datos): cierra procesos viejos, baja GitHub,
REM quita residuos del proceso anterior, regenera la configuracion (guarda copia de la tuya) y verifica todo.
REM NO toca: data\ (Excel, indice, evidencias), sesion_whatsapp\ (login), logs\.
cd /d "%~dp0"
echo.
echo [1/6] Cerrando procesos viejos del bot (python del proyecto y el navegador de la sesion)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*scripts*') -or ($_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*sesion_whatsapp*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
if exist sesion_whatsapp.lock del /q sesion_whatsapp.lock
echo [2/6] Bajando la version nueva de GitHub...
git fetch origin || goto error
git reset --hard origin/main || goto error
git clean -fd -e data -e logs -e sesion_whatsapp -e config -e .venv >nul
echo [3/6] Quitando residuos del proceso anterior (caches y carpetas viejas)...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
if exist .pytest_cache rd /s /q .pytest_cache
if exist context rd /s /q context
echo [4/6] Configuracion nueva (la anterior queda como config\config.yaml.respaldo)...
if exist config\config.yaml copy /Y config\config.yaml config\config.yaml.respaldo >nul
copy /Y config\config.example.yaml config\config.yaml >nul
echo [5/6] Instalando librerias...
python -m pip install -r requirements.txt -q
python -m playwright install chromium
echo [6/6] Verificando...
python scripts\verificar_entorno.py
echo.
echo Listo. Si tienes datos de antes, ordenalos con la interfaz: boton "Limpiar y ordenar" (marca "reorganizar lo descargado").
pause
goto fin
:error
echo.
echo ERROR al bajar de GitHub: revisa internet o que git este instalado.
pause
:fin
