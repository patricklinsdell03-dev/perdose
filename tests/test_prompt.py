from pipeline.compounds import load_registry
from pipeline.normalise.prompt import (
    MAX_CANDIDATES,
    build_user_message,
    find_candidates,
    trim_description,
)

REGISTRY = load_registry()


def ids(title, description=""):
    return [c.id for c in find_candidates(REGISTRY, title, description)]


def test_candidates_come_from_aliases_in_mention_order():
    assert ids("ZMA Zinc Magnesium B6 — 90 caps") == ["zinc", "magnesium", "vitamin_b6"]
    assert ids("Vit D 1000IU 90 Tablets") == ["vitamin_d3"]
    assert ids("Fixture Yoga Mat") == []


def test_aliases_match_whole_words_only():
    assert ids("Imaging Magazine 500mg") == []  # "mag" inside other words
    assert ids("Glycinate 500mg capsules") == []  # "500mg" must not match the alias "mg ..."


def test_candidates_are_capped():
    everything = " ".join(c.name for c in REGISTRY.compounds)
    assert len(ids(everything)) <= MAX_CANDIDATES


def test_user_message_lists_only_candidate_forms():
    candidates = find_candidates(REGISTRY, "Zinc Picolinate 15mg")
    message = build_user_message(candidates, "Zinc Picolinate 15mg", "desc", 3000)
    assert "form_id: picolinate" in message
    assert "monohydrate" not in message
    assert message.index("TITLE:") < message.index("DESCRIPTION:")


def test_long_description_keeps_the_nutrition_section():
    description = "x" * 5000 + " Nutritional information: magnesium 200mg per serving " + "y" * 5000
    trimmed = trim_description(description, 3000)
    assert len(trimmed) == 3000
    assert "magnesium 200mg per serving" in trimmed


def test_short_description_is_untouched():
    assert trim_description("short", 3000) == "short"


def test_alias_exclusions_stop_excipients_and_other_salts_becoming_candidates():
    assert ids("Calcium HMB Powder 250g") == ["hmb"]
    assert ids("Zinc Picolinate 50mg — contains magnesium stearate") == ["zinc"]
    assert ids("Calcium Citrate 1000mg 90 Tablets") == ["calcium"]
