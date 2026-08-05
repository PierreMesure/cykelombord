"""Command-line entry point for the data pipeline."""

from pathlib import Path
from typing import Annotated

import typer

from cykelpatag.gtfs import DEFAULT_GTFS_URL, GtfsError, build_gtfs
from cykelpatag.guide import DEFAULT_MARKDOWN_PAGE_URL, GuideError, update_guide
from cykelpatag.rules import RulesError, load_ruleset

app = typer.Typer(
    name="cykelpatag",
    help="Prepare bicycle-friendly public transport routing data.",
    no_args_is_help=True,
)
guide_app = typer.Typer(help="Download and convert Naturskyddsföreningen's bicycle guide.")
app.add_typer(guide_app, name="guide")
rules_app = typer.Typer(help="Validate curated bicycle-carriage rules.")
app.add_typer(rules_app, name="rules")
gtfs_app = typer.Typer(help="Download and prune GTFS Sverige 2.")
app.add_typer(gtfs_app, name="gtfs")
DEFAULT_SOURCE_DIR = Path("data/source")
DEFAULT_OUTPUT_DIR = Path("data/generated")


@app.callback()
def main() -> None:
    """Prepare bicycle-friendly public transport routing data."""


@guide_app.command("update")
def guide_update(
    page_url: Annotated[
        str, typer.Option(help="Markdown representation of the stable guide page.")
    ] = DEFAULT_MARKDOWN_PAGE_URL,
    source_dir: Annotated[
        Path, typer.Option(help="Directory for the downloaded PDF.")
    ] = DEFAULT_SOURCE_DIR,
    output_dir: Annotated[
        Path, typer.Option(help="Directory for generated Markdown and metadata.")
    ] = DEFAULT_OUTPUT_DIR,
) -> None:
    """Download the current guide PDF and convert it to reviewable Markdown."""
    try:
        result = update_guide(
            page_url=page_url,
            source_dir=source_dir,
            output_dir=output_dir,
        )
    except GuideError as error:
        typer.echo(f"Guide update failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Downloaded: {result.pdf_path}")
    typer.echo(f"Markdown: {result.markdown_path}")
    typer.echo(f"Metadata: {result.metadata_path}")


@rules_app.command("validate")
def rules_validate(
    path: Annotated[Path, typer.Option(help="YAML ruleset to validate.")] = Path(
        "rules/bike-rules.yaml"
    ),
) -> None:
    """Validate a curated ruleset and report its rule count."""
    try:
        ruleset = load_ruleset(path)
    except RulesError as error:
        typer.echo(f"Ruleset validation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Valid ruleset v{ruleset.schema_version}: {len(ruleset.rules)} rules")


@gtfs_app.command("build")
def gtfs_build(
    rules_path: Annotated[Path, typer.Option(help="Reviewed YAML bicycle rules.")] = Path(
        "rules/bike-rules.yaml"
    ),
    source_dir: Annotated[Path, typer.Option(help="Directory for the downloaded GTFS ZIP.")] = (
        DEFAULT_SOURCE_DIR
    ),
    output_dir: Annotated[Path, typer.Option(help="Directory for pruned GTFS artifacts.")] = Path(
        "data/generated/gtfs"
    ),
    source_archive: Annotated[
        Path | None, typer.Option(help="Existing GTFS ZIP to prune without downloading.")
    ] = None,
    url: Annotated[str, typer.Option(help="GTFS Sverige 2 ZIP endpoint.")] = DEFAULT_GTFS_URL,
) -> None:
    """Download GTFS Sverige 2 and retain only explicitly bicycle-compatible services."""
    try:
        result = build_gtfs(
            rules_path=rules_path,
            source_dir=source_dir,
            output_dir=output_dir,
            url=url,
            source_archive=source_archive,
        )
    except (GtfsError, RulesError) as error:
        typer.echo(f"GTFS build failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Downloaded: {result.source_path}")
    typer.echo(f"Pruned GTFS: {result.archive_path}")
    typer.echo(f"Resolution report: {result.resolution_path}")
    typer.echo(
        f"Kept {result.kept_trip_count} trips; resolved {result.resolved_rule_count} rules, "
        f"unresolved {result.unresolved_rule_count}."
    )
