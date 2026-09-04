"""Clase base DataLoader — funcionalidad común a todos los loaders."""

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import pandas as pd
from rich.console import Console

console = Console()


class DataLoader(ABC):
    """Clase base abstracta para todos los loaders del pipeline.

    Provee utilidades comunes:
    - Validación de columnas requeridas
    - Cálculo de SHA256 del archivo fuente
    - Detección de duplicados en pipeline_runs
    - Registro del run en pipeline_runs
    - Archivado del archivo procesado
    """

    source_name: str  # Debe definirse en cada subclase

    # ── Utilidades de archivo ────────────────────────────────────────────────

    @staticmethod
    def compute_sha256(filepath: Path) -> str:
        """Calcula el SHA256 de un archivo de forma eficiente (streaming)."""
        h = hashlib.sha256()
        with filepath.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Validación de columnas ───────────────────────────────────────────────

    @staticmethod
    def validate_columns(
        df: pd.DataFrame,
        required: list[str],
        filepath: Path | None = None,
    ) -> None:
        """Verifica que el DataFrame tenga todas las columnas requeridas.

        Lanza ValueError con mensaje descriptivo si faltan columnas.
        La comparación es case-insensitive y tolera espacios en los nombres.
        """
        # Normalizar nombres de columnas del DataFrame
        actual_normalized = {col.strip().lower(): col for col in df.columns}
        required_normalized = {req.strip().lower(): req for req in required}

        missing_keys = set(required_normalized.keys()) - set(actual_normalized.keys())

        if missing_keys:
            missing_display = sorted(required_normalized[k] for k in missing_keys)
            actual_display = sorted(df.columns.tolist())
            source_info = f" en {filepath.name}" if filepath else ""
            raise ValueError(
                f"Columnas requeridas faltantes{source_info}:\n"
                f"  Esperadas  : {missing_display}\n"
                f"  Encontradas: {actual_display}\n"
                f"  Faltantes  : {missing_display}"
            )

    # ── Interacción con pipeline_runs ────────────────────────────────────────

    def check_already_processed(self, sha256: str) -> bool:
        """Retorna True si el archivo ya fue procesado exitosamente (por SHA256)."""
        from pipeline.db.client import transaction

        with transaction() as cur:
            cur.execute(
                """
                SELECT filename, ran_at
                FROM pipeline_runs
                WHERE file_sha256 = %s
                  AND source      = %s
                  AND status      = 'success'
                LIMIT 1
                """,
                (sha256, self.source_name),
            )
            row = cur.fetchone()

        if row:
            filename, ran_at = row
            console.print(
                f"[yellow]⚠ Ya procesado:[/yellow] {filename} "
                f"({str(ran_at)[:10]}). Saliendo sin error."
            )
            return True
        return False

    def register_run(
        self,
        *,
        filename: str,
        sha256: str,
        records_inserted: int,
        records_updated: int,
        status: str,
        destination: str = "neon",
        error_message: str | None = None,
    ) -> None:
        """Registra el resultado de la ingesta en pipeline_runs."""
        from pipeline.db.client import transaction

        with transaction() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_runs
                    (source, destination, filename, file_sha256,
                     records_inserted, records_updated, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self.source_name,
                    destination,
                    filename,
                    sha256,
                    records_inserted,
                    records_updated,
                    status,
                    error_message,
                ),
            )

    # ── Archivado del archivo ────────────────────────────────────────────────

    @staticmethod
    def archive_file(src: Path, dest_dir: Path) -> Path:
        """Mueve el archivo fuente a dest_dir con timestamp en el nombre.

        Ejemplo: puestos_2024_q1.csv → puestos_2024_q1_20240315_143022.csv
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = src.stem
        suffix = src.suffix
        dest = dest_dir / f"{stem}_{ts}{suffix}"
        shutil.move(str(src), str(dest))
        return dest

    # ── Interfaz abstracta ───────────────────────────────────────────────────

    @abstractmethod
    def load(self, filepath: Path, *, dry_run: bool = False) -> dict:
        """Carga el archivo en Supabase.

        Args:
            filepath: Ruta al archivo a procesar.
            dry_run: Si True, valida sin escribir nada en DB ni archivar.

        Returns:
            Dict con estadísticas: inserted, updated, periodo_min, periodo_max, etc.
        """
        ...
