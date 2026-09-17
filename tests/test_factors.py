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
}
SOURCES = yaml.safe_load(Path("config/factor_sources.yml").read_text(encoding="utf-8"))["sources"]
REGISTRY = load_registry()


@pytest.mark.parametrize("source", SOURCES, ids=lambda s: f"{s['compound']}/{s['form']}")
def test_factor_matches_formula(source):
    atoms = source["atoms"]
    molecular_weight = sum(ATOMIC_WEIGHT[el] * n for el, n in atoms.items())
    computed = ATOMIC_WEIGHT[source["element"]] * atoms[source["element"]] / molecular_weight
    configured = REGISTRY.get(source["compound"]).form(source["form"]).elemental_factor
    assert configured == pytest.approx(computed, rel=0.015)


def test_every_factor_has_a_source():
    sourced = {(s["compound"], s["form"]) for s in SOURCES}
    configured = {
        (c.id, f.id) for c in REGISTRY.compounds for f in c.forms if f.elemental_factor is not None
    }
    assert configured == sourced
