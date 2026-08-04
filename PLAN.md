# Implementation plan

## Goal

Build a low-cost Swedish journey planner that searches only public-transport services compatible
with an assembled bicycle and explains fees, reservations, packing requirements, capacity limits,
and other conditions.

The architecture has three products:

1. a reviewed structured policy dataset derived from Naturskyddsföreningen's guide;
2. a valid, all-dates GTFS subset plus compact browser routing artifacts;
3. a lightweight static web application that plans and explains bicycle-compatible journeys.

## Guiding decisions

- Include bicycle-compatible trains, buses, and ferries; do not assume rail-only eligibility.
- Use GTFS Sverige 2 for the first complete national timetable.
- Treat curated guide rules as authoritative and GTFS bicycle metadata as supporting evidence.
- Maintain one canonical all-dates GTFS; introduce client chunks only after measuring mobile limits.
- Run conversion and pruning in scheduled CI rather than a permanent application server.
- Route in a Web Worker and keep the main interface responsive.
- Publish no inferred policy rule without review and a traceable source.

## Milestone 0 — Project skeleton

Status: complete.

- Create a Python 3.12 project managed with uv.
- Create a Vite and TypeScript npm project under `frontend/`.
- Add local and example environment files containing `TRAFIKLAB_API_KEY` configuration.
- Add baseline Python and frontend CI checks.
- Add source and generated-data directories without committing downloaded material.
- Document the research and implementation sequence.

No guide conversion or GTFS pruning code belongs in this milestone.

## Milestone 1 — Convert the guide to Markdown

Status: not started.

1. Download or place the current guide PDF in `data/source/`.
2. Record its URL, publication date, retrieval time, and checksum.
3. Add a Python command that invokes LiteParse exactly once to extract the born-digital PDF to an
   intermediate text file, normally using `--no-ocr`.
4. Convert that intermediate text deterministically into readable Markdown, preserving headings,
   operator sections, lists, tables, page references where available, and original wording.
5. Accept an already extracted `.txt` source as an input so repeated LiteParse work is unnecessary.
6. Test stable output using small fixtures and golden files.

Expected outputs:

```text
data/generated/guide.md
data/generated/guide-source.json
```

Stop for a manual Markdown review before extracting rules.

## Milestone 2 — Convert Markdown into reviewed rules

Status: not started.

1. Define a versioned Pydantic schema for operators, modes, routes, stop corridors, direction,
   dates, fees, reservations, capacity, packing, exceptions, and evidence.
2. Parse the guide Markdown into draft rules while retaining source sections and excerpts.
3. Generate a review report for ambiguous statements and rules without stable selectors.
4. Add a manually maintained override file for corrections that cannot be derived safely.
5. Validate enums, date ranges, rule priority, overlapping selectors, and source attribution.
6. Require explicit review state before a rule can affect the published feed.

Expected outputs:

```text
data/generated/bike-rules.json
data/generated/rule-review.md
```

## Milestone 3 — Download and prune GTFS Sverige 2

Status: not started.

1. Add a downloader that reads `TRAFIKLAB_API_KEY` from the environment and never logs it.
2. Use `HEAD`, ETag, Last-Modified, feed version, or checksum information to avoid unchanged builds.
3. Download GTFS Sverige 2 into temporary storage.
4. Load relevant tables with DuckDB.
5. Resolve reviewed policy selectors against current agencies, routes, stops, services, and trips.
6. Keep all bicycle-compatible services, including selected buses and ferries.
7. Preserve referential closure across required and supported optional GTFS tables.
8. Preserve the complete useful calendar horizon, including services needed after midnight.
9. Emit unmatched, ambiguous, contradictory, and unexpectedly changed rule reports.
10. Produce a deterministic all-dates `bike.gtfs.zip`, rules JSON, and manifest.

The pruning code must not interpret missing GTFS bicycle metadata as prohibition.

## Milestone 4 — Automate rebuilding and validate GTFS

Status: not started.

1. Add a scheduled GitHub Action that checks for new source data daily.
2. Rebuild only when the GTFS feed, guide rules, or pipeline version changes.
3. Run unit and integration tests before publishing artifacts.
4. Run an established GTFS validator plus project-specific referential and policy checks.
5. Reject publication on GTFS errors, unresolved approved rules, empty critical corridors, or
   implausible size changes.
6. Retain manifests and validation reports for diagnosis and reproducibility.
7. Upload versioned build artifacts or publish them to static hosting.

Secrets will be supplied through GitHub Actions secrets as `TRAFIKLAB_API_KEY`; `.env` remains local.

## Milestone 5 — Test browser-based RAPTOR in real conditions

Status: not started.

1. Compile the validated feed using Minotor first.
2. Run routing in a Web Worker and load artifacts from static hosting.
3. Test representative daytime, mixed-mode, Kalmar–Öland bus, through-midnight, and
   after-midnight-transfer journeys.
4. Compare results against the canonical pruned GTFS and selected manual itineraries.
5. Measure compressed size, initial load, parse time, query latency, peak memory, and cache behaviour
   on desktop and low- to mid-range mobile devices.
6. Verify searches over service days D and D+1, times above 24:00, and `Europe/Stockholm` daylight
   saving transitions.
7. Test one all-date artifact first. If it exceeds agreed mobile budgets, compare daily artifacts
   with overlap, rolling date windows, or geographic chunks.
8. If Minotor cannot meet requirements, test `gtfs-sqljs-raptor`, direct planarnetwork RAPTOR with
   custom serialization, and finally a small hosted router.

Initial acceptance targets should be agreed from prototype measurements; candidate targets are less
than 10 MB compressed initial timetable data, less than 50 MB steady-state browser memory, and
sub-second warm queries on a representative mobile phone.

## Milestone 6 — Deploy the routing proof of concept

Status: not started.

1. Deploy the static artifact and minimal browser router to a preview environment.
2. Configure immutable versioned asset caching and a small mutable manifest.
3. Add error reporting that contains no API key or journey-sensitive personal data.
4. Publish Trafiklab attribution and data freshness information.
5. Confirm that no proxy or persistent backend is necessary; add one only for a measured need.

## Milestone 7 — Build the lightweight planner

Status: not started.

1. Add accessible origin, destination, departure/arrival time, and date controls.
2. Plan journeys entirely from the bicycle-compatible routing artifact.
3. Present several useful alternatives with transfers, duration, operating companies, and bicycle
   compatibility clearly visible.
4. Explain every matched policy condition: fees, booking, capacity, packing, seasonal rules, and
   uncertainty.
5. Link explanations to their guide/operator source and show the timetable/rule freshness date.
6. Handle no-route and unknown-policy cases honestly rather than silently widening eligibility.
7. Make the application installable and cache routing data for repeat/offline use where feasible.

## Milestone 8 — Optimise search and policy presentation

Status: not started.

1. Build a compact normalized stop index from the pruned GTFS.
2. Add fast, typo-tolerant Swedish place and stop autocompletion without external requests.
3. Support parent stations, nearby stops, municipalities, aliases, and diacritics.
4. Lazy-load timetable or policy chunks only if measurements demonstrate a benefit.
5. Precompute indexes and typed/binary structures in CI rather than on the phone.
6. Refine ranking so practical journeys are preferred without hiding slower valid alternatives.
7. Add concise policy badges with expandable full conditions from the structured guide rules.
8. Re-run mobile performance, accessibility, overnight, and regression tests before production.

## Definition of a successful first release

- A user can select Swedish origins, destinations, and a date/time on a mobile phone.
- Results use only services approved for an assembled bicycle by reviewed rules.
- Eligible buses and ferries are included alongside trains.
- Overnight journeys and transfers across service days work.
- Every restriction is explained and sourced.
- The timetable and policy version are visible.
- The system rebuilds reproducibly in free CI and the deployed planner needs no heavyweight server.
