"""Command-line entry point for the data pipeline."""

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from cykelpatag.gtfs import DEFAULT_GTFS_URL, GtfsError, build_gtfs
from cykelpatag.guide import DEFAULT_MARKDOWN_PAGE_URL, GuideError, update_guide
from cykelpatag.router import RouterBuildError, build_router_data
from cykelpatag.rules import RulesError, load_ruleset
from cykelpatag.validation import GtfsValidationError, validate_gtfs

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
router_app = typer.Typer(help="Generate date-specific browser routing artifacts.")
app.add_typer(router_app, name="router")
pipeline_app = typer.Typer(help="Run the complete GTFS-to-browser update pipeline.")
app.add_typer(pipeline_app, name="pipeline")
DEFAULT_SOURCE_DIR = Path("data/source")
DEFAULT_OUTPUT_DIR = Path("data/generated")


def _parse_start_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise RouterBuildError("start-date must use ISO format YYYY-MM-DD") from error


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


@gtfs_app.command("validate")
def gtfs_validate(
    archive_path: Annotated[
        Path, typer.Option(help="Pruned GTFS archive to validate.")
    ] = Path("data/generated/gtfs/bike.gtfs.zip"),
    output_dir: Annotated[
        Path, typer.Option(help="Directory for gtfs-guru JSON and HTML reports.")
    ] = Path("data/generated/validation"),
) -> None:
    """Validate a pruned GTFS archive with gtfs-guru."""
    try:
        result = validate_gtfs(archive_path, output_dir)
    except GtfsValidationError as error:
        typer.echo(f"GTFS validation failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Valid GTFS: {archive_path} ({result.notice_count} notices)")
    typer.echo(f"JSON report: {result.report_json}")
    typer.echo(f"HTML report: {result.report_html}")


@router_app.command("build")
def router_build(
    gtfs_archive: Annotated[
        Path, typer.Option(help="Validated pruned GTFS archive to compile.")
    ] = Path("data/generated/gtfs/bike.gtfs.zip"),
    output_dir: Annotated[
        Path, typer.Option(help="Directory for Minotor binaries and router manifest.")
    ] = Path("data/generated/router"),
    frontend_dir: Annotated[
        Path, typer.Option(help="Frontend directory containing Minotor.")
    ] = Path("frontend"),
    start_date: Annotated[
        str | None,
        typer.Option(help="First Swedish service date as YYYY-MM-DD (defaults to today)."),
    ] = None,
    days: Annotated[int, typer.Option(min=1, help="Number of consecutive service dates.")] = 90,
    reuse_existing: Annotated[
        bool,
        typer.Option(help="Reuse existing binaries to resume an interrupted local build."),
    ] = False,
) -> None:
    """Compile a rolling range of daily Minotor timetables for the static frontend."""
    try:
        result = build_router_data(
            gtfs_archive=gtfs_archive,
            output_dir=output_dir,
            frontend_dir=frontend_dir,
            start_date=_parse_start_date(start_date),
            days=days,
            reuse_existing=reuse_existing,
        )
    except RouterBuildError as error:
        typer.echo(f"Router build failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Stops index: {result.stops_path}")
    typer.echo(f"Router manifest: {result.manifest_path}")
    typer.echo(f"Built {len(result.dates)} dates: {result.dates[0]} to {result.dates[-1]}")


@pipeline_app.command("update")
def pipeline_update(
    rules_path: Annotated[Path, typer.Option(help="Reviewed YAML bicycle rules.")] = Path(
        "rules/bike-rules.yaml"
    ),
    source_dir: Annotated[Path, typer.Option(help="Directory for downloaded GTFS ZIP.")] = (
        DEFAULT_SOURCE_DIR
    ),
    gtfs_output_dir: Annotated[
        Path, typer.Option(help="Directory for pruned GTFS artifacts.")
    ] = Path("data/generated/gtfs"),
    validation_output_dir: Annotated[
        Path, typer.Option(help="Directory for gtfs-guru reports.")
    ] = Path("data/generated/validation"),
    router_output_dir: Annotated[
        Path, typer.Option(help="Directory for Minotor binaries and manifest.")
    ] = Path("data/generated/router"),
    frontend_dir: Annotated[
        Path, typer.Option(help="Frontend directory containing Minotor.")
    ] = Path("frontend"),
    start_date: Annotated[
        str | None,
        typer.Option(help="First Swedish service date as YYYY-MM-DD (defaults to today)."),
    ] = None,
    days: Annotated[int, typer.Option(min=1, help="Number of consecutive service dates.")] = 90,
    url: Annotated[str, typer.Option(help="GTFS Sverige 2 ZIP endpoint.")] = DEFAULT_GTFS_URL,
) -> None:
    """Download, prune, validate, and compile browser routing data."""
    try:
        pruned = build_gtfs(
            rules_path=rules_path,
            source_dir=source_dir,
            output_dir=gtfs_output_dir,
            url=url,
        )
        validated = validate_gtfs(pruned.archive_path, validation_output_dir)
        router = build_router_data(
            gtfs_archive=pruned.archive_path,
            output_dir=router_output_dir,
            frontend_dir=frontend_dir,
            start_date=_parse_start_date(start_date),
            days=days,
        )
    except (GtfsError, GtfsValidationError, RouterBuildError, RulesError) as error:
        typer.echo(f"Pipeline update failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(f"Pruned GTFS: {pruned.archive_path}")
    typer.echo(f"Validation report: {validated.report_json}")
    typer.echo(f"Router manifest: {router.manifest_path}")
