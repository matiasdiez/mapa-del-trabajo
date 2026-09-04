"""Configuración global del pipeline — lee variables de entorno."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Busca .env desde el directorio del proyecto (mapa/)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ── Neon (PostgreSQL serverless) ──────────────────────────────────────────────
# Formato: postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
# Obtener desde Neon dashboard → proyecto → Connection string

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")


# ── DuckDB (base analítica local) ─────────────────────────────────────────────

_duckdb_raw = os.environ.get("DUCKDB_PATH", "data/analytics.db")
DUCKDB_PATH: Path = (
    Path(_duckdb_raw) if Path(_duckdb_raw).is_absolute() else _PROJECT_ROOT / _duckdb_raw
)


# ── Cloudflare R2 ─────────────────────────────────────────────────────────────

R2_ACCOUNT_ID: str = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID: str = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY: str = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME: str = os.environ.get("R2_BUCKET_NAME", "mapa-industrial-tiles")
R2_PUBLIC_URL: str = os.environ.get("R2_PUBLIC_URL", "")


# ── Georef AR ─────────────────────────────────────────────────────────────────

GEOREF_API_BASE: str = os.environ.get(
    "GEOREF_API_BASE", "https://apis.datos.gob.ar/georef/api"
)


# ── Rutas de datos ────────────────────────────────────────────────────────────

DATA_INCOMING_DIR: Path = Path(
    os.environ.get("DATA_INCOMING_DIR", str(_PROJECT_ROOT / "data" / "incoming"))
)
DATA_PROCESSED_DIR: Path = Path(
    os.environ.get("DATA_PROCESSED_DIR", str(_PROJECT_ROOT / "data" / "processed"))
)


def require_database() -> None:
    """Lanza ValueError si DATABASE_URL no está configurada."""
    if not DATABASE_URL:
        raise ValueError(
            "La variable de entorno DATABASE_URL no está definida.\n"
            "Copiá .env.example a .env y completá el connection string de Neon.\n"
            "Formato: postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require"
        )
