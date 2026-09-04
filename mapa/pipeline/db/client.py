"""Cliente de base de datos — conexión a Neon via psycopg2.

Neon es PostgreSQL serverless; se conecta igual que a cualquier instancia
de Postgres usando una connection string con sslmode=require.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Generator

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection, cursor as PgCursor

# La variable DATABASE_URL debe estar definida en .env; falla explícito si no.
# Formato esperado:
#   postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require
_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

# Parámetros extra para psycopg2.connect() — keepalive evita que Neon
# cierre conexiones silenciosamente durante operaciones largas.
_CONNECT_KWARGS: dict = {
    "keepalives": 1,
    "keepalives_idle": 10,       # segundos sin actividad antes de enviar keepalive
    "keepalives_interval": 5,    # segundos entre reintentos de keepalive
    "keepalives_count": 5,       # intentos antes de declarar la conexión muerta
    "connect_timeout": 15,       # timeout de conexión inicial
}


def get_connection() -> PgConnection:
    """Retorna una conexión psycopg2 a Neon con keepalive habilitado.

    Preferir el context manager `transaction()` para manejo automático
    de commit/rollback y cierre de conexión.
    """
    if not _DATABASE_URL:
        raise ValueError(
            "La variable de entorno DATABASE_URL no está definida.\n"
            "Copiá .env.example a .env y completá el connection string de Neon."
        )
    return psycopg2.connect(_DATABASE_URL, **_CONNECT_KWARGS)


@contextlib.contextmanager
def transaction(
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> Generator[PgCursor, None, None]:
    """Context manager que abre conexión, expone cursor, hace commit al salir
    y rollback si hay excepción.

    Reintenta automáticamente ante errores de conexión transitorios (ej: Neon
    cierra la conexión SSL por inactividad entre chunks).

    Args:
        max_retries: Número máximo de reintentos ante OperationalError.
        retry_delay: Segundos de espera entre reintentos (se duplica cada vez).

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
            with conn:               # psycopg2: commit al salir del with, rollback en excepción
                with conn.cursor() as cur:
                    yield cur
            return                   # éxito: salir del loop
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_exc = exc
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2           # backoff exponencial
            # si fue el último intento, re-raise al salir del loop
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
    """Wrapper de psycopg2.extras.execute_values para upserts en batch.

    Más eficiente que execute() en loop para miles de registros.
    """
    psycopg2.extras.execute_values(cur, sql, data, page_size=page_size)
