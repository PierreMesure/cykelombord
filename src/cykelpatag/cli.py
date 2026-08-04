"""Command-line entry point for the data pipeline."""

import typer

app = typer.Typer(
    name="cykelpatag",
    help="Prepare bicycle-friendly public transport routing data.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Prepare bicycle-friendly public transport routing data."""
