"""Brief §11: EAN match, key match, new product, id stability, manual overrides."""

import json

from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.normalise.run import content_hash
from pipeline.price.build import Overrides, build

REGISTRY = load_registry()
PROMPT = "fixture-1"
NO_OVERRIDES = Overrides(split=set(), merge={})


def fixture_extraction(amount=200, pack_units=180):
    return {
        "actives": [
            {
                "compound_id": "magnesium",
                "form_id": "bisglycinate",
                "amount_per_serving": amount,
                "amount_unit": "mg",
                "amount_refers_to": "elemental",
                "evidence": {"amount_per_serving": f"{amount}mg magnesium"},
            }
        ],
        "is_single_ingredient": True,
        "pack_units": pack_units,
        "pack_unit_type": "capsule",
        "units_per_serving": 2,
        "confidence": 0.95,
        "evidence": {
            "pack_units": f"{pack_units} Capsules",
            "units_per_serving": "2 capsules provide",
        },
    }


def add_listing(conn, retailer, pid, price, ean=None, brand="Fixture Brand", amount=200, pack=180):
    title = (
        f"Fixture Magnesium Bisglycinate {pack} Capsules - 2 capsules provide {amount}mg magnesium"
    )
    title = f"{title} ({retailer} {pid})"  # distinct text per listing, like real feeds
    hash_ = content_hash(title, None)
    conn.execute(
        "INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, NULL, 'https://example.invalid', NULL,"
        " ?, 1, '2026-09-17', '2026-09-17', ?)",
        (f"{retailer}:{pid}", retailer, pid, ean, brand, title, price, hash_),
    )
    conn.execute(
        "INSERT INTO extractions VALUES (?, ?, 'fixture-model', ?, 0.95, 0, '2026-09-17')",
        (hash_, PROMPT, json.dumps(fixture_extraction(amount, pack))),
    )


def product_of(conn, listing_id):
    return conn.execute(
        "SELECT product_id, match_method FROM offers WHERE listing_id = ?", (listing_id,)
    ).fetchone()


def test_same_ean_is_one_product():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99, ean="0000000000017")
    add_listing(conn, "fixture_b", "9", 13.49, ean="0000000000017", brand="Fixture Brand Ltd")
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    first, second = product_of(conn, "fixture_a:1"), product_of(conn, "fixture_b:9")
    assert first[0] == second[0]
    assert second[1] == "ean"
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 2


def test_same_key_without_ean_is_one_product():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_b", "9", 13.49)
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    assert product_of(conn, "fixture_a:1")[0] == product_of(conn, "fixture_b:9")[0]
    assert product_of(conn, "fixture_b:9")[1] == "key"


def test_different_pack_or_amount_or_brand_stays_separate():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_a", "2", 7.99, pack=60)
    add_listing(conn, "fixture_a", "3", 14.99, amount=100)
    add_listing(conn, "fixture_b", "4", 14.99, brand="Fixture Other")
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    ids = {product_of(conn, f"{r}:{p}")[0] for r, p in [("fixture_a", "1"), ("fixture_a", "2"),
           ("fixture_a", "3"), ("fixture_b", "4")]}  # fmt: skip
    assert len(ids) == 4


def test_product_ids_are_stable_across_runs():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    before = product_of(conn, "fixture_a:1")[0]
    conn.execute("UPDATE listings SET price_gbp = 12.99")
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    assert product_of(conn, "fixture_a:1")[0] == before
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1


def test_split_override_forces_a_separate_product():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_b", "9", 13.49)
    build(conn, REGISTRY, PROMPT, Overrides(split={"fixture_b:9"}, merge={}))
    assert product_of(conn, "fixture_a:1")[0] != product_of(conn, "fixture_b:9")[0]


def test_merge_override_folds_one_product_into_another():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_b", "4", 14.99, brand="Fixture Other")
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    keep, fold = product_of(conn, "fixture_a:1")[0], product_of(conn, "fixture_b:4")[0]
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={fold: keep}))
    assert product_of(conn, "fixture_b:4") == (keep, "manual")


def test_offer_prices_use_each_listings_own_price():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99, ean="0000000000017")
    add_listing(conn, "fixture_b", "9", 9.00, ean="0000000000017")
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    prices = dict(conn.execute("SELECT listing_id, price_per_std_dose FROM offer_prices"))
    assert round(prices["fixture_a:1"], 4) == 0.0833  # the brief's worked example
    assert round(prices["fixture_b:9"], 4) == 0.05


def test_same_key_but_different_other_ingredients_stays_separate():
    # Real case from the seed data: "Zinc 25mg" vs "Zinc 25mg + Copper", same brand and pack.
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 9.69)
    add_listing(conn, "fixture_a", "2", 15.69)
    with_copper = fixture_extraction()
    with_copper["other_actives"] = ["Copper Bisglycinate"]
    with_copper["is_single_ingredient"] = False
    conn.execute(
        "UPDATE extractions SET extracted_json = ? WHERE content_hash ="
        " (SELECT content_hash FROM listings WHERE listing_id = 'fixture_a:2')",
        (json.dumps(with_copper),),
    )
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    assert product_of(conn, "fixture_a:1")[0] != product_of(conn, "fixture_a:2")[0]
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 2


def test_orphaned_products_are_removed():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    conn.execute("DELETE FROM extractions")  # the listing can no longer be read
    build(conn, REGISTRY, PROMPT, NO_OVERRIDES)
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
