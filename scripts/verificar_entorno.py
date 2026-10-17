#!/usr/bin/env python3
"""
Verifica que todo esté listo para correr (Python, librerías, Chromium, internet, config, Excel, sesión...)
y dice qué hacer si algo falla. Código de salida 1 si hay errores.

Uso:  python scripts/verificar_entorno.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.verificador import hay_errores, informe, verificar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
resultados = verificar()
print(informe(resultados))
sys.exit(1 if hay_errores(resultados) else 0)
