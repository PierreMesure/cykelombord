from pathlib import Path

import pytest

from cykelombord.rules import RulesError, load_ruleset

RULESET_PATH = Path("rules/bike-rules.yaml")


def test_checked_in_ruleset_is_valid() -> None:
    ruleset = load_ruleset(RULESET_PATH)

    assert ruleset.schema_version == 1
    assert len(ruleset.rules) == 18
    assert len(ruleset.advisories) == 2
    assert ruleset.source.edition == "2026-06"


def test_checked_in_ruleset_contains_a_narrower_exception() -> None:
    ruleset = load_ruleset(RULESET_PATH)
    rules = {rule.id: rule for rule in ruleset.rules}
    advisories = {advisory.id: advisory for advisory in ruleset.advisories}

    assert rules["ostgotapendeln"].bicycle.permission == "allowed"
    assert advisories["ostgotapendeln-vatternrundan"].kind == "event"
    assert advisories["ostgotapendeln-vatternrundan"].recurrence == "weekend_before_midsummer"


def test_variable_capacity_stays_with_the_matching_rule() -> None:
    ruleset = load_ruleset(RULESET_PATH)
    rules = {rule.id: rule for rule in ruleset.rules}
    advisories = {advisory.id: advisory for advisory in ruleset.advisories}

    assert rules["krosatagen-general"].bicycle.capacity.kind == "range"
    assert rules["krosatagen-general"].bicycle.capacity.min == 2
    assert rules["krosatagen-general"].bicycle.capacity.max == 6
    assert rules["tag-i-bergslagen"].bicycle.capacity.min == 0
    assert rules["tag-i-bergslagen"].bicycle.capacity.max == 6
    assert advisories["tag-i-bergslagen-bicycle-space"].kind == "operational"


def test_rejects_an_inconsistent_fixed_fare(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-rules.yaml"
    invalid.write_text(
        """
schema_version: 1
source:
  name: Test
  edition: test
  url: https://example.invalid/guide.pdf
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
rules:
  - id: test-service
    priority: 100
    match: {modes: [rail], agencies: [Test]}
    bicycle:
      permission: allowed
      fare: {kind: fixed_sek}
      capacity: {kind: unspecified}
    evidence: [{page: 1, locator: Test}]
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(RulesError, match="fixed_sek fare needs amount_sek"):
        load_ruleset(invalid)
