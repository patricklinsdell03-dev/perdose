"""The extractor's control flow, with a fake API client — no network, no key."""

from types import SimpleNamespace

import pytest

from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.normalise.llm import (
    ExtractionFailed,
    Extractor,
    LlmExtraction,
    to_extraction,
)
from pipeline.normalise.run import BudgetExceeded, content_hash, normalise
from pipeline.settings import load_llm_config

REGISTRY = load_registry()
CONFIG = load_llm_config()


def fixture_output(
    confidence=0.95, refers_to="elemental", compound_id="zinc", form_id="picolinate"
):
    return LlmExtraction.model_validate(
        {
            "actives": [
                {
                    "compound_id": compound_id,
                    "form_raw": None,
                    "form_id": form_id,
                    "amount_per_serving": 15,
                    "amount_unit": "mg",
                    "amount_refers_to": refers_to,
                    "components": [],
                    "extract_ratio": None,
                    "branded_extract": None,
                    "evidence": [{"field": "amount_per_serving", "quote": "15mg"}],
                }
            ],
            "is_single_ingredient": True,
            "other_actives": [],
            "pack_units": 120,
            "pack_unit_type": "capsule",
            "units_per_serving": None,
            "servings_stated": None,
            "multipack_count": None,
            "tested_claims": [],
            "confidence": confidence,
            "review_reasons": [],
            "evidence": [{"field": "pack_units", "quote": "120 Capsules"}],
        }
    )


class FixtureClient:
    """Stands in for anthropic.Anthropic(): returns queued outputs, records requests."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.requests.append(kwargs)
        output = self.outputs.pop(0)
        return SimpleNamespace(parsed_output=output, stop_reason="end_turn")


def make_extractor(outputs):
    client = FixtureClient(outputs)
    return Extractor(CONFIG, REGISTRY, client=client), client


def test_evidence_lists_become_dicts():
    extraction = to_extraction(fixture_output())
    assert extraction.evidence == {"pack_units": "120 Capsules"}
    assert extraction.actives[0].evidence == {"amount_per_serving": "15mg"}


def test_confident_extraction_uses_one_call_and_never_sees_a_price():
    extractor, client = make_extractor([fixture_output()])
    result = extractor.extract("Zinc Picolinate 15mg 120 Capsules")
    assert (extractor.calls, result.escalated) == (1, False)
    request = client.requests[0]
    assert request["model"] == CONFIG.models.default.id
    assert "temperature" not in request  # Sonnet 5 rejects sampling parameters
    assert "£" not in request["messages"][0]["content"]
    assert "compound_id: zinc" in request["messages"][0]["content"]
    assert "compound_id: creatine" not in request["messages"][0]["content"]  # candidates only


def test_low_confidence_escalates():
    extractor, client = make_extractor([fixture_output(confidence=0.5), fixture_output()])
    result = extractor.extract("Zinc Picolinate 15mg 120 Capsules")
    assert result.escalated and extractor.calls == 2
    assert client.requests[1]["output_config"] == {"effort": CONFIG.models.escalation.effort}
    assert extractor.escalation_rate == 1.0


def test_unclear_amount_on_an_ambiguous_compound_escalates():
    unclear = fixture_output(refers_to="unclear", compound_id="magnesium", form_id="citrate")
    extractor, _ = make_extractor([unclear, unclear])
    assert extractor.extract("Magnesium Citrate 200mg 120 Capsules").escalated


def test_unclear_amount_on_an_elemental_default_compound_does_not_escalate():
    extractor, _ = make_extractor([fixture_output(refers_to="unclear")])
    assert not extractor.extract("Zinc Picolinate 15mg 120 Capsules").escalated


def test_invalid_output_is_retried_once_then_escalated():
    extractor, _ = make_extractor([None, None, fixture_output()])
    result = extractor.extract("Zinc Picolinate 15mg 120 Capsules")
    assert result.escalated and extractor.calls == 3


def test_nothing_valid_anywhere_raises():
    extractor, _ = make_extractor([None, None, None, None])
    with pytest.raises(ExtractionFailed):
        extractor.extract("Zinc Picolinate 15mg 120 Capsules")


def test_listing_with_no_candidate_compound_makes_no_call():
    extractor, _ = make_extractor([])
    result = extractor.extract("Fixture Yoga Mat 6mm")
    assert extractor.calls == 0 and result.extraction.actives == []


# --- make normalise ----------------------------------------------------------------------


def fixture_db(titles):
    conn = connect(":memory:")
    for i, title in enumerate(titles):
        conn.execute(
            "INSERT INTO listings VALUES (?, 'fixture_retailer', ?, NULL, NULL, ?, NULL,"
            " 'https://example.invalid', NULL, 1.0, 1, '2026-09-17', '2026-09-17', ?)",
            (f"fixture_retailer:{i}", str(i), title, content_hash(title, None)),
        )
    return conn


def test_normalise_caches_by_content_hash_and_prompt_version():
    conn = fixture_db(["Zinc Picolinate 15mg 120 Capsules", "Zinc Picolinate 15mg 120 Capsules"])
    extractor, _ = make_extractor([fixture_output()])
    first = normalise(conn, extractor)
    assert (first["pending"], first["extracted"], first["calls"]) == (1, 1, 1)  # same text once
    second = normalise(conn, extractor)
    assert second["pending"] == 0  # never re-call for an unchanged listing


def test_normalise_force_re_extracts():
    conn = fixture_db(["Zinc Picolinate 15mg 120 Capsules"])
    extractor, _ = make_extractor([fixture_output(), fixture_output()])
    normalise(conn, extractor)
    assert normalise(conn, extractor, force=True)["extracted"] == 1


def test_normalise_budget_guard_aborts_before_any_call():
    conn = fixture_db([f"Zinc Picolinate 15mg {n} Capsules" for n in range(3)])
    extractor, _ = make_extractor([])
    extractor.config = CONFIG.model_copy(update={"max_calls_per_run": 2})
    with pytest.raises(BudgetExceeded):
        normalise(conn, extractor)
    assert extractor.calls == 0
