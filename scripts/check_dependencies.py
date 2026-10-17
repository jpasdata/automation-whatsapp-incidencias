#!/usr/bin/env python3
"""
Revisa si las librerías pineadas en requirements.txt tienen versiones
más nuevas disponibles en PyPI, sin actualizar nada automáticamente
(actualizar playwright/pandas a ciegas puede romper selectores o
compatibilidad del Excel).

Uso:
    python scripts/check_dependencies.py
"""
import subprocess
import sys


def main() -> None:
    print("Comparando versiones instaladas vs. la última disponible en PyPI...\n")
    resultado = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--outdated", "--format=columns"],
        capture_output=True,
        text=True,
        check=False,
    )
    salida = resultado.stdout.strip()
    if not salida or salida.count("\n") <= 1:
        print("Todo está en la última versión disponible (o no hay conexión a PyPI).")
        return

    print(salida)
    print(
        "\nSi quieres subir alguna versión, edita requirements.txt a mano "
        "(no lo hagas automático) y vuelve a correr:\n"
        "  pip install -r requirements.txt\n"
        "  pytest\n"
        "antes de usarlo contra el WhatsApp real."
    )


if __name__ == "__main__":
    main()
