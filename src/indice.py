"""
Índice local (SQLite) de los mensajes leídos de WhatsApp Web.

Por qué existe: leer el chat es lo lento y lo riesgoso (scroll en un
navegador real); cruzar con el Excel no. Guardando lo leído se puede:
  - volver a cruzar y afinar reglas sin tocar WhatsApp,
  - leer solo lo nuevo en cada corrida (incremental),
  - ver cuánto histórico se ha cargado y cuántos mensajes/fotos hay por día,
  - llevar el estado de descarga de cada adjunto.
Solo texto y metadatos; las fotos van aparte, a carpetas.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .modelos import Mensaje

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensajes (
    grupo TEXT NOT NULL,
    id TEXT NOT NULL,
    ts TEXT NOT NULL,                -- ISO, hora de envío
    pos INTEGER NOT NULL DEFAULT 0,  -- orden dentro del lote leído (desempata mensajes del mismo minuto)
    remitente TEXT,
    texto TEXT,
    n_adjuntos INTEGER NOT NULL DEFAULT 0,
    tipo_adjunto TEXT,
    cita_autor TEXT,
    cita_texto TEXT,
    leido_en TEXT NOT NULL,
    estado_descarga TEXT,            -- NULL = no intentado | 'ok' | 'error'
    ruta_descarga TEXT,
    PRIMARY KEY (grupo, id)
);
CREATE INDEX IF NOT EXISTS ix_mensajes_ts ON mensajes (grupo, ts);
"""


@dataclass
class ResumenDia:
    dia: date
    mensajes: int
    con_adjunto: int
    fotos_videos: int


class Indice:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(self.ruta)
        self._con.executescript(ESQUEMA)

    def cerrar(self) -> None:
        self._con.close()

    def __enter__(self) -> "Indice":
        return self

    def __exit__(self, *a) -> None:
        self.cerrar()

    # --- escritura ------------------------------------------------------
    def guardar(self, grupo: str, mensajes: list[Mensaje]) -> int:
        """Inserta los mensajes nuevos (por id). No pisa los ya guardados ni su estado de descarga. Devuelve cuántos eran nuevos."""
        ahora = datetime.now().isoformat(timespec="seconds")
        antes = self.contar(grupo)
        self._con.executemany(
            "INSERT OR IGNORE INTO mensajes (grupo,id,ts,pos,remitente,texto,n_adjuntos,tipo_adjunto,cita_autor,cita_texto,leido_en)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (grupo, m.id_mensaje, m.timestamp.isoformat(timespec="minutes"), i, m.remitente, m.texto,
                 m.n_adjuntos, m.tipo_adjunto, m.cita_autor, m.cita_texto, ahora)
                for i, m in enumerate(mensajes) if m.id_mensaje
            ],
        )
        self._con.commit()
        return self.contar(grupo) - antes

    def marcar_descarga(self, grupo: str, id_mensaje: str, estado: str, ruta: str | None = None) -> None:
        self._con.execute(
            "UPDATE mensajes SET estado_descarga=?, ruta_descarga=? WHERE grupo=? AND id=?",
            (estado, ruta, grupo, id_mensaje),
        )
        self._con.commit()

    # --- lectura --------------------------------------------------------
    def contar(self, grupo: str) -> int:
        return self._con.execute("SELECT COUNT(*) FROM mensajes WHERE grupo=?", (grupo,)).fetchone()[0]

    def ids(self, grupo: str) -> set[str]:
        return {r[0] for r in self._con.execute("SELECT id FROM mensajes WHERE grupo=?", (grupo,))}

    def rango(self, grupo: str) -> tuple[datetime | None, datetime | None]:
        a, b = self._con.execute("SELECT MIN(ts), MAX(ts) FROM mensajes WHERE grupo=?", (grupo,)).fetchone()
        return (datetime.fromisoformat(a) if a else None, datetime.fromisoformat(b) if b else None)

    def cubre_desde(self, grupo: str, desde: datetime) -> bool:
        """True si el índice ya tiene mensajes de un día anterior a `desde` o del mismo día que `desde`."""
        primero, _ = self.rango(grupo)
        return primero is not None and primero.date() <= desde.date()

    def mensajes(self, grupo: str, desde: datetime | None = None) -> list[Mensaje]:
        sql = ("SELECT id,ts,remitente,texto,n_adjuntos,tipo_adjunto,cita_autor,cita_texto FROM mensajes WHERE grupo=?")
        args: list = [grupo]
        if desde:
            sql += " AND ts>=?"
            args.append(desde.isoformat(timespec="minutes"))
        sql += " ORDER BY ts, pos"
        return [
            Mensaje(
                remitente=r[2], timestamp=datetime.fromisoformat(r[1]), texto=r[3], tiene_adjunto=r[4] > 0,
                tipo_adjunto=r[5], id_mensaje=r[0], n_adjuntos=r[4], cita_autor=r[6], cita_texto=r[7],
            )
            for r in self._con.execute(sql, args)
        ]

    def estado_descarga(self, grupo: str) -> dict[str, tuple[str | None, str | None]]:
        return {r[0]: (r[1], r[2]) for r in self._con.execute(
            "SELECT id, estado_descarga, ruta_descarga FROM mensajes WHERE grupo=? AND n_adjuntos>0", (grupo,))}

    def resumen_por_dia(self, grupo: str) -> list[ResumenDia]:
        filas = self._con.execute(
            "SELECT substr(ts,1,10), COUNT(*), SUM(n_adjuntos>0), SUM(n_adjuntos) FROM mensajes WHERE grupo=? GROUP BY 1 ORDER BY 1",
            (grupo,),
        )
        return [ResumenDia(date.fromisoformat(d), n, a or 0, f or 0) for d, n, a, f in filas]

    def grupos(self) -> list[str]:
        return [r[0] for r in self._con.execute("SELECT DISTINCT grupo FROM mensajes ORDER BY 1")]

    # --- traspaso entre PCs ----------------------------------------------------------------------
    def rebasar_rutas(self, raiz_evidencias: str | Path) -> int:
        """
        Las rutas de descarga se guardan completas, así que al mover el índice a otro PC apuntan a una carpeta que no existe.
        Esto las reapunta a `raiz_evidencias` conservando lo que hay desde 'Evidencias_WhatsApp' hacia adentro.
        Devuelve cuántos mensajes se corrigieron.
        """
        from pathlib import PureWindowsPath

        raiz = Path(raiz_evidencias)
        corregidos = 0
        for grupo, id_, ruta in self._con.execute("SELECT grupo, id, ruta_descarga FROM mensajes WHERE ruta_descarga IS NOT NULL AND ruta_descarga<>''").fetchall():
            nuevas = []
            for r in ruta.split(";"):
                partes = PureWindowsPath(r).parts
                if "Evidencias_WhatsApp" in partes:
                    r = str(raiz.joinpath(*partes[partes.index("Evidencias_WhatsApp") + 1:]))
                nuevas.append(r)
            if ";".join(nuevas) != ruta:
                self._con.execute("UPDATE mensajes SET ruta_descarga=? WHERE grupo=? AND id=?", (";".join(nuevas), grupo, id_))
                corregidos += 1
        self._con.commit()
        return corregidos

    def fusionar(self, ruta_otro: str | Path) -> dict[str, int]:
        """
        Mezcla otro índice (el de otro PC) en este: agrega los mensajes que no estaban y, si aquí un mensaje no tiene estado de
        descarga y allá sí, toma el de allá. Lo que ya está aquí NO se pisa.
        """
        self._con.execute("ATTACH DATABASE ? AS otro", (str(ruta_otro),))
        try:
            antes = self._con.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0]
            self._con.execute(
                "INSERT OR IGNORE INTO mensajes (grupo,id,ts,pos,remitente,texto,n_adjuntos,tipo_adjunto,cita_autor,cita_texto,leido_en,estado_descarga,ruta_descarga)"
                " SELECT grupo,id,ts,pos,remitente,texto,n_adjuntos,tipo_adjunto,cita_autor,cita_texto,leido_en,estado_descarga,ruta_descarga FROM otro.mensajes")
            nuevos = self._con.execute("SELECT COUNT(*) FROM mensajes").fetchone()[0] - antes
            cur = self._con.execute(
                "UPDATE mensajes SET estado_descarga=(SELECT o.estado_descarga FROM otro.mensajes o WHERE o.grupo=mensajes.grupo AND o.id=mensajes.id),"
                " ruta_descarga=(SELECT o.ruta_descarga FROM otro.mensajes o WHERE o.grupo=mensajes.grupo AND o.id=mensajes.id)"
                " WHERE estado_descarga IS NULL AND EXISTS (SELECT 1 FROM otro.mensajes o WHERE o.grupo=mensajes.grupo AND o.id=mensajes.id AND o.estado_descarga IS NOT NULL)")
            estados = cur.rowcount
            self._con.commit()
        finally:
            self._con.execute("DETACH DATABASE otro")
        return {"mensajes_nuevos": nuevos, "estados_de_descarga_tomados": estados}
