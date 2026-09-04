"""Conexión a DuckDB local — base analítica.

DuckDB almacena datos grandes (OEDE completo: ~3.5M filas, todos los sectores)
sin límite de tamaño. Es un archivo local que NO se commitea al repo.

Archivo: data/analytics.db  (configurable via DUCKDB_PATH)

Por qué DuckDB y no Neon para OEDE:
  - Neon free tier tiene 512 MB de límite de storage
  - El OEDE completo supera ese límite (~400-500 MB con índices)
  - DuckDB no tiene límite y es muy eficiente para queries analíticas
  - DuckDB solo corre localmente; GitHub Actions lee los pesos ya
    calculados desde Neon (event_weights), no necesita DuckDB
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from pipeline.config import DUCKDB_PATH


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Conexión al archivo DuckDB local.

    Args:
        read_only: Si True, abre en modo lectura (útil para queries concurrentes).
    """
    # Asegurar que el directorio existe
    Path(DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DUCKDB_PATH), read_only=read_only)


def init_schema() -> None:
    """Crea tablas y vistas en DuckDB si no existen.

    Llamar una vez al inicio del pipeline o al ingestar por primera vez.
    Es idempotente (usa IF NOT EXISTS / CREATE OR REPLACE).
    """
    conn = get_connection()
    try:
        # Tabla principal OEDE: todos los sectores (sin filtrar manufactura)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oede_empleo (
                codgeo_depto  VARCHAR(5) NOT NULL,
                clae2         VARCHAR(2),          -- código CLAE a 2 dígitos
                letra         VARCHAR(1),          -- 'C'=manufactura, 'G'=comercio, etc.
                periodo       DATE    NOT NULL,    -- primer día del mes: 2024-01-01
                puestos       INTEGER,
                ingested_from VARCHAR(255)         -- nombre del archivo fuente
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS oede_pk
                ON oede_empleo (codgeo_depto, clae2, periodo)
        """)

        # Vista: total de empleo por departamento y período (denominador)
        conn.execute("""
            CREATE OR REPLACE VIEW oede_total_depto AS
            SELECT
                codgeo_depto,
                periodo,
                SUM(puestos) AS puestos_total
            FROM oede_empleo
            GROUP BY codgeo_depto, periodo
        """)

        # Vista: empleo manufacturero por departamento y período
        conn.execute("""
            CREATE OR REPLACE VIEW oede_manufactura_depto AS
            SELECT
                codgeo_depto,
                periodo,
                SUM(puestos) AS puestos_manufactura
            FROM oede_empleo
            WHERE letra = 'C' OR (TRY_CAST(clae2 AS INTEGER) BETWEEN 10 AND 33)
            GROUP BY codgeo_depto, periodo
        """)
    finally:
        conn.close()


def upsert_oede(
    data: list[dict] | pd.DataFrame,
    filename: str = "",
) -> tuple[int, int]:
    """Inserta o reemplaza registros en oede_empleo.

    DuckDB usa INSERT OR REPLACE sobre la clave definida en oede_pk.
    Para grandes volúmenes (~3.5M filas), pasar un pd.DataFrame es
    órdenes de magnitud más rápido y eficiente en memoria.

    Args:
        data: DataFrame de pandas o lista de dicts.
        filename: Nombre del archivo fuente (usado si data es DataFrame).

    Returns:
        (inserted, updated) — Estimación de filas insertadas vs actualizadas.
    """
    if data is None or (isinstance(data, (list, pd.DataFrame)) and len(data) == 0):
        return 0, 0

    init_schema()
    conn = get_connection()

    try:
        count_before = conn.execute("SELECT COUNT(*) FROM oede_empleo").fetchone()[0]

        if isinstance(data, pd.DataFrame):
            df = data
            clae2_col = "clae2_norm" if "clae2_norm" in df.columns else "clae2"
            clae2_series = df[clae2_col].astype(str)

            # Si la columna letra no vino o está vacía, inferir 'C' para manufactura (10-33)
            clae2_numeric = pd.to_numeric(clae2_series, errors="coerce")
            is_manufactura = (clae2_numeric >= 10) & (clae2_numeric <= 33)

            if "letra" in df.columns:
                raw_letra = df["letra"].fillna("").astype(str).str.strip().str.upper()
                letra_series = raw_letra.where(raw_letra != "", other=None)
                letra_series = letra_series.mask(letra_series.isna() & is_manufactura, "C")
            else:
                letra_series = pd.Series(
                    [("C" if m else None) for m in is_manufactura],
                    index=df.index,
                )

            df_view = pd.DataFrame({
                "codgeo_depto": df["codgeo_depto"].astype(str),
                "clae2": clae2_series,
                "letra": letra_series,
                "periodo": df["periodo"].astype(str),
                "puestos": df["puestos_num" if "puestos_num" in df.columns else "puestos"].astype(int),
                "ingested_from": filename or df.get("ingested_from", [""] * len(df)),
            })

            conn.execute("""
                INSERT OR REPLACE INTO oede_empleo
                    (codgeo_depto, clae2, letra, periodo, puestos, ingested_from)
                SELECT
                    codgeo_depto,
                    clae2,
                    letra,
                    periodo::DATE,
                    puestos,
                    ingested_from
                FROM df_view
            """)
            total_records = len(df_view)
        else:
            records = data
            conn.executemany(
                """
                INSERT OR REPLACE INTO oede_empleo
                    (codgeo_depto, clae2, letra, periodo, puestos, ingested_from)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r["codgeo_depto"],
                        r["clae2"],
                        r.get("letra") or None,
                        r["periodo"],
                        r["puestos"],
                        r.get("ingested_from", filename),
                    )
                    for r in records
                ],
            )
            total_records = len(records)

        count_after = conn.execute("SELECT COUNT(*) FROM oede_empleo").fetchone()[0]
        net_new = max(0, count_after - count_before)
        updated = max(0, total_records - net_new)
        return net_new, updated

    finally:
        conn.close()

