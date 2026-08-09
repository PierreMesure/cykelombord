"""GTFS validation through the native gtfs-guru Python package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class GtfsValidationError(RuntimeError):
    """Raised when GTFS validation cannot complete or reports errors."""


@dataclass(frozen=True)
class GtfsValidationResult:
    """Summary of a persisted gtfs-guru validation report."""

    is_valid: bool
    notice_count: int
    report_json: Path
    report_html: Path


def validate_gtfs(
    archive_path: Path = Path("data/generated/gtfs/bike.gtfs.zip"),
    output_dir: Path = Path("data/generated/validation"),
) -> GtfsValidationResult:
    """Validate a GTFS archive and fail only when gtfs-guru finds errors."""
    if not archive_path.is_file():
        raise GtfsValidationError(f"GTFS archive does not exist: {archive_path}")
    try:
        import gtfs_guru  # type: ignore[import-not-found]
    except ImportError as error:
        raise GtfsValidationError(
            "gtfs-guru is unavailable; run 'uv sync' on a supported platform."
        ) from error
    output_dir.mkdir(parents=True, exist_ok=True)
    report: Any = gtfs_guru.validate(str(archive_path))
    report_json = output_dir / "report.json"
    report_html = output_dir / "report.html"
    report.save_json(str(report_json))
    report.save_html(str(report_html))
    result = GtfsValidationResult(
        is_valid=bool(report.is_valid),
        notice_count=len(report.notices),
        report_json=report_json,
        report_html=report_html,
    )
    if not result.is_valid:
        raise GtfsValidationError(
            f"gtfs-guru found errors; see {result.report_json} and {result.report_html}"
        )
    return result
