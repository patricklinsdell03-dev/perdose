"""LLM extraction (brief §9.1-9.2): listing text in, `Extraction` out.

The model never sees a price and never computes anything. Its output is forced to a JSON
schema by the API (structured outputs via `client.messages.parse`), then validated again
into our own `Extraction` model.
"""

from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, ValidationError

from pipeline.compounds import Registry
from pipeline.normalise.prompt import SYSTEM_PROMPT, build_user_message, find_candidates
from pipeline.normalise.schema import AmountRefersTo, Extraction, PackUnitType
from pipeline.settings import LlmConfig, ModelChoice

# --- the shape the API fills in ------------------------------------------------------------
# Same fields as schema.Extraction, but every field is required and evidence is a list:
# structured outputs cannot express free-form {field: quote} objects.


class LlmQuote(BaseModel):
    field: str
    quote: str


class LlmComponent(BaseModel):
    name: str
    amount: float
    unit: Literal["mg", "mcg", "g", "IU", "percent"]


class LlmActive(BaseModel):
    compound_id: str
    form_raw: str | None
    form_id: str | None
    amount_per_serving: float | None
    amount_unit: Literal["mg", "mcg", "g", "IU"] | None
    amount_refers_to: AmountRefersTo | None
    components: list[LlmComponent]
    extract_ratio: str | None
    branded_extract: str | None
    evidence: list[LlmQuote]


class LlmExtraction(BaseModel):
    actives: list[LlmActive]
    is_single_ingredient: bool
    other_actives: list[str]
    pack_units: int | None
    pack_unit_type: PackUnitType | None
    units_per_serving: float | None
    servings_stated: int | None
    multipack_count: int | None
    tested_claims: list[str]
    confidence: float
    review_reasons: list[str]
    evidence: list[LlmQuote]


def to_extraction(raw: LlmExtraction) -> Extraction:
    data = raw.model_dump()
    data["confidence"] = min(max(data["confidence"], 0.0), 1.0)
    data["evidence"] = {q["field"]: q["quote"] for q in data["evidence"]}
    for active in data["actives"]:
        active["evidence"] = {q["field"]: q["quote"] for q in active["evidence"]}
    return Extraction.model_validate(data)


# --- the extractor -------------------------------------------------------------------------


class ExtractionFailed(Exception):
    """No valid extraction even after a retry and an escalation."""


@dataclass
class ExtractionResult:
    extraction: Extraction
    model_id: str
    escalated: bool


class Extractor:
    def __init__(self, config: LlmConfig, registry: Registry, client=None):
        self.config = config
        self.registry = registry
        self.client = client or anthropic.Anthropic()
        self.calls = 0
        self.listings = 0
        self.escalations = 0

    @property
    def escalation_rate(self) -> float:
        return self.escalations / self.listings if self.listings else 0.0

    def _call(self, choice: ModelChoice, user_message: str) -> Extraction | None:
        kwargs = {}
        if choice.effort:
            kwargs["output_config"] = {"effort": choice.effort}
        self.calls += 1
        response = self.client.messages.parse(
            model=choice.id,
            max_tokens=self.config.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=LlmExtraction,
            **kwargs,
        )
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            return None
        try:
            return to_extraction(response.parsed_output)
        except ValidationError:
            return None

    def _attempt(self, choice: ModelChoice, user_message: str) -> Extraction | None:
        """One call, plus one retry if the output does not validate (§9.2)."""
        return self._call(choice, user_message) or self._call(choice, user_message)

    def _needs_escalation(self, extraction: Extraction | None) -> bool:
        if extraction is None:
            return True
        if extraction.confidence < self.config.escalation_confidence_threshold:
            return True
        for active in extraction.actives:
            compound = self.registry.get(active.compound_id)
            if (
                compound
                and compound.label_convention == "ambiguous"
                and active.amount_per_serving is not None
                and active.amount_refers_to in ("unclear", None)
            ):
                return True
        return False

    def extract(self, title: str, description: str = "") -> ExtractionResult:
        candidates = find_candidates(self.registry, title, description)
        if not candidates:
            empty = Extraction(is_single_ingredient=False, confidence=1.0)
            return ExtractionResult(empty, model_id="none", escalated=False)

        self.listings += 1
        message = build_user_message(
            candidates, title, description, self.config.description_max_chars
        )
        models = self.config.models
        first = self._attempt(models.default, message)
        if not self._needs_escalation(first):
            return ExtractionResult(first, models.default.id, escalated=False)

        self.escalations += 1
        second = self._attempt(models.escalation, message)
        if second is not None:
            return ExtractionResult(second, models.escalation.id, escalated=True)
        if first is not None:
            return ExtractionResult(first, models.default.id, escalated=True)
        raise ExtractionFailed(title)
