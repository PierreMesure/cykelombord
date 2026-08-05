# Research

## Problem and constraints

Swedish journey planners do not reliably answer the question "Can I take an assembled bicycle on
this complete journey?" Bicycle policy is distributed across many operators and can differ by
line, vehicle, season, departure, capacity, reservation requirement, and replacement service.

The intended project is deliberately small:

- no permanently running heavyweight routing server;
- a static frontend or very small proxy if one becomes unavoidable;
- processing that can run in free scheduled CI;
- useful performance on ordinary mobile phones;
- transparent, sourced explanations for bicycle conditions.

The eligible network is not rail-only. It includes every service that accepts bicycles, including
specific buses such as Kalmar–Öland services and relevant ferries.

## Sources of truth

### Naturskyddsföreningen guide

The guide is the best available policy overview and is more complete than timetable bicycle
metadata. It should be converted to Markdown and then into reviewed structured rules. The original
text remains important as evidence: generated rules must retain their source section, source URL,
retrieval date, and a human-readable explanation.

The rules are an overlay, not timetable data. Routing rules need selectors for operator, transport
mode, route or corridor, stops, direction, calendar period, and exceptional trips. Capacity belongs
on the matching rule, including a range when it varies by rolling stock. Separate display advisories
hold recurring events and service-specific operational warnings, such as a train with no usable bike
space.
Outcomes should distinguish at least:

- assembled bicycle allowed;
- allowed with a fee;
- reservation required;
- limited spaces or first-come-first-served;
- only a packed or disassembled bicycle allowed;
- not allowed;
- unknown or requiring confirmation.

Extraction can accelerate transcription, but rules should not be published without human review.
Natural-language policy contains exceptions that cannot safely be inferred from headings alone.

### PDF-to-Markdown conversion

LiteParse was initially evaluated because it is compact and exposes text coordinates. On the 2026
guide it interleaved two-column prose and, more seriously, flattened the regional-policy table by
visual column rather than by row. Its raw coordinates were intact, but its generic Markdown renderer
was not safe as a policy source.

PyMuPDF4LLM 1.28.0 was tested on the same PDF. Its layout-aware renderer preserved the left-to-right
reading order and produced the regional policy as a four-column Markdown table with correctly aligned
Skåne, Småland/Krösatåg, Mälardalen, and Inlandsbanan rows. It is selected as an optional `guide`
dependency. The stack is substantially larger because it includes the PyMuPDF layout engine and ONNX
runtime, but it runs only during occasional guide updates, never in the GTFS or browser pipelines.
PyMuPDF and PyMuPDF4LLM are AGPL v3 or commercially licensed, so the project's eventual distribution
licence must be compatible.

A minimal normalizer joins an incomplete lower-case continuation left at a column boundary. The PDF,
generated Markdown, checksum, and source URL remain review inputs; structured rules still require
human approval.

### Ruleset representation

YAML is the canonical ruleset format because policy reviewers can read it directly in GitHub, retain
short explanatory notes, and make narrow edits without rewriting a generated artifact. A strict
Pydantic schema rejects unknown keys and inconsistent values. The checked-in source carries a PDF
edition, URL, checksum, page number, and heading locator for every policy. A later GTFS build should
resolve its human-readable selectors to feed identifiers and compile the result to JSON for routing;
that JSON is a build artifact, not an authoring format.

### GTFS bicycle metadata

GTFS provides `bikes_allowed` at trip level and `bikes_allowed`/`bikes_allowed`-related extensions
may appear in particular feeds, but Swedish coverage is inconsistent. Earlier live sampling found
explicit bicycle information for some Mälartåg journeys while sampled services from other operators
did not expose equivalent detail. Missing metadata must mean "unknown," not "forbidden."

Consequently, GTFS metadata is supporting evidence. The curated rules remain authoritative when a
rule matches, and conflicts should be reported during the build rather than silently resolved.

## API and data options considered

### ResRobot journey-planner API

ResRobot is attractive because it needs only a small frontend or proxy. It was tested with the
free-tier key and can filter broad products and operators. It cannot express the required
operator-plus-line-plus-policy constraints, however, and returns only a small selection of journey
alternatives. Filtering those results afterwards can discard all useful answers even when a more
unusual bicycle-compatible itinerary exists.

Conclusion: useful for comparison tests and possibly fallback links, but not the primary search
engine.

### GTFS Sverige 2

GTFS Sverige 2 supplies a nationwide static and historical timetable. It also shares stop IDs with
ResRobot, which is useful for comparison and stop lookup. Trafiklab's current API overview still
describes it as containing all scheduled public transport, without realtime data:
[Trafiklab API overview](https://www.trafiklab.se/api/) and
[combining Trafiklab data](https://www.trafiklab.se/docs/using-trafiklab-data/combining-data/).

The inspected national archive was approximately 71 MB compressed and 675 MB expanded, with about
12.7 million stop-time rows, 587,000 trips, and 48,000 stops. These are manageable batch-processing
sizes. A rail-only experiment reduced the timetable to roughly 28,000 trips and 314,000 stop times;
the real subset will be somewhat larger because eligible buses and ferries must also remain.

Advantages:

- national coverage and one coherent feed;
- enough calendar data for all-date and overnight routing;
- simple daily download and deterministic pruning;
- manageable in short-lived CI with DuckDB.

Limitations:

- less detailed than newer regional sources;
- no realtime data;
- bicycle fields cannot be trusted as complete;
- all downstream files must retain valid GTFS references when pruned.

The first live pruning run also showed why a reviewed resolution layer is necessary: GTFS Sverige 2
uses extended `route_type` values such as `101`, `102`, and `106` for rail, often stores a train
number in `route_short_name`, and leaves `route_long_name` empty. Some guide/operator spellings also
differ, for example `Värmlandstrafiken` versus the feed's `Värmlandstrafik`. Exact reviewed aliases
can handle the latter, but train model, service brand, and route-corridor distinctions must remain
unresolved until a deterministic mapping is available.

Conclusion: selected for the first implementation because completeness matters more than maximum
detail for this use case.

### GTFS Sweden 3 and regional feeds

GTFS Sweden 3 is described as higher quality and is designed to combine detailed regional feeds,
with associated realtime datasets. The static endpoint documentation currently says it contains
"most" Swedish public transport rather than guaranteeing complete national coverage:
[GTFS Sweden 3 static specification](https://www.trafiklab.se/api/gtfs-datasets/gtfs-sweden/static-specification/).

This is a strong future source, especially for realtime overlays and richer booking information.
It was not selected initially because a bicycle planner must not lose uncovered operators. The
importer should nevertheless be feed-agnostic enough to evaluate or migrate to GTFS Sweden 3 when
coverage is verified.

### Direct operator feeds

Regional GTFS and GTFS-RT feeds provide greater detail and are updated daily, generally between
03:00 and 07:00. They also multiply identifier reconciliation, download, coverage, and operational
work: [Trafiklab GTFS Regional](https://www.trafiklab.se/api/gtfs-datasets/gtfs-regional).

Conclusion: valuable later for realtime enhancement or targeted gaps, but too complex for the
first small-project version.

### Server-side routers

OpenTripPlanner and similar established engines could route the national feed and support bicycle
access modelling, but require a continuously hosted JVM or comparable service and a built graph.
That conflicts with the desired static/mobile-first operating model.

Conclusion: technically robust fallback if browser routing fails, not the preferred deployment.

## Can a national GTFS be pruned?

Yes. A subset remains functional if referential closure is preserved. Starting from eligible
`trip_id` values, the build must retain corresponding rows in `stop_times.txt`, `trips.txt`,
`routes.txt`, `agency.txt`, and used `stops.txt`; retain the referenced services in `calendar.txt`
and `calendar_dates.txt`; and consistently retain or rewrite optional relationships such as shapes,
transfers, pathways, fare data, and parent stations.

The build should produce one canonical, all-dates `bike.gtfs.zip`. GTFS calendars avoid duplicating
the same trip for every date, so an all-dates feed need not be large. Device-specific date or region
chunks can be generated later without changing the canonical model.

Pruning routes purely by operator or transport type is insufficient. Eligibility can vary within
one operator and one route. Rules should be resolved to trips for each feed version, with unmatched
and ambiguous rules causing visible validation findings.

## Refresh frequency and resource cost

A daily scheduled check is appropriate. Conditional HTTP requests or feed version checks should
avoid downloading and rebuilding unchanged data. A changed national feed can reasonably be
downloaded, expanded, filtered with DuckDB, validated, and compiled in a few minutes on a normal CI
runner. It needs temporary disk and memory, not a permanent server.

The policy guide changes much less frequently. A new guide or manual rule correction should trigger
the same build independently of timetable updates. Realtime disruption data should eventually be
overlaid at query time rather than forcing repeated static rebuilds.

## Calendar and overnight routing

GTFS represents service after midnight with times greater than `24:00:00`; for example, an arrival
at 01:15 after a 22:30 departure may be `25:15:00`. This is part of the official
[GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/).

A router must search both the departure service day and the next service day. A through vehicle can
remain attached to day D with times above 24 hours, while a transfer after midnight may board a
service activated on D+1. Internally, routing should use a service date plus seconds from service-day
midnight, apply the `Europe/Stockholm` timezone correctly, and initially cap searches at 36 or 48
hours.

This is an argument for preserving all dates in the canonical feed and, if practical, in the
browser artifact.

## Browser routing options considered

### Minotor

[Minotor](https://www.minotor.dev/) is an active open-source RAPTOR-derived router for browsers,
Node.js, and React Native. Its Node-side parser emits compact protobuf timetable and stop-index
files, and its demo runs routing in a Web Worker. It is the most promising first experiment.

Its current normal workflow compiles one service date at a time and officially tests Swiss data.
Overnight journeys therefore require two day artifacts or deliberate overlap, and Swedish GTFS
compatibility needs testing.

### gtfs-sqljs-raptor

[gtfs-sqljs-raptor](https://jspm-packages.deno.dev/package/gtfs-sqljs-raptor%400.2.0) bridges an
in-browser SQLite GTFS loader to `raptor-journey-planner`. It is naturally browser-oriented and can
retain calendar-aware data, but is young, likely has a larger memory footprint, and inherits licence
and maintenance considerations from its dependencies.

Conclusion: useful comparison implementation if Minotor's daily artifact model is too restrictive.

### planarnetwork RAPTOR

[planarnetwork/raptor](https://github.com/planarnetwork/raptor) provides a direct RAPTOR
implementation with calendar and range-query concepts. Its loading path is Node-oriented, so a
custom browser serialization and worker layer would be required.

Conclusion: more engineering, but a possible foundation for a single all-date browser artifact.

### Planner.js and Linked Connections

[Planner.js](https://github.com/openplannerteam/planner.js) can perform client-side planning over
Linked Connections fragments. It avoids loading an entire timetable, but requires publishing and
serving a transformed connection stream and makes offline/mobile caching more involved.

Conclusion: a credible serverless-web architecture, but more infrastructure than a compact static
RAPTOR artifact for the first version.

## Selected direction

The first implementation will use GTFS Sverige 2 plus reviewed Naturskyddsföreningen rules to build
one valid, all-dates bicycle-compatible GTFS. CI will rebuild only when inputs change. Minotor will
be tested first in a real mobile browser using generated artifacts and a Web Worker. The decision
to use one all-date browser artifact or generated date chunks will be made from measured download,
parse, memory, and overnight-routing behaviour rather than assumed in advance.

## Principal risks and measurements

- Rule matching may be ambiguous as operator and route names change between guide editions and
  feed versions.
- A service advertised as bicycle-compatible may have inaccessible replacement buses or vehicle
  substitutions.
- Removing non-bicycle services may eliminate transfers needed to reach a bicycle-compatible
  service; walking and cycling access legs must be modelled separately.
- Minotor may require Swedish-feed adaptations or date chunking.
- Browser memory, not compressed download size, is likely the decisive mobile constraint.
- Static GTFS cannot promise realtime bicycle capacity or vehicle assignment.

The prototype must therefore record unmatched rules, validate GTFS references, compare known
journeys with operator information, and benchmark low- to mid-range mobile hardware before a public
deployment decision.
