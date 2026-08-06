"""Download and conservatively prune GTFS Sverige 2 using reviewed bicycle rules."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import duckdb
import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from cykelpatag.rules import Rule, Ruleset, load_ruleset

DEFAULT_GTFS_URL = "https://api.resrobot.se/gtfs/sweden.zip"
REQUIRED_GTFS_FILES = frozenset(
    {"agency.txt", "routes.txt", "trips.txt", "stop_times.txt", "stops.txt"}
)
# GTFS Sverige 2 uses the extended route-type hierarchy. The listed values were
# observed in the live feed and correspond to railway, bus/coach, and water service.
ROUTE_TYPES = {
    "rail": {"2", "101", "102", "106"},
    "bus": {"3", "700", "702"},
    "ferry": {"4", "1000"},
}
STATION_SUFFIXES = ("centralstation", "resecentrum", "station", "stasjon")


class GtfsError(RuntimeError):
    """Raised when the GTFS feed cannot be safely downloaded or pruned."""


class GtfsSettings(BaseSettings):
    """GTFS credentials; the value is intentionally never included in output."""

    trafiklab_gtfs_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@dataclass(frozen=True)
class GtfsBuildResult:
    """Artifacts emitted by a successful GTFS build."""

    source_path: Path
    archive_path: Path
    manifest_path: Path
    resolution_path: Path
    kept_trip_count: int
    resolved_rule_count: int
    unresolved_rule_count: int


def _normalise(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _service_key(value: str) -> str:
    """Normalise a service label and its common Swedish definite plural ending."""
    key = _normalise(value)
    return key.removesuffix("en")


def _stop_name_keys(value: str) -> set[str]:
    """Return a GTFS stop label and its station-level equivalent when unambiguous."""
    key = _normalise(value)
    keys = {key}
    for suffix in STATION_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            keys.add(key.removesuffix(suffix))
    return keys


def _sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _atomic_write_json(path: Path, value: object) -> None:
    _atomic_write_bytes(path, f"{json.dumps(value, ensure_ascii=False, indent=2)}\n".encode())


def _download_gtfs(url: str, api_key: SecretStr) -> tuple[bytes, dict[str, str]]:
    try:
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            response = client.get(url, params={"key": api_key.get_secret_value()})
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise GtfsError(
            "GTFS Sverige 2 download returned "
            f"HTTP {error.response.status_code}; check that TRAFIKLAB_GTFS_API_KEY is enabled "
            "for GTFS Sverige 2."
        ) from error
    except httpx.HTTPError as error:
        raise GtfsError(
            f"Could not download GTFS Sverige 2 ({type(error).__name__}); check network access."
        ) from error
    if not response.content.startswith(b"PK\x03\x04"):
        content_type = response.headers.get("content-type", "unknown")
        detail = response.text[:200].replace("\n", " ").strip()
        raise GtfsError(
            "GTFS Sverige 2 did not return a ZIP archive "
            f"(HTTP {response.status_code}, {content_type}): {detail}"
        )
    return response.content, dict(response.headers)


def _extract_zip_safely(content: bytes, destination: Path) -> set[str]:
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(content)) as archive:
            names = {member.filename for member in archive.infolist() if not member.is_dir()}
            missing = REQUIRED_GTFS_FILES - names
            if missing:
                message = ", ".join(sorted(missing))
                raise GtfsError(f"GTFS archive is missing required files: {message}")
            for member in archive.infolist():
                target = destination / member.filename
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise GtfsError(f"Refusing unsafe ZIP member: {member.filename}")
            archive.extractall(destination)
    except zipfile.BadZipFile as error:
        raise GtfsError("GTFS Sverige 2 returned an invalid ZIP archive.") from error
    return names


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_headers(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    return set(header)


def _create_view(connection: Any, name: str, path: Path) -> None:
    connection.execute(
        f"CREATE VIEW {name} AS SELECT * FROM read_csv_auto('{_sql_path(path)}', "
        "header=true, all_varchar=true)"
    )


def _copy_query(connection: Any, query: str, output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = _count_query(connection, f"SELECT count(*) FROM ({query})")
    connection.execute(
        f"COPY ({query}) TO '{_sql_path(output)}' (HEADER, DELIMITER ',', QUOTE '\"')"
    )
    return count


def _count_query(connection: Any, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise GtfsError("DuckDB returned no row while counting GTFS data.")
    return int(row[0])


def _insert_ids(connection: Any, table: str, column: str, values: Iterable[str]) -> None:
    unique_values = sorted(set(values))
    connection.execute(f"CREATE TEMP TABLE {table} ({column} VARCHAR PRIMARY KEY)")
    if unique_values:
        connection.executemany(
            f"INSERT INTO {table} VALUES (?)", [(value,) for value in unique_values]
        )


def _corridor_endpoints(corridor: str) -> tuple[str, set[str]] | None:
    parts = [part.strip() for part in re.split(r"[–-]", corridor) if part.strip()]
    if len(parts) < 2:
        return None
    return parts[0], {part.strip() for part in parts[-1].split("/") if part.strip()}


def _resolve_rule_routes(
    *,
    rule: Rule,
    agencies: list[dict[str, str]],
    routes: list[dict[str, str]],
    stops: list[dict[str, str]],
    connection: Any,
) -> tuple[list[str], str | None]:
    """Resolve a source rule only when its explicit GTFS selectors can be checked."""
    if rule.match.vehicle_types:
        return [], "GTFS Sverige 2 has no standard train-vehicle-type selector"

    requested_agencies = {
        _normalise(value) for value in [*rule.match.agencies, *rule.match.agency_aliases]
    }
    matching_agencies = {
        row["agency_id"]
        for row in agencies
        if not requested_agencies or _normalise(row.get("agency_name", "")) in requested_agencies
    }
    if not matching_agencies:
        return [], "no exact agency_name match"

    requested_modes = set(rule.match.modes)
    allowed_route_types = {
        route_type for mode in requested_modes for route_type in ROUTE_TYPES[mode]
    }
    candidate_routes = {
        row["route_id"]
        for row in routes
        if row.get("agency_id") in matching_agencies
        and row.get("route_type") in allowed_route_types
    }
    if rule.match.services:
        requested_services = {_service_key(value) for value in rule.match.services}
        candidate_routes &= {
            row["route_id"]
            for row in routes
            if any(
                _service_key(row.get(field, "")) in requested_services
                for field in ("route_short_name", "route_long_name", "route_desc")
            )
        }
    if not candidate_routes:
        return [], "no route matched agency, mode, and service selectors"

    if not rule.match.corridors:
        return sorted(candidate_routes), None

    stop_ids_by_name: dict[str, set[str]] = defaultdict(set)
    for row in stops:
        for key in _stop_name_keys(row.get("stop_name", "")):
            stop_ids_by_name[key].add(row["stop_id"])

    corridor_routes: set[str] = set()
    for corridor in rule.match.corridors:
        endpoints = _corridor_endpoints(corridor)
        if endpoints is None:
            continue
        start, ends = endpoints
        start_ids = stop_ids_by_name.get(_normalise(start), set())
        end_ids = set().union(*(stop_ids_by_name.get(_normalise(end), set()) for end in ends))
        if not start_ids or not end_ids:
            continue
        connection.execute("DROP TABLE IF EXISTS corridor_start")
        connection.execute("DROP TABLE IF EXISTS corridor_end")
        _insert_ids(connection, "corridor_start", "stop_id", start_ids)
        _insert_ids(connection, "corridor_end", "stop_id", end_ids)
        _insert_ids(connection, "corridor_routes", "route_id", candidate_routes)
        rows = connection.execute(
            """
            SELECT DISTINCT route_id
            FROM (
                SELECT trips.route_id, trips.trip_id,
                    bool_or(stop_times.stop_id IN (SELECT stop_id FROM corridor_start))
                        AS has_start,
                    bool_or(stop_times.stop_id IN (SELECT stop_id FROM corridor_end)) AS has_end
                FROM trips
                JOIN stop_times USING (trip_id)
                WHERE trips.route_id IN (SELECT route_id FROM corridor_routes)
                GROUP BY trips.route_id, trips.trip_id
            )
            WHERE has_start AND has_end
            """
        ).fetchall()
        corridor_routes.update(str(row[0]) for row in rows)
        connection.execute("DROP TABLE corridor_routes")
    resolved = candidate_routes & corridor_routes
    if not resolved:
        return [], "no route contains both named corridor endpoints"
    return sorted(resolved), None


def _resolve_rules(ruleset: Ruleset, extracted_dir: Path, connection: Any) -> list[dict[str, Any]]:
    agencies = _read_csv(extracted_dir / "agency.txt")
    routes = _read_csv(extracted_dir / "routes.txt")
    stops = _read_csv(extracted_dir / "stops.txt")
    _create_view(connection, "trips", extracted_dir / "trips.txt")
    _create_view(connection, "stop_times", extracted_dir / "stop_times.txt")

    resolutions: list[dict[str, Any]] = []
    for rule in ruleset.rules:
        route_ids, reason = _resolve_rule_routes(
            rule=rule,
            agencies=agencies,
            routes=routes,
            stops=stops,
            connection=connection,
        )
        resolutions.append(
            {
                "rule_id": rule.id,
                "priority": rule.priority,
                "permission": rule.bicycle.permission,
                "status": "resolved" if route_ids else "unresolved",
                "route_ids": route_ids,
                "reason": reason,
                "condition_kinds": [condition.kind for condition in rule.bicycle.conditions],
            }
        )
    return resolutions


def _select_routes(
    resolutions: list[dict[str, Any]],
) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Choose routes that can be safely decided from static, all-date GTFS alone."""
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resolution in resolutions:
        if resolution["status"] == "resolved":
            for route_id in resolution["route_ids"]:
                by_route[str(route_id)].append(resolution)

    kept: set[str] = set()
    contradictions: list[dict[str, Any]] = []
    deferred_by_rule: dict[str, set[str]] = defaultdict(set)
    for route_id, matching in by_route.items():
        temporal_kinds = {"event_dates", "season", "time_window"}
        temporal_prohibitions = [
            item
            for item in matching
            if item["permission"] == "not_allowed" and temporal_kinds & set(item["condition_kinds"])
        ]
        if temporal_prohibitions:
            for item in temporal_prohibitions:
                deferred_by_rule[str(item["rule_id"])].add(route_id)
        static_matching = [item for item in matching if item not in temporal_prohibitions]
        if not static_matching:
            continue
        highest_priority = max(int(item["priority"]) for item in static_matching)
        highest = [item for item in static_matching if int(item["priority"]) == highest_priority]
        permissions = {str(item["permission"]) for item in highest}
        if len(permissions) != 1:
            contradictions.append(
                {
                    "route_id": route_id,
                    "priority": highest_priority,
                    "rule_ids": [item["rule_id"] for item in highest],
                    "permissions": sorted(permissions),
                }
            )
            continue
        if permissions.pop() in {"allowed", "conditional"}:
            kept.add(route_id)
    deferred = [
        {
            "rule_id": rule_id,
            "route_ids": sorted(route_ids),
            "reason": "A temporal prohibition must be applied by the router, not all-date pruning.",
        }
        for rule_id, route_ids in sorted(deferred_by_rule.items())
    ]
    return kept, contradictions, deferred


def _expand_parent_stops(stops: list[dict[str, str]], selected: set[str]) -> set[str]:
    parents = {row["stop_id"]: row.get("parent_station", "") for row in stops}
    expanded = set(selected)
    while True:
        additions = {parents[stop_id] for stop_id in expanded if parents.get(stop_id)} - expanded
        if not additions:
            return expanded
        expanded.update(additions)


def _write_pruned_feed(
    *,
    extracted_dir: Path,
    names: set[str],
    output_dir: Path,
    route_ids: set[str],
) -> tuple[dict[str, int], list[str]]:
    """Write a referentially closed subset of supported GTFS tables."""
    with duckdb.connect() as connection:
        for name in ("agency", "routes", "trips", "stop_times", "stops"):
            _create_view(connection, name, extracted_dir / f"{name}.txt")
        _insert_ids(connection, "keep_routes", "route_id", route_ids)
        route_query = "SELECT * FROM routes WHERE route_id IN (SELECT route_id FROM keep_routes)"
        trip_query = "SELECT * FROM trips WHERE route_id IN (SELECT route_id FROM keep_routes)"
        _copy_query(connection, route_query, output_dir / "routes.txt")
        _copy_query(connection, trip_query, output_dir / "trips.txt")
        trip_headers = _csv_headers(extracted_dir / "trips.txt")
        shape_expression = "shape_id" if "shape_id" in trip_headers else "NULL::VARCHAR AS shape_id"
        connection.execute(
            "CREATE TEMP TABLE keep_trips AS SELECT trip_id, service_id, "
            f"{shape_expression} FROM trips "
            "WHERE route_id IN (SELECT route_id FROM keep_routes)"
        )
        stop_time_query = (
            "SELECT * FROM stop_times WHERE trip_id IN (SELECT trip_id FROM keep_trips)"
        )
        _copy_query(connection, stop_time_query, output_dir / "stop_times.txt")
        connection.execute(
            "CREATE TEMP TABLE keep_stops AS SELECT DISTINCT stop_id FROM stop_times "
            "WHERE trip_id IN (SELECT trip_id FROM keep_trips)"
        )
        stop_rows = _read_csv(extracted_dir / "stops.txt")
        selected_stop_rows = connection.execute("SELECT stop_id FROM keep_stops").fetchall()
        selected_stops = {str(row[0]) for row in selected_stop_rows}
        expanded_stops = _expand_parent_stops(stop_rows, selected_stops)
        _insert_ids(connection, "expanded_stops", "stop_id", expanded_stops)
        stops_query = "SELECT * FROM stops WHERE stop_id IN (SELECT stop_id FROM expanded_stops)"
        _copy_query(connection, stops_query, output_dir / "stops.txt")
        connection.execute(
            "CREATE TEMP TABLE keep_agencies AS SELECT DISTINCT agency_id FROM routes "
            "WHERE route_id IN (SELECT route_id FROM keep_routes)"
        )
        agency_query = (
            "SELECT * FROM agency WHERE agency_id IN (SELECT agency_id FROM keep_agencies)"
        )
        _copy_query(connection, agency_query, output_dir / "agency.txt")

        counts = {
            "agency.txt": _count_query(connection, "SELECT count(*) FROM keep_agencies"),
            "routes.txt": _count_query(connection, "SELECT count(*) FROM keep_routes"),
            "trips.txt": _count_query(connection, "SELECT count(*) FROM keep_trips"),
            "stop_times.txt": _count_query(connection, f"SELECT count(*) FROM ({stop_time_query})"),
            "stops.txt": _count_query(connection, "SELECT count(*) FROM expanded_stops"),
        }

        transfer_conditions = [
            "from_stop_id IN (SELECT stop_id FROM expanded_stops)",
            "to_stop_id IN (SELECT stop_id FROM expanded_stops)",
        ]
        if "transfers.txt" in names:
            transfer_headers = set(_csv_headers(extracted_dir / "transfers.txt"))
            for trip_field in ("from_trip_id", "to_trip_id"):
                if trip_field in transfer_headers:
                    transfer_conditions.append(
                        f"({trip_field} IS NULL OR {trip_field} = '' OR {trip_field} IN "
                        "(SELECT trip_id FROM keep_trips))"
                    )
        transfers_query = "SELECT * FROM transfers WHERE " + " AND ".join(transfer_conditions)

        optional_queries = {
            "calendar.txt": (
                "SELECT * FROM calendar WHERE service_id IN (SELECT service_id FROM keep_trips)"
            ),
            "calendar_dates.txt": (
                "SELECT * FROM calendar_dates WHERE service_id IN "
                "(SELECT service_id FROM keep_trips)"
            ),
            "frequencies.txt": (
                "SELECT * FROM frequencies WHERE trip_id IN (SELECT trip_id FROM keep_trips)"
            ),
            "shapes.txt": (
                "SELECT * FROM shapes WHERE shape_id IN ("
                "SELECT shape_id FROM keep_trips WHERE shape_id IS NOT NULL AND shape_id != '')"
            ),
            "transfers.txt": transfers_query,
            "pathways.txt": (
                "SELECT * FROM pathways WHERE from_stop_id IN (SELECT stop_id FROM expanded_stops) "
                "AND to_stop_id IN (SELECT stop_id FROM expanded_stops)"
            ),
        }
        for filename, query in optional_queries.items():
            if filename in names:
                _create_view(connection, filename.removesuffix(".txt"), extracted_dir / filename)
                counts[filename] = _copy_query(connection, query, output_dir / filename)
    copied = ["feed_info.txt", "levels.txt"]
    for filename in copied:
        if filename in names:
            shutil.copyfile(extracted_dir / filename, output_dir / filename)
    dropped = sorted(names - set(counts) - set(copied))
    return counts, dropped


def _write_deterministic_zip(source_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=archive_path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    with zipfile.ZipFile(
        temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(source_dir.glob("*.txt")):
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    temporary_path.replace(archive_path)


def _write_route_metadata(feed_dir: Path, output_path: Path) -> None:
    """Export agency and service labels keyed by Minotor's route-short-name field."""
    agencies = {
        row["agency_id"]: row["agency_name"]
        for row in _read_csv(feed_dir / "agency.txt")
    }
    by_short_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in _read_csv(feed_dir / "routes.txt"):
        short_name = row.get("route_short_name", "").strip()
        if not short_name:
            continue
        agency = agencies.get(row.get("agency_id", ""), "Unknown operator")
        service = row.get("route_long_name", "").strip()
        by_short_name[short_name].add((agency, service))
    _atomic_write_json(
        output_path,
        {
            "by_short_name": {
                short_name: [
                    {"agency": agency, "service": service}
                    for agency, service in sorted(candidates)
                ]
                for short_name, candidates in sorted(by_short_name.items())
            }
        },
    )


def build_gtfs(
    *,
    rules_path: Path = Path("rules/bike-rules.yaml"),
    source_dir: Path = Path("data/source"),
    output_dir: Path = Path("data/generated/gtfs"),
    url: str = DEFAULT_GTFS_URL,
    source_archive: Path | None = None,
) -> GtfsBuildResult:
    """Download GTFS Sverige 2 and emit the subset explicitly allowed by resolved rules."""
    ruleset = load_ruleset(rules_path)
    if source_archive is None:
        settings = GtfsSettings()
        if settings.trafiklab_gtfs_api_key is None:
            raise GtfsError("TRAFIKLAB_GTFS_API_KEY is not set; add it to .env or the environment.")
        archive_bytes, headers = _download_gtfs(url, settings.trafiklab_gtfs_api_key)
        source_path = source_dir / "gtfs-sweden-2.zip"
        _atomic_write_bytes(source_path, archive_bytes)
    else:
        try:
            archive_bytes = source_archive.read_bytes()
        except OSError as error:
            raise GtfsError(
                f"Could not read local GTFS archive {source_archive}: {error}"
            ) from error
        headers = {}
        source_path = source_archive
    source_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    with TemporaryDirectory(prefix="cykelpatag-gtfs-") as temporary_name:
        temporary_dir = Path(temporary_name)
        extracted_dir = temporary_dir / "source"
        extracted_dir.mkdir()
        names = _extract_zip_safely(archive_bytes, extracted_dir)
        with duckdb.connect() as connection:
            resolutions = _resolve_rules(ruleset, extracted_dir, connection)
        route_ids, contradictions, deferred = _select_routes(resolutions)
        feed_dir = temporary_dir / "bike-gtfs"
        feed_dir.mkdir()
        counts, dropped_files = _write_pruned_feed(
            extracted_dir=extracted_dir,
            names=names,
            output_dir=feed_dir,
            route_ids=route_ids,
        )
        archive_path = output_dir / "bike.gtfs.zip"
        _write_deterministic_zip(feed_dir, archive_path)
        _write_route_metadata(feed_dir, output_dir / "route-metadata.json")

    resolved = [item for item in resolutions if item["status"] == "resolved"]
    unresolved = [item for item in resolutions if item["status"] != "resolved"]
    resolution_path = output_dir / "rules-resolved.json"
    manifest_path = output_dir / "manifest.json"
    _atomic_write_json(
        resolution_path,
        {
            "ruleset_source": ruleset.source.model_dump(mode="json"),
            "resolved": resolved,
            "unresolved": unresolved,
            "contradictions": contradictions,
            "deferred_from_static_pruning": deferred,
        },
    )
    _atomic_write_json(
        manifest_path,
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_url": url,
            "source_sha256": source_sha256,
            "source_bytes": len(archive_bytes),
            "source_etag": headers.get("etag"),
            "ruleset_path": str(rules_path),
            "ruleset_sha256": hashlib.sha256(rules_path.read_bytes()).hexdigest(),
            "kept_route_count": len(route_ids),
            "kept_trip_count": counts["trips.txt"],
            "table_row_counts": counts,
            "dropped_source_files": dropped_files,
        },
    )
    return GtfsBuildResult(
        source_path=source_path,
        archive_path=archive_path,
        manifest_path=manifest_path,
        resolution_path=resolution_path,
        kept_trip_count=counts["trips.txt"],
        resolved_rule_count=len(resolved),
        unresolved_rule_count=len(unresolved),
    )
