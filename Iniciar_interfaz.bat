@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe scripts\interfaz.py || python scripts\interfaz.py
