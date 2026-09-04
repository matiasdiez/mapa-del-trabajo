"""Conexión a Neon (PostgreSQL serverless) via psycopg2.

Usado para:
  - Datos operacionales: factory_events, geo_departamentos, event_weights
  - Audit log: pipeline_runs  (accesible desde GitHub Actions)

NO usado para: oede_empleo (→ DuckDB local)
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Generator

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection, cursor as PgCursor

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

# TCP keepalive: evita que Neon cierre conexiones SSL por inactividad
_CONNECT_KWARGS: dict = {
    "keepalives": 1,
    "keepalives_idle": 10,
    "keepalives_interval": 5,
    "keepalives_count": 5,
    "connect_timeout": 15,
}


def get_connection() -> PgConnection:
    """Retorna una conexión psycopg2 a Neon con keepalive habilitado."""
    if not DATABASE_URL:
        raise ValueError(
            "La variable de entorno DATABASE_URL no está definida.\n"
            "Copiá .env.example a .env y completá el connection string de Neon."
        )
    return psycopg2.connect(DATABASE_URL, **_CONNECT_KWARGS)


@contextlib.contextmanager
def transaction(
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> Generator[PgCursor, None, None]:
    """Context manager: abre conexión, expone cursor, commit al salir,
    rollback en excepción. Reintenta ante errores SSL transitorios de Neon.

    Uso::

        with transaction() as cur:
            cur.execute("INSERT INTO ...")
    """
    last_exc: Exception | None = None
    delay = retry_delay

    for attempt in range(1, max_retries + 1):
        conn: PgConnection | None = None
        try:
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    yield cur
            return
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_exc = exc
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    raise last_exc  # type: ignore[misc]


def execute_values(
    cur: PgCursor,
    sql: str,
    data: list[tuple],
    page_size: int = 1000,
) -> None:
    """Wrapper de psycopg2.extras.execute_values para upserts en batch."""
    psycopg2.extras.execute_values(cur, sql, data, page_size=page_size)
