"""The `Extraction` schema (brief §9.3): what the LLM returns for one listing.

The model only fills these fields from the label text. It never sees a price and never
computes anything — that happens in rules.py and price/calc.py.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AmountRefersTo = Literal["elemental", "compound", "total_oil", "extract", "unclear"]
PackUnitType = Literal["capsule", "tablet", "softgel", "gummy", "gram", "ml", "sachet", "drop"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentAmount(_Model):
    name: str  # e.g. "EPA", "DHA", "withanolides", "compound_mass"
    amount: float
    unit: Literal["mg", "mcg", "g", "IU", "percent"]


class ActiveExtraction(_Model):
    compound_id: str  # one of the candidate ids supplied in the user message
    form_raw: str | None = None  # form words exactly as on label
    form_id: str | None = None  # mapped id from compounds.yml, else null
    amount_per_serving: float | None = None
    amount_unit: Literal["mg", "mcg", "g", "IU"] | None = None
    amount_refers_to: AmountRefersTo | None = None
    components: list[ComponentAmount] = []
    extract_ratio: str | None = None  # e.g. "10:1"
    branded_extract: str | None = None  # "KSM-66", "Creapure", "Magtein"…
    evidence: dict[str, str] = {}  # field (or component name) -> exact label substring


class Extraction(_Model):
    actives: list[ActiveExtraction] = []  # every candidate compound present; [] if none
    is_single_ingredient: bool
    other_actives: list[str] = []  # actives that are NOT candidates (B6, copper, piperine…)
    pack_units: int | None = None
    pack_unit_type: PackUnitType | None = None
    units_per_serving: float | None = None
    servings_stated: int | None = None
    multipack_count: int | None = None  # "3 x 90 tablets" -> 3
    tested_claims: list[str] = []
    confidence: float = Field(ge=0, le=1)  # 0..1, model's own
    review_reasons: list[str] = []
    evidence: dict[str, str] = {}  # pack/serving fields -> exact label substring
