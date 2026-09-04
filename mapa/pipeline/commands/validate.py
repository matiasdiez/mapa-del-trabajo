"""Subcomando: validate — dry-run sin escribir en DB ni archivar."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()

# Mismo registro de loaders que ingest.py
LOADERS: dict[str, str] = {
    "oede": "pipeline.loaders.oede.OEDELoader",
}


def _get_loader(source: str):
    if source not in LOADERS:
        available = ", ".join(LOADERS.keys())
        raise click.BadParameter(
            f"Fuente desconocida: '{source}'. Disponibles: {available}",
            param_hint="--source",
        )
    module_path, class_name = LOADERS[source].rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


@click.command("validate")
@click.option(
    "--source",
    required=True,
    type=click.Choice(list(LOADERS.keys()), case_sensitive=False),
    help="Fuente de datos a validar.",
)
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Ruta al archivo a validar.",
)
def validate_command(source: str, filepath: Path) -> None:
    """Valida un archivo sin escribir nada en la base de datos (dry-run).

    Útil para verificar el formato antes de un ingest real.
    No requiere credenciales de Supabase.

    \b
    Ejemplos:
      python -m pipeline validate --source oede --file data/incoming/oede/puestos.csv
    """
    try:
        loader = _get_loader(source)
        loader.load(filepath, dry_run=True)
        console.print("\n[bold green]✓ Validación exitosa.[/bold green] Archivo listo para ingestar.")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]✗ Error de validación:[/bold red] {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        console.print(f"[bold red]✗ Error inesperado:[/bold red] {exc}")
        raise
