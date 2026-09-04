"""Loader para CSVs del OEDE (Observatorio de Empleo y Dinámica Empresarial).

Fuente:
  - argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-provinciales
  - datos.produccion.gob.ar → "Puestos de trabajo por departamento/partido y sector"

Columnas requeridas en el CSV:
  codigo_departamento_indec, clae2, fecha, puestos
  (letra es opcional)

El loader:
  1. Calcula SHA256 y detecta duplicados en pipeline_runs (Neon)
  2. Valida columnas requeridas
  3. Parsea y normaliza: codgeo_depto (5 chars), fecha (DATE), clae2 (2 chars)
  4. Carga TODOS los sectores en DuckDB local (data/analytics.db)
  5. Archiva el archivo en data/processed/oede/
  6. Registra en pipeline_runs (Neon) con destination='duckdb'
  7. Imprime resumen con rich
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pipeline import config
from pipeline.loaders.base import DataLoader

console = Console()

# Columnas obligatorias en el CSV de entrada
REQUIRED_COLUMNS = [
    "codigo_departamento_indec",
    "clae2",
    "fecha",
    "puestos",
]

# Columnas opcionales (presentes en algunos formatos del OEDE)
OPTIONAL_COLUMNS = ["letra"]

# Rango CLAE2 de manufactura (sección C del CIIU)
CLAE2_MANUFACTURA_MIN = 10
CLAE2_MANUFACTURA_MAX = 33


def _parse_fecha(value: str | int) -> str:
    """Convierte distintos formatos de fecha a 'YYYY-MM-DD' (primer día del mes).

    Formatos soportados:
      - YYYYMM  (ej: 202401)
      - YYYY-MM  (ej: 2024-01)
      - YYYY-MM-DD  (ej: 2024-01-15 → normaliza al primer día)
      - YYYY-M  (ej: 2024-1)
    """
    s = str(value).strip()

    # YYYYMM → 6 dígitos sin separador
    if re.fullmatch(r"\d{6}", s):
        return f"{s[:4]}-{s[4:6]}-01"

    # YYYY-MM o YYYY-M
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-01"

    # YYYY-MM-DD → truncar al primer día del mes
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-\d{1,2}", s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-01"

    raise ValueError(
        f"Formato de fecha no reconocido: '{value}'. "
        "Formatos soportados: YYYYMM, YYYY-MM, YYYY-MM-DD"
    )


def _is_manufactura(row: pd.Series) -> bool:
    """Retorna True si la fila pertenece al sector manufactura.

    Acepta dos mecanismos de filtro (cualquiera es suficiente):
      - letra == 'C'  (cuando la columna existe)
      - clae2 entre 10 y 33  (siempre disponible)
    """
    letra = str(row.get("letra", "")).strip().upper()
    if letra == "C":
        return True
    try:
        clae2_num = int(str(row.get("clae2", "")).strip())
        return CLAE2_MANUFACTURA_MIN <= clae2_num <= CLAE2_MANUFACTURA_MAX
    except (ValueError, TypeError):
        return False


class OEDELoader(DataLoader):
    """Loader para archivos CSV del OEDE."""

    source_name = "oede"

    def load(self, filepath: Path, *, dry_run: bool = False) -> dict:
        """Carga un CSV del OEDE en Neon (PostgreSQL).

        Args:
            filepath: Ruta al archivo CSV.
            dry_run: Si True, solo valida sin escribir ni archivar.

        Returns:
            Dict con estadísticas de la carga.
        """
        filepath = Path(filepath).resolve()

        if not filepath.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {filepath}")

        mode_label = "[dim](dry-run)[/dim]" if dry_run else ""
        console.print(f"\n[bold cyan]OEDE Loader[/bold cyan] {mode_label}")
        console.print(f"  Archivo: [blue]{filepath}[/blue]")

        # ── Paso 1: SHA256 y detección de duplicados ─────────────────────────
        console.print("  Calculando SHA256...", end=" ")
        sha256 = self.compute_sha256(filepath)
        console.print(f"[dim]{sha256[:12]}…[/dim]")

        if not dry_run and self.check_already_processed(sha256):
            return {"status": "skipped", "sha256": sha256}

        # ── Paso 2: Leer CSV y validar columnas ──────────────────────────────
        console.print("  Leyendo CSV...", end=" ")
        try:
            df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
        except Exception as exc:
            raise ValueError(f"No se pudo leer el CSV: {exc}") from exc

        # Normalizar nombres de columnas: strip + lower
        df.columns = [c.strip().lower() for c in df.columns]
        console.print(f"[dim]{len(df):,} filas brutas[/dim]")

        self.validate_columns(df, REQUIRED_COLUMNS, filepath)

        # ── Paso 3: Parsear y normalizar ─────────────────────────────────────
        console.print("  Normalizando campos...")

        errors: list[str] = []

        def safe_parse_fecha(val: str, idx: int) -> str | None:
            try:
                return _parse_fecha(val)
            except ValueError as e:
                errors.append(f"  Fila {idx + 2}: {e}")
                return None

        df["codgeo_depto"] = df["codigo_departamento_indec"].str.strip().str.zfill(5)
        df["clae2_norm"] = df["clae2"].str.strip().str.zfill(2)
        df["periodo"] = [
            safe_parse_fecha(v, i) for i, v in enumerate(df["fecha"])
        ]

        # Descartar códigos CLAE2 inválidos (ej: 999 = fila de total/agregado).
        # Los códigos reales tienen exactamente 2 dígitos (01-97).
        mask_clae2_valido = df["clae2_norm"].str.len() == 2
        n_clae2_invalidos = (~mask_clae2_valido).sum()
        if n_clae2_invalidos > 0:
            invalidos_ejemplo = (
                df.loc[~mask_clae2_valido, "clae2"]
                .unique()[:5]
                .tolist()
            )
            console.print(
                f"[yellow]  ⚠ {n_clae2_invalidos:,} filas con código clae2 inválido "
                f"(se omitirán): {invalidos_ejemplo}[/yellow]"
            )
        df = df[mask_clae2_valido].copy()

        # 'letra' es opcional
        if "letra" not in df.columns:
            df["letra"] = ""
            console.print("  [dim]Columna 'letra' no encontrada[/dim]")

        # Reportar errores de parseo (sin abortar si son pocos)
        if errors:
            console.print(
                f"[yellow]  ⚠ {len(errors)} filas con fecha inválida (se omitirán):[/yellow]"
            )
            for err in errors[:5]:
                console.print(f"[dim]{err}[/dim]")
            if len(errors) > 5:
                console.print(f"[dim]  … y {len(errors) - 5} más[/dim]")

        # Descartar filas sin período válido
        df = df[df["periodo"].notna()].copy()

        # Convertir puestos a int (descartar no numéricos)
        df["puestos_num"] = pd.to_numeric(df["puestos"], errors="coerce")
        invalid_puestos = df["puestos_num"].isna().sum()
        if invalid_puestos > 0:
            console.print(
                f"[yellow]  ⚠ {invalid_puestos:,} filas con 'puestos' no numérico (se omitirán)[/yellow]"
            )
        df = df[df["puestos_num"].notna()].copy()
        df["puestos_num"] = df["puestos_num"].astype(int)

        # ── Paso 4: Preparar filas a insertar (todos los sectores en DuckDB) ──
        df_out = df.copy()

        total_bruto = len(df)
        total_out = len(df_out)
        clae2_sectores = df_out["clae2_norm"].nunique()
        console.print(
            f"  Filas a insertar: [green]{total_out:,}[/green] "
            f"([dim]{clae2_sectores} sectores CLAE2 distintos[/dim])"
        )

        if df_out.empty:
            console.print(
                "[yellow]⚠ No se encontraron filas válidas para insertar.[/yellow]"
            )
            if not dry_run:
                self.register_run(
                    filename=filepath.name,
                    sha256=sha256,
                    records_inserted=0,
                    records_updated=0,
                    status="success",
                    destination="duckdb",
                )
            return {"status": "success", "inserted": 0, "updated": 0}

        # Estadísticas del período
        periodo_min = df_out["periodo"].min()
        periodo_max = df_out["periodo"].max()
        deptos_cubiertos = df_out["codgeo_depto"].nunique()

        if dry_run:
            self._print_summary(
                total_out=total_out,
                inserted=0,
                updated=0,
                periodo_min=periodo_min,
                periodo_max=periodo_max,
                deptos=deptos_cubiertos,
                archived_path=None,
                dry_run=True,
            )
            return {
                "status": "dry_run",
                "rows_total": total_out,
                "periodo_min": periodo_min,
                "periodo_max": periodo_max,
                "deptos": deptos_cubiertos,
            }

        # ── Paso 5: Inserción en DuckDB ───────────────────────────────────────
        console.print("  Insertando en DuckDB...")
        from pipeline.db import duckdb as duck_db

        inserted, updated = duck_db.upsert_oede(df_out, filepath.name)

        # ── Paso 6: Archivar archivo ──────────────────────────────────────────
        dest_dir = config.DATA_PROCESSED_DIR / "oede"
        archived = self.archive_file(filepath, dest_dir)
        console.print(f"  Archivado: [dim]{archived}[/dim]")

        # ── Paso 7: Registrar en pipeline_runs (Neon) ────────────────────────
        self.register_run(
            filename=filepath.name,
            sha256=sha256,
            records_inserted=inserted,
            records_updated=updated,
            status="success",
            destination="duckdb",
        )

        # ── Paso 8: Imprimir resumen ──────────────────────────────────────────
        self._print_summary(
            total_out=total_out,
            inserted=inserted,
            updated=updated,
            periodo_min=periodo_min,
            periodo_max=periodo_max,
            deptos=deptos_cubiertos,
            archived_path=archived,
            dry_run=False,
        )

        return {
            "status": "success",
            "inserted": inserted,
            "updated": updated,
            "rows_total": total_out,
            "periodo_min": periodo_min,
            "periodo_max": periodo_max,
            "deptos": deptos_cubiertos,
            "archived": str(archived),
        }

    # ── Helpers privados ─────────────────────────────────────────────────────

    @staticmethod
    def _print_summary(
        *,
        total_out: int,
        inserted: int,
        updated: int,
        periodo_min: str,
        periodo_max: str,
        deptos: int,
        archived_path: Path | None,
        dry_run: bool,
    ) -> None:
        """Imprime el resumen final con rich."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()

        if dry_run:
            table.add_row("Modo", "[yellow]DRY-RUN (sin escritura)[/yellow]")

        table.add_row("Filas a insertar", f"[green]{total_out:,}[/green]")

        if not dry_run:
            table.add_row("Insertadas", f"[green]{inserted:,}[/green]")
            table.add_row("Actualizadas", f"[blue]{updated:,}[/blue]")

        table.add_row("Período", f"{periodo_min} → {periodo_max}")
        table.add_row("Departamentos", str(deptos))

        if archived_path:
            table.add_row("Archivado", f"[dim]{archived_path.name}[/dim]")

        icon = "🔍" if dry_run else "✓"
        title = f"{icon} OEDE procesado"
        console.print(Panel(table, title=title, border_style="green" if not dry_run else "yellow"))
