# Bicycle ruleset specification

`rules/bike-rules.yaml` is the reviewed, human-readable source of truth for bicycle carriage.
The GTFS build will later validate it and compile it to JSON; do not hand-edit generated JSON.

## Extraction instructions

Use the current `data/generated/guide.md` and the source PDF metadata. Follow these rules exactly:

1. Keep capacity in the routing rule, including a range when it varies by train type. Put recurring
   events and service-specific operational warnings (for example, some trains having no usable bike
   space) in `advisories`.
2. Copy source names into `agencies`. Use `agency_aliases` only for an exact, reviewed GTFS
   `agency_name` spelling; never invent a GTFS ID or silently guess a company mapping.
3. Encode only explicit facts. Use `unknown` where the guide does not say whether a bicycle booking,
   ticket purchase method, fare, or capacity applies.
4. State an assembled-bicycle permission in every rule. `conditional` means it is permitted only
   subject to one or more listed conditions; it is not a denial.
5. Give every rule at least one page number and stable source locator, for example
   `Cykel på regionala tåg > Skåne`.
6. Make a narrower exception higher priority than its broad parent rule. A later build applies
   matching rules in ascending priority; a populated field in the higher-priority rule overrides a
   populated lower-priority field.
7. Preserve ambiguity in `conditions[].description`; never turn a recommendation into a prohibition.
8. Keep comments short and factual. The original guide remains the evidence, not the YAML.

## YAML shape

```yaml
schema_version: 1
source:
  name: Cykel på tåg
  edition: 2026-06
  url: https://example.invalid/Cykel_pa_Tag_2026-06-07.pdf
  sha256: 64-lowercase-hex-characters
rules:
  - id: operator-service
    priority: 100
    match:
      modes: [rail]                 # rail, bus, or ferry
      agencies: [Operator name]
      agency_aliases: [GTFS operator name] # optional, only when the source spelling differs
      services: [Service name]       # optional, guide spelling
      corridors: [Origin–destination] # optional, guide spelling
      vehicle_types: [electric]      # optional
    bicycle:
      permission: allowed            # allowed, not_allowed, packed_only, conditional, unknown
      bike_booking: unknown          # required, not_required, first_come, unknown
      ticket_purchase: unknown       # advance_only, onboard_allowed, unknown
      fare:
        kind: free                   # free, fixed_sek, included_with_ticket, unknown
        amount_sek: null             # required only for fixed_sek
        note: null
      capacity:
        kind: exact                  # exact, range, at_least, variable, unspecified
        min: 6
        max: 6
        per: trainset                # train, trainset, vehicle, unknown
        note: null
      conditions:
        - kind: time_window          # see allowed kinds below
          description: "Only outside peak hours."
    evidence:
      - page: 8
        locator: "Cykel på regionala tåg > Operator name"
advisories:
  - id: operator-capacity
    match:
      modes: [rail]
      agencies: [Operator name]
    kind: capacity                 # capacity, event, or operational
    severity: info                 # info or warning
    message: "Space is limited."
    recurrence: null               # weekend_before_midsummer for Vätternrundan
    evidence:
      - page: 8
        locator: "Cykel på regionala tåg > Operator name"
```

Allowed condition kinds are `bike_type`, `capacity_discretion`, `event_dates`,
`route_exclusion`, `season`, `secure_bike`, and `time_window`.

Advisories never affect GTFS pruning. The frontend can display them after the corresponding
service is matched; it is responsible for evaluating a declared recurrence.

## Validation

Run:

```bash
uv run cykelpatag rules validate
```

The parser rejects unknown fields, duplicate IDs, missing evidence, invalid enums, invalid capacity
ranges, and malformed fixed fares. This strictness is intentional: an LLM may create a draft, but a
draft must pass validation and human review before it can affect routing.
