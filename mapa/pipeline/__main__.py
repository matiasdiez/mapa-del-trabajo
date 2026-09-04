"""Punto de entrada CLI del pipeline.

Uso:
  python -m pipeline <subcomando> [opciones]

Subcomandos disponibles:
  ingest    — Ingesta un archivo en Supabase
  validate  — Valida un archivo sin escribir (dry-run)
"""

import click

from pipeline.commands.ingest import ingest_command
from pipeline.commands.validate import validate_command


@click.group()
@click.version_option("0.1.0", prog_name="mapa-pipeline")
def cli() -> None:
    """Pipeline CLI — Mapa Industrial Argentina.

    Herramienta de línea de comandos para ingestar y procesar datos del
    mapa interactivo de cierre de fábricas en Argentina.
    """
    pass


cli.add_command(ingest_command)
cli.add_command(validate_command)


if __name__ == "__main__":
    cli()
