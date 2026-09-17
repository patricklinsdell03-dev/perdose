"""Drafted compound batches (config/drafts/) are held to the same standard as live rules:
the merged registry must validate, every factor must match its formula, and every compound
needs three golden labels that pass the rules + calculator. Drafts never reach the site."""

from pathlib import Path

import pytest
import yaml

from pipeline.compounds import COMPOUNDS_PATH, Registry
from pipeline.golden import MIN_LABELS_PER_COMPOUND, run_calc_only

DRAFTS = sorted(Path("config/drafts").glob("batch_*.yml"))
DRAFTS = [path for path in DRAFTS if not path.stem.endswith("_factor_sources")]

ATOMIC_WEIGHT = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "S": 32.06, "Cl": 35.45, "K": 39.098,
    "Ca": 40.078, "Cr": 51.996, "Fe": 55.845, "I": 126.904, "Mg": 24.305, "Zn": 65.38,
}  # fmt: skip


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def merged_registry(draft_path) -> Registry:
    live = load_yaml(COMPOUNDS_PATH)
    draft = load_yaml(draft_path)
    return Registry.model_validate(
        {"version": 1, "compounds": live["compounds"] + draft["compounds"]}
    )


@pytest.mark.parametrize("draft", DRAFTS, ids=lambda p: p.stem)
def test_draft_merges_cleanly_with_the_live_registry(draft):
    registry = merged_registry(draft)  # raises on duplicate ids, shared classes, bad factors…
    assert len(registry.compounds) > 10


@pytest.mark.parametrize("draft", DRAFTS, ids=lambda p: p.stem)
def test_draft_factors_match_their_formulas(draft):
    registry = merged_registry(draft)
    sources = load_yaml(draft.with_name(f"{draft.stem}_factor_sources.yml"))["sources"]
    draft_ids = {c["id"] for c in load_yaml(draft)["compounds"]}
    for source in sources:
        atoms = source["atoms"]
        weight = sum(ATOMIC_WEIGHT[el] * n for el, n in atoms.items())
        computed = ATOMIC_WEIGHT[source["element"]] * atoms[source["element"]] / weight
        configured = registry.get(source["compound"]).form(source["form"]).elemental_factor
        assert configured == pytest.approx(computed, rel=0.015), source["substance"]
    sourced = {(s["compound"], s["form"]) for s in sources}
    configured = {
        (c.id, f.id)
        for c in registry.compounds
        if c.id in draft_ids
        for f in c.forms
        if f.elemental_factor is not None
    }
    assert configured == sourced


@pytest.mark.parametrize("draft", DRAFTS, ids=lambda p: p.stem)
def test_draft_golden_labels_pass_rules_and_calculator(draft):
    registry = merged_registry(draft)
    labels = load_yaml(Path("tests/golden/drafts") / draft.name)["labels"]
    results = run_calc_only(registry, labels)
    failures = {label_id: problems for label_id, problems in results.items() if problems}
    assert failures == {}

    counts: dict[str, int] = {}
    for label in labels:
        for compound_id in label["compounds"]:
            counts[compound_id] = counts.get(compound_id, 0) + 1
    for compound in load_yaml(draft)["compounds"]:
        assert counts.get(compound["id"], 0) >= MIN_LABELS_PER_COMPOUND, compound["id"]


@pytest.mark.parametrize("draft", DRAFTS, ids=lambda p: p.stem)
def test_draft_saved_llm_readings_meet_the_threshold(draft):
    from pipeline.golden import PASS_THRESHOLD, run_replay
    from pipeline.settings import load_llm_config

    labels = load_yaml(Path("tests/golden/drafts") / draft.name)["labels"]
    cache = Path("tests/golden/drafts/cache") / draft.stem
    replayed = run_replay(merged_registry(draft), labels, load_llm_config().prompt_version, cache)
    if not replayed:
        pytest.skip("not validated against the model yet: make golden-live DRAFT=<batch>")
    passed = sum(1 for problems in replayed.values() if not problems)
    assert passed / len(replayed) >= PASS_THRESHOLD
