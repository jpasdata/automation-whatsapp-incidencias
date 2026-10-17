"""
Carga y valida la configuración del proyecto desde config/config.yaml.

Por qué este módulo existe por separado: así ningún otro módulo lee
el YAML directamente ni asume que una clave existe. Si falta algo
importante, falla aquí, temprano y con un mensaje claro, en vez de
fallar a mitad de una corrida de 2 horas contra WhatsApp Web.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "config.example.yaml"


class ConfigError(Exception):
    """Error de configuración: falta un archivo o una clave requerida."""


@dataclass
class WhatsAppConfig:
    grupos: list[str]
    carpeta_sesion: str
    headless: bool
    cargar_desde: str = "mes_actual"  # "mes_actual", "AAAA-MM-DD" o "" (sin límite)


@dataclass
class ExcelConfig:
    ruta_archivo: str
    nombre_hoja: str
    columna_codigo_largo: str
    columna_codigo_corto: str
    columna_evidencia_manual: str
    columna_estado_automatico: str
    columna_ruta_foto: str
    columna_observaciones: str | None = None
    columna_numero_aviso: str | None = None
    columna_fecha_deteccion: str | None = None
    columna_fecha_sr: str | None = None
    columna_provincia: str | None = None


@dataclass
class MatchingConfig:
    patron_codigo_regex: str
    ventana_minutos_mensaje_separado: int
    margen_horas_evidencia: float = 4
    provincias_por_grupo: dict[str, list[str]] = field(default_factory=dict)  # fragmento del grupo -> provincias del Excel
    patron_elemento_regex: str | None = r"\bF[\s:\-#]?\d{3,6}\b"  # "F-15966", "F:08976"; "" lo desactiva


@dataclass
class NotificacionesConfig:
    activas: bool
    mapeo_nombre_telefono: dict[str, str] = field(default_factory=dict)
    plantilla_mensaje: str = ""


@dataclass
class RutasConfig:
    carpeta_evidencias: str
    carpeta_identificadas: str
    carpeta_sin_codigo: str


@dataclass
class LoggingConfig:
    carpeta_logs: str
    nivel: str


@dataclass
class AppConfig:
    whatsapp: WhatsAppConfig
    excel: ExcelConfig
    matching: MatchingConfig
    notificaciones: NotificacionesConfig
    rutas: RutasConfig
    logging: LoggingConfig


def resolver_cargar_desde(valor: str | None, hoy: datetime | None = None) -> datetime | None:
    """"mes_actual" -> día 1 del mes en curso; "AAAA-MM-DD" -> esa fecha; vacío -> None (sin límite)."""
    v = str(valor or "").strip().lower()
    if v in ("", "ninguno", "no", "false"):
        return None
    hoy = hoy or datetime.now()
    if v == "mes_actual":
        return datetime(hoy.year, hoy.month, 1)
    try:
        return datetime.fromisoformat(v)
    except ValueError as e:
        raise ConfigError(f"whatsapp.cargar_desde='{valor}' no es 'mes_actual' ni una fecha AAAA-MM-DD.") from e


def provincias_de_grupo(cfg: "AppConfig", grupo: str) -> set[str] | None:
    """Provincias del Excel (normalizadas) que atiende un grupo, o None si no está configurado (sin filtrar)."""
    from .modelos import normalizar_texto

    g = (normalizar_texto(grupo) or "")
    for fragmento, provincias in cfg.matching.provincias_por_grupo.items():
        f = normalizar_texto(fragmento) or ""
        if f and (f in g or g in f):
            return {normalizar_texto(p) for p in provincias if normalizar_texto(p)} or None
    return None


def _require(data: dict[str, Any], section: str) -> dict[str, Any]:
    if section not in data:
        raise ConfigError(
            f"Falta la sección '{section}' en config.yaml. "
            f"Compara con config/config.example.yaml."
        )
    return data[section]


def load_config(path: Path | str | None = None) -> AppConfig:
    """
    Carga config/config.yaml. Si no existe, lanza un error explicando
    que hay que copiarlo desde config.example.yaml (no lo creamos
    automáticamente para no pisar algo que el usuario ya personalizó).
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise ConfigError(
            f"No existe {config_path}.\n"
            f"Copia {EXAMPLE_CONFIG_PATH.name} a config/config.yaml y ajusta los valores:\n"
            f"  cp {EXAMPLE_CONFIG_PATH} {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ConfigError(f"{config_path} está vacío o mal formado.")

    wa = _require(raw, "whatsapp")
    ex = _require(raw, "excel")
    mt = _require(raw, "matching")
    no = _require(raw, "notificaciones")
    ru = _require(raw, "rutas")
    lo = _require(raw, "logging")

    # Acepta `grupos: [...]` (varios) o la clave antigua `nombre_grupo: "..."` (uno).
    grupos = wa.get("grupos") or ([wa["nombre_grupo"]] if wa.get("nombre_grupo") else [])
    if isinstance(grupos, str):
        grupos = [grupos]
    grupos = [str(g).strip() for g in grupos if str(g).strip()]
    if not grupos:
        raise ConfigError("whatsapp.grupos está vacío: pon al menos un nombre de grupo en config.yaml.")

    return AppConfig(
        whatsapp=WhatsAppConfig(
            grupos=grupos,
            carpeta_sesion=wa["carpeta_sesion"],
            headless=bool(wa.get("headless", False)),
            cargar_desde=str(wa.get("cargar_desde", "mes_actual") or ""),
        ),
        excel=ExcelConfig(
            ruta_archivo=ex["ruta_archivo"],
            nombre_hoja=ex["nombre_hoja"],
            columna_codigo_largo=ex["columna_codigo_largo"],
            columna_codigo_corto=ex["columna_codigo_corto"],
            columna_evidencia_manual=ex["columna_evidencia_manual"],
            columna_estado_automatico=ex["columna_estado_automatico"],
            columna_ruta_foto=ex["columna_ruta_foto"],
            columna_observaciones=ex.get("columna_observaciones") or None,
            columna_numero_aviso=ex.get("columna_numero_aviso") or None,
            columna_fecha_deteccion=ex.get("columna_fecha_deteccion") or None,
            columna_fecha_sr=ex.get("columna_fecha_sr") or None,
            columna_provincia=ex.get("columna_provincia") or None,
        ),
        matching=MatchingConfig(
            patron_codigo_regex=mt["patron_codigo_regex"],
            ventana_minutos_mensaje_separado=int(mt.get("ventana_minutos_mensaje_separado", 15)),
            margen_horas_evidencia=float(mt.get("margen_horas_evidencia", 4)),
            provincias_por_grupo={str(k): [str(p) for p in (v or [])] for k, v in (mt.get("provincias_por_grupo") or {}).items()},
            patron_elemento_regex=(mt["patron_elemento_regex"] or None) if "patron_elemento_regex" in mt else MatchingConfig.patron_elemento_regex,
        ),
        notificaciones=NotificacionesConfig(
            activas=bool(no.get("activas", False)),
            mapeo_nombre_telefono=no.get("mapeo_nombre_telefono", {}) or {},
            plantilla_mensaje=no.get("plantilla_mensaje", ""),
        ),
        rutas=RutasConfig(
            carpeta_evidencias=ru["carpeta_evidencias"],
            carpeta_identificadas=ru["carpeta_identificadas"],
            carpeta_sin_codigo=ru["carpeta_sin_codigo"],
        ),
        logging=LoggingConfig(
            carpeta_logs=lo["carpeta_logs"],
            nivel=lo.get("nivel", "INFO"),
        ),
    )


if __name__ == "__main__":
    # Chequeo manual rápido: python -m src.config
    try:
        cfg = load_config()
        print("Configuración cargada correctamente:")
        print(cfg)
    except ConfigError as e:
        print(f"ERROR DE CONFIGURACIÓN: {e}", file=sys.stderr)
        sys.exit(1)
