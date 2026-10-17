@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\interfaz.py
) else (
  python scripts\interfaz.py
)
