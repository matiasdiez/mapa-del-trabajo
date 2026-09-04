"""Subcomando: ingest — ingesta datos de distintas fuentes en Supabase."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()

# Registro de loaders disponibles por --source
LOADERS: dict[str, str] = {
    "oede": "pipeline.loaders.oede.OEDELoader",
    # Fase 2:
    # "indec-geo": "pipeline.loaders.indec_geo.IndecGeoLoader",
    # "eventos": "pipeline.loaders.eventos.EventosLoader",
}


def _get_loader(source: str):
    """Importa y devuelve la instancia del loader correspondiente a `source`."""
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


@click.command("ingest")
@click.option(
    "--source",
    required=True,
    type=click.Choice(list(LOADERS.keys()), case_sensitive=False),
    help="Fuente de datos a ingestar.",
)
@click.option(
    "--file",
    "filepath",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Ruta al archivo descargado manualmente.",
)
def ingest_command(source: str, filepath: Path) -> None:
    """Ingesta un archivo de datos en Supabase.

    \b
    Ejemplos:
      python -m pipeline ingest --source oede --file data/incoming/oede/puestos_2024_q1.csv
    """
    try:
        loader = _get_loader(source)
        result = loader.load(filepath, dry_run=False)

        if result.get("status") == "skipped":
            console.print("[yellow]ℹ Archivo ya procesado anteriormente. No se realizaron cambios.[/yellow]")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]✗ Error:[/bold red] {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        console.print(f"[bold red]✗ Error inesperado:[/bold red] {exc}")
        raise
