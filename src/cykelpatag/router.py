"""Build compact, date-specific Minotor artifacts for the static frontend."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


class RouterBuildError(RuntimeError):
    """Raised when Minotor artifacts cannot be generated."""


@dataclass(frozen=True)
class RouterBuildResult:
    """Artifacts emitted for a contiguous range of service dates."""

    manifest_path: Path
    stops_path: Path
    dates: tuple[date, ...]


def stockholm_today() -> date:
    """Return today's service date in the feed's timezone."""
    return datetime.now(ZoneInfo("Europe/Stockholm")).date()


def _minotor_command(frontend_dir: Path) -> str:
    local = frontend_dir / "node_modules" / ".bin" / "minotor"
    if local.exists():
        return str(local)
    installed = shutil.which("minotor")
    if installed:
        return installed
    raise RouterBuildError(
        "Minotor is not installed. Run 'npm --prefix frontend install' before building router data."
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_router_data(
    *,
    gtfs_archive: Path = Path("data/generated/gtfs/bike.gtfs.zip"),
    output_dir: Path = Path("data/generated/router"),
    frontend_dir: Path = Path("frontend"),
    start_date: date | None = None,
    days: int = 90,
    transfer_radius_meters: int = 500,
    reuse_existing: bool = False,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> RouterBuildResult:
    """Generate a shared stops index and one Minotor timetable per service day."""
    if days < 1:
        raise RouterBuildError("days must be at least 1")
    if not gtfs_archive.is_file():
        raise RouterBuildError(f"Pruned GTFS archive does not exist: {gtfs_archive}")
    minotor = _minotor_command(frontend_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    first_day = start_date or stockholm_today()
    service_dates = tuple(first_day + timedelta(days=offset) for offset in range(days))
    stops_path = output_dir / "stops.bin"

    def execute(arguments: list[str]) -> None:
        result = run(arguments, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout)[-2000:].strip()
            raise RouterBuildError(f"Minotor failed: {detail}")

    for index, service_date in enumerate(service_dates):
        timetable_path = output_dir / f"timetable-{service_date.isoformat()}.bin"
        if reuse_existing and timetable_path.is_file():
            continue
        arguments = [
            minotor,
            "parse-gtfs",
            str(gtfs_archive),
            "--date",
            service_date.isoformat(),
            "-t",
            str(timetable_path),
            "-s",
            str(stops_path),
            "--virtual-transfers-radius",
            str(transfer_radius_meters),
        ]
        execute(arguments)
        if not timetable_path.is_file():
            raise RouterBuildError(f"Minotor did not create {timetable_path}")
        if index == 0 and not stops_path.is_file():
            raise RouterBuildError(f"Minotor did not create {stops_path}")

    manifest_path = output_dir / "router-manifest.json"
    manifest = {
        "schema_version": 1,
        "timezone": "Europe/Stockholm",
        "stops_file": stops_path.name,
        "stops_sha256": _sha256(stops_path),
        "available_dates": [
            {
                "date": service_date.isoformat(),
                "timetable_file": f"timetable-{service_date.isoformat()}.bin",
                "sha256": _sha256(output_dir / f"timetable-{service_date.isoformat()}.bin"),
                "bytes": (output_dir / f"timetable-{service_date.isoformat()}.bin").stat().st_size,
            }
            for service_date in service_dates
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return RouterBuildResult(
        manifest_path=manifest_path, stops_path=stops_path, dates=service_dates
    )
