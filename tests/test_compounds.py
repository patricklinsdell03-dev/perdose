import copy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pipeline.compounds import Registry, load_registry

RAW = yaml.safe_load(Path("config/compounds.yml").read_text(encoding="utf-8"))


def _raw():
    return copy.deepcopy(RAW)


PROTOTYPE_IDS = {
    "magnesium", "zinc", "vitamin_d3", "vitamin_k2", "vitamin_c", "vitamin_b12",
    "omega_3", "creatine", "ashwagandha", "l_theanine",
}  # fmt: skip


def test_registry_loads_the_prototype_compounds_and_batch_one():
    registry = load_registry()
    ids = {c.id for c in registry.compounds}
    assert PROTOTYPE_IDS <= ids
    assert len(ids) == 92  # 10 prototype + batches 1-4 + multivitamin + collagen (DECISIONS.md)
    assert registry.get("magnesium").form("bisglycinate").form_class == "mg_glycinate"


def test_standard_dose_override_applies_per_class():
    k2 = load_registry().get("vitamin_k2")
    assert k2.standard_dose_for(k2.form("mk7")) == 100
    assert k2.standard_dose_for(k2.form("mk4")) == 5000


def test_duplicate_compound_id_rejected():
    raw = _raw()
    raw["compounds"].append(copy.deepcopy(raw["compounds"][0]))
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)


def test_factor_outside_zero_to_one_rejected():
    raw = _raw()
    raw["compounds"][0]["forms"][0]["elemental_factor"] = 1.41
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)


def test_unit_must_be_a_base_unit():
    raw = _raw()
    raw["compounds"][0]["unit"] = "g"
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)


def test_form_without_class_rejected():
    raw = _raw()
    del raw["compounds"][0]["forms"][0]["class"]
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)


def test_unknown_normalisation_type_rejected():
    raw = _raw()
    raw["compounds"][0]["normalisation_type"] = "magic"
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)


def test_conflicting_dose_within_a_class_rejected():
    raw = _raw()
    d3 = next(c for c in raw["compounds"] if c["id"] == "vitamin_d3")
    d3["forms"][1]["standard_dose_override"] = 2000  # d3_vegan shares class d3 with d3
    with pytest.raises(ValidationError):
        Registry.model_validate(raw)
