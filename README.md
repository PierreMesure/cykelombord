# Cykel på tåg

Cykel på tåg aims to plan Swedish public-transport journeys on which a traveller can bring an
assembled bicycle. It will combine Trafiklab timetable data with structured rules derived from
Naturskyddsföreningen's regularly updated guide.

The repository currently contains the first project skeleton only. Guide conversion, rule
extraction, GTFS downloading, pruning, validation, routing, and the planner interface have not yet
been implemented.

## Repository layout

```text
.
├── data/
│   ├── source/       # Local source guide and downloaded GTFS (gitignored)
│   └── generated/    # Generated Markdown, rules, and routing data (gitignored)
├── frontend/         # Vite and TypeScript web application
├── src/cykelpatag/  # Python data-pipeline package
├── tests/            # Python tests
├── PLAN.md          # Chosen implementation plan
└── RESEARCH.md      # Research findings and alternatives
```

## Local setup

Prerequisites are Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22, npm, and the
[`lit` CLI](https://www.npmjs.com/package/@llamaindex/liteparse) for guide extraction.

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

## Data and attribution

Downloaded source material is not committed. Put the current guide in `data/source/` when the
conversion milestone begins. Generated artifacts belong in `data/generated/` until the publishing
strategy is implemented.

The eventual application must display the attribution required by Trafiklab's data licence and
retain a source URL and retrieval date for every manually maintained bicycle rule.

See [PLAN.md](PLAN.md) for the ordered milestones and [RESEARCH.md](RESEARCH.md) for the reasoning
behind the architecture.
