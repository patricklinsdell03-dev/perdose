"""Brief §9.5 — one test (at least) per rule. Extractions here are hand-built fixtures."""

import pytest

from pipeline.compounds import load_registry
from pipeline.normalise.rules import apply_rules, convert_amount
from pipeline.normalise.schema import Extraction

REGISTRY = load_registry()


def fixture_active(compound_id, form_id, amount=None, unit="mg", refers_to=None, **extra):
    active = {
        "compound_id": compound_id,
        "form_id": form_id,
        "amount_per_serving": amount,
        "amount_unit": unit if amount is not None else None,
        "amount_refers_to": refers_to,
        "evidence": {"amount_per_serving": "fixture"} if amount is not None else {},
    }
    components = extra.pop("components", [])
    active["components"] = components
    active["evidence"].update({c["name"]: "fixture" for c in components})
    active.update(extra)
    return active


def fixture_extraction(actives, pack_units=120, units_per_serving=1, **extra):
    data = {
        "actives": actives,
        "is_single_ingredient": len(actives) == 1 and not extra.get("other_actives"),
        "pack_units": pack_units,
        "pack_unit_type": "capsule",
        "units_per_serving": units_per_serving,
        "confidence": 0.95,
        "evidence": {"pack_units": "fixture", "units_per_serving": "fixture"},
    }
    for key in ("servings_stated", "multipack_count"):
        if key in extra:
            data["evidence"][key] = "fixture"
    data.update(extra)
    return Extraction.model_validate(data)


def run(actives, title="", **extra):
    extraction = fixture_extraction(actives, **extra)
    return apply_rules(extraction, REGISTRY, title=title, verify_quotes=False)


# --- step 1: unit normalisation -----------------------------------------------------------


@pytest.mark.parametrize(
    ("compound_id", "amount", "unit", "expected"),
    [
        ("creatine", 5, "g", 5000),  # g -> mg
        ("vitamin_b12", 1, "mg", 1000),  # mg -> mcg
        ("vitamin_k2", 5, "mg", 5000),
        ("vitamin_d3", 25, "mcg", 1000),  # 1 mcg = 40 IU
        ("vitamin_d3", 0.025, "mg", 1000),
        ("vitamin_d3", 4000, "IU", 4000),
        ("magnesium", 200, "mg", 200),
    ],
)
def test_unit_conversion_to_the_compounds_own_unit(compound_id, amount, unit, expected):
    assert convert_amount(amount, unit, REGISTRY.get(compound_id)) == pytest.approx(expected)


def test_iu_is_not_convertible_without_a_declared_rate():
    assert convert_amount(1000, "IU", REGISTRY.get("vitamin_b12")) is None
    product = run([fixture_active("vitamin_b12", "methyl", 1000, "IU")])
    assert product.needs_review and "unit_not_convertible" in product.review_reasons


# --- step 2: servings ---------------------------------------------------------------------


def test_servings_from_pack_multipack_and_units_per_serving():
    product = run(
        [fixture_active("vitamin_d3", "d3", 1000, "IU")], pack_units=90, multipack_count=3
    )
    assert product.servings == 270


def test_servings_conflict_over_five_percent_needs_review():
    product = run(
        [fixture_active("creatine", "monohydrate", 5, "g", "compound")],
        pack_units=500,
        units_per_serving=5,
        servings_stated=80,
    )
    assert "servings_conflict" in product.review_reasons


def test_stated_servings_within_tolerance_is_not_a_conflict():
    product = run(
        [fixture_active("creatine", "monohydrate", 3, "g", "compound")],
        pack_units=1000,
        units_per_serving=3,
        servings_stated=333,
    )
    assert not product.needs_review
    assert product.servings == pytest.approx(333.33, abs=0.01)


def test_missing_units_per_serving_assumes_one_with_lower_confidence():
    extraction = fixture_extraction([fixture_active("zinc", "picolinate", 15, "mg", "elemental")])
    extraction.units_per_serving = None
    product = apply_rules(extraction, REGISTRY, verify_quotes=False)
    assert product.units_per_serving == 1
    assert product.confidence == pytest.approx(0.85)


# --- evidence (§9.3) ----------------------------------------------------------------------


def test_number_without_evidence_is_discarded():
    active = fixture_active("zinc", "picolinate", 15, "mg", "elemental")
    active["evidence"] = {}
    product = run([active])
    assert product.actives[0].amount_per_serving is None
    assert product.needs_review


def test_evidence_quote_must_occur_in_the_label_text():
    active = fixture_active("zinc", "picolinate", 15, "mg", "elemental")
    active["evidence"] = {"amount_per_serving": "15mg"}
    extraction = fixture_extraction([active])
    extraction.evidence = {"pack_units": "120 Capsules"}
    good = apply_rules(extraction, REGISTRY, title="Zinc Picolinate 15mg 120 Capsules")
    bad = apply_rules(extraction, REGISTRY, title="Zinc Picolinate 120 Capsules")
    assert good.actives[0].amount_per_serving == 15
    assert bad.actives[0].amount_per_serving is None


# --- step 3: elemental resolution ---------------------------------------------------------


def test_stated_elemental_used_as_is():
    active = run([fixture_active("magnesium", "bisglycinate", 200, "mg", "elemental")]).actives[0]
    assert (active.amount_per_serving, active.amount_basis) == (200, "stated_elemental")


def test_compound_mass_multiplied_by_factor():
    active = run([fixture_active("magnesium", "oxide", 500, "mg", "compound")]).actives[0]
    assert active.amount_per_serving == pytest.approx(301.5)
    assert active.amount_basis == "estimated_from_compound"


def test_compound_mass_without_a_factor_needs_review():
    product = run([fixture_active("magnesium", "other", 500, "mg", "compound")])
    assert "no_elemental_factor" in product.review_reasons


def test_unclear_with_elemental_default_is_elemental_capped_at_point_eight():
    product = run([fixture_active("zinc", "picolinate", 50, "mg", "unclear")])
    assert product.actives[0].amount_per_serving == 50
    assert product.actives[0].amount_basis == "stated_elemental"
    assert product.confidence <= 0.8
    assert not product.needs_review


def test_magnesium_heuristic_large_amount_is_compound():
    active = run([fixture_active("magnesium", "taurate", 1000, "mg", "unclear")]).actives[0]
    assert active.amount_per_serving == pytest.approx(89)
    assert active.amount_basis == "estimated_from_compound"


def test_magnesium_heuristic_small_amount_is_elemental():
    active = run([fixture_active("magnesium", "citrate", 100, "mg", "unclear")]).actives[0]
    assert (active.amount_per_serving, active.amount_basis) == (100, "stated_elemental")


def test_magnesium_heuristic_middle_amount_needs_review():
    product = run([fixture_active("magnesium", "citrate", 200, "mg", "unclear")])
    assert product.review_reasons == ["ambiguous_basis"]
    assert not product.actives[0].rank_eligible


def test_magnesium_heuristic_does_not_cover_oxide():
    # 500 mg elemental from oxide is physically plausible, so it stays ambiguous.
    product = run([fixture_active("magnesium", "oxide", 500, "mg", "unclear")])
    assert "ambiguous_basis" in product.review_reasons


# --- step 4: omega-3 ----------------------------------------------------------------------


def fixture_omega(components):
    return fixture_active(
        "omega_3", "fish_unspecified", 1000, "mg", "total_oil", components=components
    )


def test_omega3_amount_is_epa_plus_dha():
    components = [
        {"name": "EPA", "amount": 180, "unit": "mg"},
        {"name": "DHA", "amount": 120, "unit": "mg"},
    ]
    active = run([fixture_omega(components)]).actives[0]
    assert (active.amount_per_serving, active.amount_basis) == (300, "stated_component_sum")


def test_omega3_total_only_is_used_with_a_confidence_penalty():
    components = [{"name": "total_omega_3", "amount": 600, "unit": "mg"}]
    product = run([fixture_omega(components)])
    assert product.actives[0].amount_per_serving == 600
    assert product.actives[0].amount_basis == "stated_total"
    assert product.confidence == pytest.approx(0.75)


def test_omega3_oil_mass_only_needs_review():
    product = run([fixture_omega([])])
    assert product.actives[0].amount_per_serving is None
    assert product.review_reasons == ["no_epa_dha"]


# --- step 5: creatine ---------------------------------------------------------------------


def test_creatine_monohydrate_uses_stated_mass():
    active = run([fixture_active("creatine", "monohydrate", 5, "g", "compound")]).actives[0]
    assert (active.amount_per_serving, active.amount_basis) == (5000, "stated_compound")


def test_creatine_prefers_monohydrate_mass_over_creatine_content():
    components = [{"name": "compound_mass", "amount": 5, "unit": "g"}]
    active = run(
        [fixture_active("creatine", "monohydrate", 4.4, "g", "elemental", components=components)]
    ).actives[0]
    assert active.amount_per_serving == 5000


def test_creatine_hcl_has_its_own_class_and_dose():
    active = run([fixture_active("creatine", "hcl", 750, "mg", "compound")]).actives[0]
    assert (active.form_class, active.standard_dose) == ("cr_hcl", 1500)


# --- step 6: ashwagandha ------------------------------------------------------------------


def test_branded_extract_decides_the_class():
    active = run(
        [
            fixture_active(
                "ashwagandha", "generic_extract", 500, "mg", "extract", branded_extract="KSM-66"
            )
        ]
    ).actives[0]
    assert (active.form_id, active.form_class) == ("ksm66", "ash_ksm66")


def test_extract_mass_wins_over_herb_equivalent():
    components = [{"name": "extract_mass", "amount": 500, "unit": "mg"}]
    active = run(
        [
            fixture_active(
                "ashwagandha",
                "generic_extract",
                5000,
                "mg",
                "unclear",
                components=components,
                extract_ratio="10:1",
            )
        ]
    ).actives[0]
    assert (active.amount_per_serving, active.amount_basis) == (500, "stated_extract")


def test_shoden_class_dose_override():
    active = run([fixture_active("ashwagandha", "shoden", 120, "mg", "extract")]).actives[0]
    assert active.standard_dose == 120


# --- step 7: vitamin C --------------------------------------------------------------------


def test_vitamin_c_buffered_forms_share_the_standard_class():
    active = run([fixture_active("vitamin_c", "buffered", 1000, "mg", "elemental")]).actives[0]
    assert (active.form_class, active.amount_per_serving) == ("vc_standard", 1000)


def test_vitamin_c_liposomal_is_its_own_class():
    active = run([fixture_active("vitamin_c", "liposomal", 1000, "mg", "elemental")]).actives[0]
    assert active.form_class == "vc_liposomal"


# --- step 8: B12 / K2 ---------------------------------------------------------------------


def test_b12_and_k2_class_by_form():
    methyl = run([fixture_active("vitamin_b12", "methyl", 1, "mg", "elemental")]).actives[0]
    mk4 = run([fixture_active("vitamin_k2", "mk4", 5, "mg", "elemental")]).actives[0]
    assert (methyl.form_class, methyl.amount_per_serving) == ("b12_methyl", 1000)
    assert (mk4.form_class, mk4.amount_per_serving, mk4.standard_dose) == ("k2_mk4", 5000, 5000)


# --- step 9: multiple actives -------------------------------------------------------------


def test_accepted_cofactor_keeps_product_single_ingredient():
    product = run(
        [fixture_active("zinc", "gluconate", 15, "mg", "elemental")], other_actives=["Copper"]
    )
    assert not product.multi_ingredient and not product.needs_review


def test_unaccepted_other_active_makes_a_combination():
    product = run(
        [fixture_active("zinc", "gluconate", 15, "mg", "elemental")], other_actives=["Selenium"]
    )
    assert product.multi_ingredient


def test_d3_and_k2_accept_each_other_and_both_rank():
    product = run(
        [
            fixture_active("vitamin_k2", "mk7", 75, "mcg", "elemental"),
            fixture_active("vitamin_d3", "d3", 2000, "IU", "elemental"),
        ],
        title="Vitamin D3 + K2 (2000IU / 75µg MK-7) 90 caps",
    )
    assert product.primary.compound_id == "vitamin_d3"  # title order, not list order
    assert not product.multi_ingredient
    assert all(a.rank_eligible for a in product.actives)


def test_zinc_plus_magnesium_is_a_combination_with_zinc_primary():
    product = run(
        [
            fixture_active("magnesium", "other", 150, "mg", "elemental"),
            fixture_active("zinc", "other", 10, "mg", "elemental"),
        ],
        title="ZMA Zinc Magnesium B6 — 90 caps",
        other_actives=["Vitamin B6"],
    )
    assert product.primary.compound_id == "zinc"
    assert product.multi_ingredient
    assert {a.compound_id for a in product.actives} == {"zinc", "magnesium"}


# --- step 11: confidence floor ------------------------------------------------------------


def test_confidence_below_floor_needs_review():
    product = run([fixture_active("zinc", "picolinate", 15, "mg", "elemental")], confidence=0.55)
    assert product.review_reasons == ["low_confidence"]
    assert not product.actives[0].rank_eligible


# --- misc ---------------------------------------------------------------------------------


def test_tested_flag_from_label_claims():
    sport = run(
        [fixture_active("creatine", "monohydrate", 5, "g")], tested_claims=["Informed Sport"]
    )
    other = run([fixture_active("creatine", "monohydrate", 5, "g")], tested_claims=["lab tested"])
    assert (sport.tested_flag, other.tested_flag) == ("informed_sport", "third_party")


def test_unknown_form_needs_review():
    product = run([fixture_active("magnesium", None, 100, "mg", "elemental")])
    assert "form_unknown" in product.review_reasons


def test_component_evidence_may_be_keyed_with_a_components_prefix():
    active = fixture_omega([{"name": "EPA", "amount": 660, "unit": "mg"}])
    active["evidence"] = {"components.EPA": "fixture"}
    assert run([active]).actives[0].amount_per_serving == 660


def test_a_total_the_model_added_up_itself_is_discarded():
    # "EPA 660mg DHA 440mg" -> the model may offer 1100 as the amount; it has no quote, so
    # only the evidenced components count (the model extracts, the code computes).
    components = [
        {"name": "EPA", "amount": 660, "unit": "mg"},
        {"name": "DHA", "amount": 440, "unit": "mg"},
    ]
    active = fixture_omega(components)
    active["amount_per_serving"] = 1100
    del active["evidence"]["amount_per_serving"]
    resolved = run([active]).actives[0]
    assert (resolved.amount_per_serving, resolved.amount_basis) == (1100, "stated_component_sum")
