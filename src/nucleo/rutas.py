"""
Todas las rutas del proyecto en UN solo lugar (para encontrar y cambiar dónde va cada cosa).

    data/
      Incidencias/        INCIDENCIAS_BASE.xlsx (la base) · nuevas/ (aquí se ponen las nuevas) · procesadas/ · respaldo/ · original/
      indice/             indice.sqlite3 (mensajes leídos y estado de descarga) · respaldo/
      Evidencias_WhatsApp/<Grupo>/<día>/<Inc-…_Aviso-…>/   fotos y videos
      Reportes/           en_vivo/ (Excel que el bot reescribe solo) · historial/ (reportes con fecha) · analisis/
      Traspasos/          .zip para pasar el avance a otro PC
    logs/
      corridas/<AAAA-MM-DD>/<HHMMSS>_<modo>/   los logs de cada corrida (automatizacion_001.log, detalle_001.log, CSV)
      estado/             vigilante_estado.json (dónde quedó cada grupo)
      archivo/            lo viejo / pruebas
"""
from __future__ import annotations

from pathlib import Path


class Rutas:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.config = self.raiz / "config"
        self.data = self.raiz / "data"
        self.incidencias = self.data / "Incidencias"
        self.incidencias_base = self.incidencias / "INCIDENCIAS_BASE.xlsx"
        self.incidencias_nuevas = self.incidencias / "nuevas"
        self.indice_dir = self.data / "indice"
        self.indice_db = self.indice_dir / "indice.sqlite3"
        self.evidencias = self.data / "Evidencias_WhatsApp"
        self.reportes = self.data / "Reportes"
        self.reportes_en_vivo = self.reportes / "en_vivo"
        self.reportes_historial = self.reportes / "historial"
        self.reportes_analisis = self.reportes / "analisis"
        self.traspasos = self.data / "Traspasos"
        self.logs = self.raiz / "logs"
        self.logs_corridas = self.logs / "corridas"
        self.logs_estado = self.logs / "estado"
        self.logs_archivo = self.logs / "archivo"
        self.estado_vigilante = self.logs_estado / "vigilante_estado.json"

    def carpetas_de_trabajo(self) -> list[Path]:
        return [self.data, self.incidencias_nuevas, self.indice_dir, self.evidencias, self.reportes_en_vivo, self.logs_corridas, self.logs_estado]


RAIZ = Path(__file__).resolve().parents[2]   # src/nucleo/rutas.py -> raíz del proyecto
R = Rutas(RAIZ)
