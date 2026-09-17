"""Brief §5.3 / §15: export shape, ranking order, unverified separation, size guards."""

import json

import pytest

from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.export import run as export_module
from pipeline.ingest.run import load_retailers
from pipeline.price.build import Overrides, build
from tests.test_dedupe import PROMPT, add_listing, fixture_extraction

REGISTRY = load_registry()
RETAILERS = [
    r.model_copy(update={"id": f"fixture_{x}"})
    for r, x in zip(load_retailers()[:2], "ab", strict=True)
]


@pytest.fixture
def exported(monkeypatch):
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_b", "2", 9.00, brand="Fixture Other")
    add_listing(conn, "fixture_b", "3", 5.00, brand="Fixture Third", amount=150)
    # Make listing 3 ambiguous: an unqualified mid-range amount must never be ranked.
    ambiguous = fixture_extraction(150)
    ambiguous["actives"][0]["amount_refers_to"] = "unclear"
    conn.execute(
        "UPDATE extractions SET extracted_json = ? WHERE content_hash ="
        " (SELECT content_hash FROM listings WHERE listing_id = 'fixture_b:3')",
        (json.dumps(ambiguous),),
    )
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))

    files: dict[str, object] = {}

    def fake_write(path, data):
        files[path.as_posix().split("data/export/")[-1]] = data
        return len(json.dumps(data))

    monkeypatch.setattr(export_module, "_write", fake_write)
    monkeypatch.setattr(export_module, "_clear_compound_files", lambda out_dir: None)
    stats = export_module.export(conn, REGISTRY, RETAILERS, PROMPT)
    return files, stats


def test_files_written(exported):
    files, stats = exported
    assert set(files) == {"compounds.json", "compounds/magnesium.json", "index.json", "meta.json"}
    assert stats["products"] == 3


def test_ranked_sorted_by_price_per_dose_and_unverified_kept_apart(exported):
    files, _ = exported
    glycinate = next(
        c for c in files["compounds/magnesium.json"]["classes"] if c["id"] == "mg_glycinate"
    )
    prices = [offer["price_per_std_dose"] for offer in glycinate["ranked"]]
    assert prices == sorted(prices) and len(prices) == 2
    assert [o["listing_id"] for o in glycinate["unverified"]] == ["fixture_b:3"]
    assert glycinate["unverified"][0]["price_per_std_dose"] is None
    assert glycinate["unverified"][0]["review_reasons"][0]["code"] == "ambiguous_basis"


def test_rows_carry_the_working(exported):
    files, _ = exported
    offer = files["compounds/magnesium.json"]["classes"][0]["ranked"][0]
    assert offer["evidence"]["amount_per_serving"] == "200mg magnesium"
    assert offer["amount_basis"] == "stated_elemental"
    assert offer["pack"]["servings"] == 90
    assert offer["url"].startswith("https://")


def test_index_and_meta(exported):
    files, _ = exported
    card = files["index.json"][0]
    glycinate = next(c for c in card["classes"] if c["id"] == "mg_glycinate")
    assert (card["id"], card["product_count"], card["retailer_count"]) == ("magnesium", 3, 2)
    assert glycinate["from_price_per_std_dose"] == pytest.approx(0.05)
    assert glycinate["retailer_count"] == 2
    assert files["meta.json"]["counts"]["classes"]["mg_glycinate"] == 2
    assert len(files["meta.json"]["retailers"]) == 2


def test_rules_export_has_no_internal_notes(exported):
    files, _ = exported
    assert "note" not in json.dumps(files["compounds.json"])
    assert len(files["compounds.json"]) == 10


def test_size_guard(exported, monkeypatch):
    monkeypatch.setattr(export_module, "MAX_TOTAL_BYTES", 10)
    monkeypatch.setattr(export_module, "_write", lambda path, data: 1000)
    monkeypatch.setattr(export_module, "_clear_compound_files", lambda out_dir: None)
    conn = connect(":memory:")
    with pytest.raises(export_module.ExportTooLarge):
        export_module.export(conn, REGISTRY, RETAILERS, PROMPT)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Suitable for: vegetarians and vegans.", ["vegan", "vegetarian"]),
        ("Vitamin D3 Softgels - 180Softgels - Non-Vegan | Not suitable for vegetarians.", []),
        ("Suitable For | Halal, Vegan, Vegetarian", ["vegan", "vegetarian"]),
        ("Sugar Free Gummies, gluten-free", ["gluten-free", "sugar-free"]),
        ("Vegetarian capsule. Not suitable for vegans.", ["vegetarian"]),
        ("Magnesium Citrate 90 Tablets", []),
    ],
)
def test_claimed_dietary_flags(text, expected):
    assert export_module.claimed_flags(text) == expected


def test_classes_carry_site_label_and_slug(exported):
    files, _ = exported
    glycinate = files["compounds/magnesium.json"]["classes"][0]
    assert (glycinate["label"], glycinate["slug"]) == ("Bisglycinate (glycinate)", "bisglycinate")
    assert files["index.json"][0]["classes"][0]["slug"] == "bisglycinate"
