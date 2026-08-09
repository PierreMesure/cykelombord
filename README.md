# Cykel ombord

Cykel ombord aims to plan Swedish public-transport journeys on which a traveller can bring an
assembled bicycle. It will combine Trafiklab timetable data with structured rules derived from
Naturskyddsföreningen's regularly updated guide.

The guide downloader, PDF-to-Markdown conversion, first source-extracted YAML ruleset, GTFS 2
pruner, and a small browser-only routing prototype are implemented. The prototype is for
validation and exploration, not publication yet.

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

Prerequisites are Python 3.12 or later, [uv](https://docs.astral.sh/uv/), Node.js 24, and npm. The optional
`guide` extra installs [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) only on
machines that update the source guide.

PyMuPDF4LLM and PyMuPDF are available under AGPL v3 or a commercial licence. Confirm that the
project's eventual distribution licence is compatible before publishing the application.

```bash
cp .env.example .env
uv sync --all-groups
npm --prefix frontend install
```

Set credentials in `.env` only for the APIs you use. The local `.env` is ignored by Git:

```dotenv
TRAFIKLAB_RESROBOT_RESEPLANERARE_API_KEY=...
TRAFIKLAB_GTFS_API_KEY=...
```

Run the current skeleton checks with:

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix frontend run build
```

Create a rolling set of browser timetables from a generated bike subset, copy the artifacts to the
frontend's local public directory, then start the prototype:

```bash
cykelombord router build --days 90
npm --prefix frontend run prepare-router-data
npm --prefix frontend run dev
```

This produces one date-specific timetable per day (currently about 341 KB each), a reusable stops
index, and `router-manifest.json`. The frontend reads that manifest before enabling the date picker,
so it cannot request unpublished dates. Autocomplete and RAPTOR routing run in a web worker; no user
query is sent to a server.

## Update the bicycle guide

The guide PDF has a versioned, unstable URL. The command below fetches the stable landing page through
`r.jina.ai`, selects the Swedish `Cykel_pa_Tag_*.pdf` link with a defensive regular expression,
downloads it from Naturskyddsföreningen, and runs PyMuPDF4LLM's layout-aware Markdown conversion.
Install the optional extractor only when this command is needed:

```bash
uv sync --extra guide
uv run cykelombord guide update
```

It writes the downloaded PDF to `data/source/cykel-pa-tag.pdf` and these generated review inputs:

```text
data/generated/guide.md
data/generated/guide-source.json
```

The command fails instead of guessing if the landing page exposes multiple equally plausible Swedish
guide PDFs. `guide.md` deliberately preserves the extraction for human review. PyMuPDF4LLM retains
the guide's two-column reading order and regional-policy table as Markdown. A small normalizer joins
only incomplete lower-case continuations at a column boundary.

## Bicycle rules

[`rules/bike-rules.yaml`](rules/bike-rules.yaml) is the human-readable source of truth for the
initial policy extraction. It contains only facts explicitly stated by the June 2026 guide and links
each rule back to a page and heading. The build will later resolve these human-facing names against a
specific GTFS feed and compile the validated result to JSON for the web app.

Eligibility rules affect pruning and carry their stated capacity or capacity range. Separate
structured advisories preserve recurring events and service-specific operational warnings for display
after routing; for example, the Vätternrundan warning has a `weekend_before_midsummer` recurrence for
the frontend to evaluate.

The schema and repeatable extraction instructions are in [`RULES_SPEC.md`](RULES_SPEC.md). Validate
the checked-in ruleset with:

```bash
uv run cykelombord rules validate
```

## Build the first bike-compatible GTFS subset

The first pruner only keeps trips matched by explicit, resolved rules; it does not treat absent GTFS
`bikes_allowed` metadata as a prohibition. It writes a pruned archive, a source/feed manifest, and a
rule-resolution report. Unresolved policies are reported rather than guessed. The all-date subset is
affected only by eligibility rules; date-specific information such as Vätternrundan is retained as a
frontend advisory rather than incorrectly removing a service from every date.

```bash
uv run cykelombord gtfs build
```

This requires `TRAFIKLAB_GTFS_API_KEY`, enabled specifically for **GTFS Sverige 2**. The separate
`TRAFIKLAB_RESROBOT_RESEPLANERARE_API_KEY` is reserved for future ResRobot route-planner comparison
or fallback requests. Outputs are written to `data/generated/gtfs/` and are ignored by Git.

To re-run the pruner against an already downloaded archive without consuming an API request:

```bash
uv run cykelombord gtfs build --source-archive data/source/gtfs-sweden-2.zip
```

This is an intentionally conservative prototype, not a publishable feed yet: the accompanying
`rules-resolved.json` must have its unresolved selectors mapped and reviewed before the result is
used for journey planning.

## Operational commands

Every pipeline stage has a CLI command. GTFS validation is optional locally because `gtfs-guru`
ships a native extension; install it when running validation or the complete pipeline:

```bash
uv sync --extra gtfs-validation
```

The validator writes JSON and HTML reports and exits unsuccessfully only for validation errors, not
upstream warnings.

```bash
# Download and convert the current source guide (requires uv sync --extra guide)
cykelombord guide update

# Download GTFS Sverige 2, prune it, and write rules-resolved.json
cykelombord gtfs build

# Validate the pruned archive
cykelombord gtfs validate

# Compile a rolling range of daily browser artifacts and router-manifest.json
cykelombord router build --days 90

# Daily CI/CD command: download, prune, validate, then compile 90 days
cykelombord pipeline update --days 90
```

`pipeline update` deliberately stops before router generation if pruning produces an invalid GTFS.
Pass `--start-date YYYY-MM-DD` to `router build` or `pipeline update` for a reproducible range.

## Data and attribution

Downloaded source material is not committed. Put the current guide in `data/source/` when the
conversion milestone begins. Generated artifacts are published daily at
[cdn.cykelombord.mesu.re](https://cdn.cykelombord.mesu.re). The frontend uses this GitHub Pages data
site in production. Locally, it continues to read `/router/` after
`npm --prefix frontend run prepare-router-data`.

The eventual application must display the attribution required by Trafiklab's data licence and
retain a source URL and retrieval date for every manually maintained bicycle rule.

See [PLAN.md](PLAN.md) for the ordered milestones and [RESEARCH.md](RESEARCH.md) for the reasoning
behind the architecture.
