import csv
from pathlib import Path
from typing import Any

import duckdb

from cykelpatag.gtfs import _resolve_rules, _select_routes, _write_pruned_feed
from cykelpatag.rules import Ruleset


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture_gtfs(directory: Path) -> set[str]:
    _write_csv(
        directory / "agency.txt",
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        [
            {
                "agency_id": "agency",
                "agency_name": "Cycle Rail",
                "agency_url": "https://example.invalid",
                "agency_timezone": "Europe/Stockholm",
            }
        ],
    )
    _write_csv(
        directory / "routes.txt",
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        [
            {
                "route_id": "route",
                "agency_id": "agency",
                "route_short_name": "Line 1",
                "route_long_name": "Alpha–Beta",
                "route_type": "106",
            }
        ],
    )
    _write_csv(
        directory / "trips.txt",
        ["route_id", "service_id", "trip_id"],
        [{"route_id": "route", "service_id": "weekday", "trip_id": "trip"}],
    )
    _write_csv(
        directory / "stop_times.txt",
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        [
            {
                "trip_id": "trip",
                "arrival_time": "08:00:00",
                "departure_time": "08:00:00",
                "stop_id": "alpha",
                "stop_sequence": "1",
            },
            {
                "trip_id": "trip",
                "arrival_time": "08:30:00",
                "departure_time": "08:30:00",
                "stop_id": "beta",
                "stop_sequence": "2",
            },
        ],
    )
    _write_csv(
        directory / "stops.txt",
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "parent_station"],
        [
            {
                "stop_id": "station",
                "stop_name": "Alpha station",
                "stop_lat": "1",
                "stop_lon": "1",
                "parent_station": "",
            },
            {
                "stop_id": "alpha",
                "stop_name": "Alpha",
                "stop_lat": "1",
                "stop_lon": "1",
                "parent_station": "station",
            },
            {
                "stop_id": "beta",
                "stop_name": "Beta",
                "stop_lat": "1",
                "stop_lon": "1",
                "parent_station": "",
            },
        ],
    )
    _write_csv(
        directory / "calendar.txt",
        [
            "service_id",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "start_date",
            "end_date",
        ],
        [
            {
                "service_id": "weekday",
                "monday": "1",
                "tuesday": "1",
                "wednesday": "1",
                "thursday": "1",
                "friday": "1",
                "saturday": "0",
                "sunday": "0",
                "start_date": "20260101",
                "end_date": "20261231",
            }
        ],
    )
    return {"agency.txt", "routes.txt", "trips.txt", "stop_times.txt", "stops.txt", "calendar.txt"}


def _ruleset() -> Ruleset:
    source: dict[str, Any] = {
        "name": "Test guide",
        "edition": "test",
        "url": "https://example.invalid/guide.pdf",
        "sha256": "0" * 64,
    }
    match = {"modes": ["rail"], "agencies": ["Cycle Rail"], "services": ["Line 1"]}
    bicycle = {
        "bike_booking": "unknown",
        "ticket_purchase": "unknown",
        "fare": {"kind": "free"},
        "capacity": {"kind": "unspecified"},
    }
    return Ruleset.model_validate(
        {
            "schema_version": 1,
            "source": source,
            "rules": [
                {
                    "id": "allowed",
                    "priority": 100,
                    "match": match,
                    "bicycle": bicycle | {"permission": "allowed"},
                    "evidence": [{"page": 1, "locator": "allowed"}],
                },
                {
                    "id": "exception",
                    "priority": 200,
                    "match": match,
                    "bicycle": bicycle | {"permission": "not_allowed"},
                    "evidence": [{"page": 1, "locator": "exception"}],
                },
            ],
        }
    )


def test_higher_priority_prohibition_overrides_an_allowed_route(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    names = _fixture_gtfs(source)
    with duckdb.connect() as connection:
        resolutions = _resolve_rules(_ruleset(), source, connection)

    kept_routes, contradictions, deferred = _select_routes(resolutions)

    assert {item["status"] for item in resolutions} == {"resolved"}
    assert kept_routes == set()
    assert contradictions == []
    assert deferred == []

    output = tmp_path / "output"
    counts, dropped = _write_pruned_feed(
        extracted_dir=source,
        names=names,
        output_dir=output,
        route_ids=kept_routes,
    )

    assert counts["trips.txt"] == 0
    assert (output / "calendar.txt").read_text(encoding="utf-8").count("weekday") == 0
    assert dropped == []


def test_temporal_prohibition_is_deferred_from_all_date_pruning() -> None:
    resolutions: list[dict[str, Any]] = [
        {
            "rule_id": "allowed",
            "priority": 100,
            "permission": "allowed",
            "status": "resolved",
            "route_ids": ["route"],
            "condition_kinds": [],
        },
        {
            "rule_id": "event-exception",
            "priority": 200,
            "permission": "not_allowed",
            "status": "resolved",
            "route_ids": ["route"],
            "condition_kinds": ["event_dates"],
        },
    ]

    kept_routes, contradictions, deferred = _select_routes(resolutions)

    assert kept_routes == {"route"}
    assert contradictions == []
    assert deferred == [
        {
            "rule_id": "event-exception",
            "route_ids": ["route"],
            "reason": "A temporal prohibition must be applied by the router, not all-date pruning.",
        }
    ]


def test_pruning_drops_transfers_referencing_removed_trips(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    names = _fixture_gtfs(source)
    _write_csv(
        source / "transfers.txt",
        ["from_stop_id", "to_stop_id", "transfer_type", "from_trip_id", "to_trip_id"],
        [
            {
                "from_stop_id": "alpha",
                "to_stop_id": "beta",
                "transfer_type": "0",
                "from_trip_id": "trip",
                "to_trip_id": "trip",
            },
            {
                "from_stop_id": "alpha",
                "to_stop_id": "beta",
                "transfer_type": "0",
                "from_trip_id": "removed-trip",
                "to_trip_id": "trip",
            },
        ],
    )
    names.add("transfers.txt")

    output = tmp_path / "output"
    counts, _ = _write_pruned_feed(
        extracted_dir=source,
        names=names,
        output_dir=output,
        route_ids={"route"},
    )

    assert counts["transfers.txt"] == 1
    transfers = list(csv.DictReader((output / "transfers.txt").open(encoding="utf-8")))
    assert transfers == [
        {
            "from_stop_id": "alpha",
            "to_stop_id": "beta",
            "transfer_type": "0",
            "from_trip_id": "trip",
            "to_trip_id": "trip",
        }
    ]


def test_exact_reviewed_agency_alias_resolves_a_rule(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _fixture_gtfs(source)
    ruleset = _ruleset().model_copy(
        update={
            "rules": [
                _ruleset()
                .rules[0]
                .model_copy(
                    update={
                        "match": _ruleset()
                        .rules[0]
                        .match.model_copy(
                            update={
                                "agencies": ["Guide spelling"],
                                "agency_aliases": ["Cycle Rail"],
                            }
                        )
                    }
                )
            ]
        }
    )

    with duckdb.connect() as connection:
        resolutions = _resolve_rules(ruleset, source, connection)

    assert resolutions[0]["status"] == "resolved"
