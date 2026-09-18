"""Recomputes every elemental factor from its chemical formula (config/factor_sources.yml)."""

from pathlib import Path

import pytest
import yaml

from pipeline.compounds import load_registry

# IUPAC abridged standard atomic weights.
ATOMIC_WEIGHT = {
    "H": 1.008,
    "C": 12.011,
    "N": 14.007,
    "O": 15.999,
    "Mg": 24.305,
    "S": 32.06,
    "Cl": 35.45,
    "Zn": 65.38,
    "K": 39.098,
    "Ca": 40.078,
    "Cr": 51.996,
    "Fe": 55.845,
    "I": 126.904,
    "Cu": 63.546,
}


def molecular_weight(atoms: dict[str, int]) -> float:
    return sum(ATOMIC_WEIGHT[el] * n for el, n in atoms.items())


def computed_factor(source: dict) -> float:
    """An elemental factor (`element`) or, for actives that are molecules such as citrulline
    or HMB, the active's share of the salt (`active_atoms` x `active_count`)."""
    total = molecular_weight(source["atoms"])
    if "element" in source:
        return ATOMIC_WEIGHT[source["element"]] * source["atoms"][source["element"]] / total
    return molecular_weight(source["active_atoms"]) * source["active_count"] / total


SOURCES = yaml.safe_load(Path("config/factor_sources.yml").read_text(encoding="utf-8"))["sources"]
REGISTRY = load_registry()


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: f"{s['compound']}/{s['form']}")
def test_factor_matches_formula(source):
    computed = computed_factor(source)
    configured = REGISTRY.get(source["compound"]).form(source["form"]).elemental_factor
    assert configured == pytest.approx(computed, rel=0.015)


def test_every_factor_has_a_source():
    sourced = {(s["compound"], s["form"]) for s in SOURCES}
    configured = {
        (c.id, f.id) for c in REGISTRY.compounds for f in c.forms if f.elemental_factor is not None
    }
    assert configured == sourced
