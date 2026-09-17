"""Loads and validates config/compounds.yml — the rules table (brief §6, Appendix A)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

COMPOUNDS_PATH = Path("config/compounds.yml")

Unit = Literal["mg", "mcg", "IU"]
LabelConvention = Literal["elemental_default", "ambiguous", "compound_default"]
# Later types (per_serving, cfu_count, per_gram_macro) are added when they are built (§6.5).
NormalisationType = Literal[
    "mineral_elemental", "vitamin_unit", "oil_components", "extract_standardised", "simple_mass"
]
Category = Literal[
    "vitamins",
    "minerals",
    "amino-acids",
    "sports",
    "fatty-acids",
    "botanicals",
    "nootropics",
    "general-health",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Form(_Model):
    id: str
    names: list[str] = Field(min_length=1)
    form_class: str = Field(alias="class")
    elemental_factor: float | None = Field(default=None, gt=0, le=1)
    standard_dose_override: float | None = Field(default=None, gt=0)
    note: str | None = None


class UnclearAmountHeuristic(_Model):
    """What an unqualified amount most likely means (§9.5 step 3)."""

    compound_if_at_least: float | None = None
    compound_forms: list[str] = []
    elemental_if_at_most: float | None = None


class Heuristics(_Model):
    unclear_amount: UnclearAmountHeuristic | None = None


class Compound(_Model):
    id: str
    name: str
    category: Category
    tier: Literal[1, 2, 3]
    comparison_quantity: str
    unit: Unit
    standard_dose: float = Field(gt=0)
    unit_conversions: dict[str, float] = {}
    label_convention: LabelConvention
    normalisation_type: NormalisationType
    components_sum: list[str] = []
    standardisation_component: str | None = None
    aliases: list[str] = Field(min_length=1)
    accepted_cofactors: list[str] = []
    heuristics: Heuristics | None = None
    forms: list[Form] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "Compound":
        form_ids = [f.id for f in self.forms]
        if len(form_ids) != len(set(form_ids)):
            raise ValueError(f"{self.id}: duplicate form ids")
        # A class is one table with one comparison dose, so its forms must agree on it.
        doses: dict[str, float | None] = {}
        for form in self.forms:
            previous = doses.setdefault(form.form_class, form.standard_dose_override)
            if previous != form.standard_dose_override:
                raise ValueError(f"{self.id}: class {form.form_class} has conflicting doses")
        if self.normalisation_type == "oil_components" and not self.components_sum:
            raise ValueError(f"{self.id}: oil_components needs components_sum")
        if self.unit == "IU" and "mcg_to_IU" not in self.unit_conversions:
            raise ValueError(f"{self.id}: an IU compound needs unit_conversions.mcg_to_IU")
        if self.heuristics and self.heuristics.unclear_amount:
            unknown = set(self.heuristics.unclear_amount.compound_forms) - set(form_ids)
            if unknown:
                raise ValueError(f"{self.id}: heuristic names unknown forms {sorted(unknown)}")
        return self

    def form(self, form_id: str | None) -> Form | None:
        return next((f for f in self.forms if f.id == form_id), None)

    def form_by_name(self, text: str | None) -> Form | None:
        wanted = (text or "").strip().lower()
        return next((f for f in self.forms if wanted in (n.lower() for n in f.names)), None)

    def standard_dose_for(self, form: Form | None) -> float:
        if form and form.standard_dose_override:
            return form.standard_dose_override
        return self.standard_dose


class Registry(_Model):
    version: int
    compounds: list[Compound]

    @model_validator(mode="after")
    def _check(self) -> "Registry":
        ids = [c.id for c in self.compounds]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate compound ids")
        classes = [cls for c in self.compounds for cls in {f.form_class for f in c.forms}]
        if len(classes) != len(set(classes)):
            raise ValueError("a form class is used by more than one compound")
        return self

    def get(self, compound_id: str) -> Compound | None:
        return next((c for c in self.compounds if c.id == compound_id), None)


def load_registry(path: Path = COMPOUNDS_PATH) -> Registry:
    return Registry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
