# Cykel ombord

![Cykel ombord's logo](./frontend/public/logo.webp)

[Cykel ombord](https://cykelombord.mesu.re) is a Swedish public transport route planner selecting only routes where you can take your bike with you without folding it. It combines Trafiklab's timetable data ([GTFS-2 feed](https://www.trafiklab.se/api/gtfs-datasets/gtfs-sverige-2)) with structured rules derived from
Naturskyddsföreningen's guide [Cykel på tåg](https://lund.naturskyddsforeningen.se/cykling/cykel-pa-tag/).

Cykel ombord is a static website and uses client-side route planning. When the user requests a route, it downloads a daily portion of the timetable and resolves the itinerary locally without speaking further to any server.

The website is hosted at [statichost.eu](https://www.statichost.eu) and anonymous and aggregated web traffic data is collected by the privacy-friendly service [GoatCounter](https://www.goatcounter.com).

## Repository layout

```text
.
├── data/
│   ├── source/       # Local source guide and downloaded GTFS (gitignored)
│   └── generated/    # Generated Markdown, rules, and routing data (gitignored)
├── frontend/         # Vite and TypeScript web application
├── rules/            # Reviewed, human-authored bicycle policy rules
├── src/cykelombord/  # Python data-pipeline package
├── tests/            # Python tests
├── PLAN.md          # Chosen implementation plan
└── RESEARCH.md      # Research findings and alternatives
```

## Local setup

Prerequisites are [uv](https://docs.astral.sh/uv/) with Python 3.12 or later, Node.js 24, and npm.

### Download the bicycle guide

The command below fetches the PDF guide from Naturskyddsföreningen, and converts it to Markdown.

```bash
uv sync --extra guide
uv run cykelombord guide update
```

It writes the downloaded PDF to `data/source/cykel-pa-tag.pdf` and these generated review inputs:

```text
data/generated/guide.md
data/generated/guide-source.json
```

### Convert the guide to structured bicycle rules

In order to use the guide's rules in the app, we convert them  using a large language model to a structured list with predictable fields in [`rules/bike-rules.yaml`](rules/bike-rules.yaml). This file contains only facts explicitly stated by the June 2026 guide and links each rule back to a page and heading. The build will later resolve these human-facing names against a specific GTFS feed and compile the validated result to JSON for the web app.

Most information is kept either as a strict rule (this service DOES accept bikes) or a complementary note (NOT during Vätternrundan, 2-6 bikes per carriage) that can be displayed to the user but doesn't impact the routing.

The schema and repeatable extraction instructions are in [`RULES_SPEC.md`](RULES_SPEC.md). Validate
the checked-in ruleset with:

```bash
uv run cykelombord rules validate
```

### Prune the national GTFS-2 feed to a bike-allowed subset of services and routes

To download GTFS from Trafiklab, you will need an API key which you can set in `.env`:

```bash
cp .env.example .env
```

```dotenv
TRAFIKLAB_GTFS_API_KEY=...
```

You can then run this command that will download the file and use the rules generated above to remove any journey that is not considered to allow bikes:

```bash
uv run cykelombord gtfs build
```

To re-run the pruner against an already downloaded archive without consuming an API request:

```bash
uv run cykelombord gtfs build --source-archive data/source/gtfs-sweden-2.zip
```

### Validate the pruned GTFS file

To validate the bike-only GTFS file, we use a new package called `gtfs-guru`. Install it with uv then run:

```bash
uv sync --extra gtfs-validation
cykelombord gtfs validate
```

### Compile daily timetable binaries for client-side routing

```bash
uv run cykelombord router build --days 90
```

In order to run GTFS download, pruning, validation and daily binary generation in one go, you can just run:

```bash
uv run cykelombord pipeline update --days 90
```

Pass `--start-date YYYY-MM-DD` to `router build` or `pipeline update` for a reproducible range.

## Code quality and tests

Run the current skeleton checks with:

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix frontend run build
```

## Data and attribution

Generated artifacts are published daily using a Github Action and Github Pages at [cdn.cykelombord.mesu.re](https://cdn.cykelombord.mesu.re). They are downloaded by the website when a user requests a route on a certain date.

Trafiklab's license on the original GTFS feed is CC0. I am reusing this license for the data this project produces (for example [bike.gtfs.zip](https://cdn.cykelombord.mesu.re/bike.gtfs.zip)) but since its quality cannot be guaranteed, I strongly recommend that you link back to this project and inform about its experimental nature.
