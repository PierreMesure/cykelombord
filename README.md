# Cykel på tåg

Cykel på tåg aims to plan Swedish public-transport journeys on which a traveller can bring an
assembled bicycle. It will combine Trafiklab timetable data with structured rules derived from
Naturskyddsföreningen's regularly updated guide.

The guide downloader, PDF-to-Markdown conversion, and a first source-extracted YAML ruleset are
implemented.
GTFS downloading, pruning, validation, routing, and the planner interface are not yet implemented.

## Repository layout

```text
.
├── data/
│   ├── source/       # Local source guide and downloaded GTFS (gitignored)
│   └── generated/    # Generated Markdown, rules, and routing data (gitignored)
├── frontend/         # Vite and TypeScript web application
├── rules/            # Reviewed, human-authored bicycle policy rules
├── src/cykelpatag/  # Python data-pipeline package
├── tests/            # Python tests
├── PLAN.md          # Chosen implementation plan
└── RESEARCH.md      # Research findings and alternatives
```

## Local setup

Prerequisites are Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22, and npm. The optional
`guide` extra installs [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) only on
machines that update the source guide.

PyMuPDF4LLM and PyMuPDF are available under AGPL v3 or a commercial licence. Confirm that the
project's eventual distribution licence is compatible before publishing the application.

```bash
cp .env.example .env
uv sync --all-groups
npm --prefix frontend install
```

Set `TRAFIKLAB_API_KEY` in `.env`. The local `.env` is ignored by Git.

Run the current skeleton checks with:

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm --prefix frontend run build
```

Start the placeholder frontend with:

```bash
npm --prefix frontend run dev
```

## Update the bicycle guide

The guide PDF has a versioned, unstable URL. The command below fetches the stable landing page through
`r.jina.ai`, selects the Swedish `Cykel_pa_Tag_*.pdf` link with a defensive regular expression,
downloads it from Naturskyddsföreningen, and runs PyMuPDF4LLM's layout-aware Markdown conversion.
Install the optional extractor only when this command is needed:

```bash
uv sync --extra guide
uv run cykelpatag guide update
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

The schema and repeatable extraction instructions are in [`RULES_SPEC.md`](RULES_SPEC.md). Validate
the checked-in ruleset with:

```bash
uv run cykelpatag rules validate
```

## Data and attribution

Downloaded source material is not committed. Put the current guide in `data/source/` when the
conversion milestone begins. Generated artifacts belong in `data/generated/` until the publishing
strategy is implemented.

The eventual application must display the attribution required by Trafiklab's data licence and
retain a source URL and retrieval date for every manually maintained bicycle rule.

See [PLAN.md](PLAN.md) for the ordered milestones and [RESEARCH.md](RESEARCH.md) for the reasoning
behind the architecture.
