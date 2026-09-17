"""Golden set in calc-only mode (brief §15). The live-LLM mode arrives in Phase 2."""

import pytest

from pipeline.compounds import load_registry
from pipeline.golden import (
    PASS_THRESHOLD,
    coverage_gaps,
    load_golden_labels,
    run_calc_only,
)

REGISTRY = load_registry()
LABELS = load_golden_labels()
RESULTS = run_calc_only(REGISTRY, LABELS)


def test_golden_ids_unique():
    ids = [label["id"] for label in LABELS]
    assert len(ids) == len(set(ids))


def test_every_compound_has_at_least_three_golden_labels():
    assert coverage_gaps(REGISTRY, LABELS) == {}


def test_golden_pass_rate_meets_threshold():
    passed = sum(1 for problems in RESULTS.values() if not problems)
    assert passed / len(LABELS) >= PASS_THRESHOLD


@pytest.mark.parametrize("label_id", [label["id"] for label in LABELS])
def test_golden_label(label_id):
    # Calc-only mode is deterministic, so every label must pass, not just 90 %.
    assert RESULTS[label_id] == []


def test_checker_is_not_vacuous():
    # A deliberately wrong expectation must be reported.
    label = dict(LABELS[0], expect={**LABELS[0]["expect"], "amount": 999, "servings": 1})
    problems = run_calc_only(REGISTRY, [label])[label["id"]]
    assert len(problems) == 2


def test_checker_rejects_unknown_expect_keys():
    label = dict(LABELS[0], expect={"ammount": 200})
    assert run_calc_only(REGISTRY, [label])[label["id"]] == ["unknown expect key 'ammount'"]
