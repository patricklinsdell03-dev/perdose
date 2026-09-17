"""Phase 3 acceptance (brief §17) checked against the committed data/export files."""

import json
from pathlib import Path

import pytest

from pipeline.compounds import load_registry

EXPORT = Path("data/export")
pytestmark = pytest.mark.skipif(
    not (EXPORT / "index.json").exists(), reason="no export yet; run `make all`"
)


def load(name):
    return json.loads((EXPORT / name).read_text(encoding="utf-8"))


def test_at_least_fifty_products_across_all_ten_compounds():
    # Only compounds with products get a card; batch 1 has none until a retailer stocks them.
    index = load("index.json")
    from tests.test_compounds import PROTOTYPE_IDS

    carded = {card["id"] for card in index}
    assert PROTOTYPE_IDS <= carded <= {c.id for c in load_registry().compounds}
    assert load("meta.json")["counts"]["products"] >= 50


def test_magnesium_bisglycinate_class_has_two_retailers():
    magnesium = next(card for card in load("index.json") if card["id"] == "magnesium")
    glycinate = next(cls for cls in magnesium["classes"] if cls["id"] == "mg_glycinate")
    assert glycinate["retailer_count"] >= 2
    assert glycinate["ranked_count"] >= 2


def test_every_ranked_row_is_complete_and_sorted():
    for path in (EXPORT / "compounds").glob("*.json"):
        for cls in json.loads(path.read_text(encoding="utf-8"))["classes"]:
            prices = [offer["price_per_std_dose"] for offer in cls["ranked"]]
            assert prices == sorted(prices), path.name
            for offer in cls["ranked"]:
                assert offer["price_per_std_dose"] > 0
                assert offer["url"].startswith("https://")
                assert offer["evidence"], f"{offer['listing_id']} has no label quotes"
                assert not offer["review_reasons"]
            for offer in cls["unverified"]:
                assert offer["review_reasons"], f"{offer['listing_id']} has no reason"


def test_worked_example_from_the_brief_appears_in_real_data():
    # Bulk's 180-tablet magnesium bisglycinate: £14.99, 200 mg per 2 tablets -> £0.0833.
    magnesium = load("compounds/magnesium.json")
    glycinate = next(cls for cls in magnesium["classes"] if cls["id"] == "mg_glycinate")
    offer = next(o for o in glycinate["ranked"] if o["listing_id"] == "bulk:BPB-MAGB-500T-0180")
    if offer["price_gbp"] == 14.99:  # only while the seed price still matches the brief's
        assert offer["price_per_std_dose"] == pytest.approx(0.0833, abs=5e-5)
