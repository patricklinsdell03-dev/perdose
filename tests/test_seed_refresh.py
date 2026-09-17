"""Seed price refresh: only price, stock and capture date may change, and a bad row
changes nothing."""

from datetime import date

import pytest

from pipeline import seed_refresh
from pipeline.seed_refresh import SeedRefreshError, apply, checklist, read_rows, stale_counts

HEADER = "merchant_pid,ean,brand,title,description,url,image_url,price_gbp,in_stock,captured_on\n"
SEEDS = {
    "fixture_shop": HEADER
    + 'F1,,Fixture,Fixture Zinc 60 Tablets,"Directions: 1 daily, with food",https://example.test/f1,,10.00,1,2026-01-10\n'
    + "F2,,Fixture,Fixture Zinc 120 Tablets,Directions: 1 daily,https://example.test/f2,,18.00,1,2026-01-02\n",
    "fixture_other": HEADER
    + "F1,,Fixture,Fixture Iron 30 Tablets,Directions: 1 daily,https://example.test/o1,,5.50,1,2026-01-05\n",
}
TODAY = date(2026, 1, 20)


def filled(edits: dict[tuple[str, str], tuple[str, str]]) -> str:
    fieldnames, rows = read_rows(checklist(SEEDS))
    for row in rows:
        price, stock = edits.get((row["retailer_id"], row["merchant_pid"]), ("", ""))
        row["new_price_gbp"], row["new_in_stock"] = price, stock
    return seed_refresh.write_rows(fieldnames, rows)


def test_checklist_lists_every_row_oldest_first_with_blank_answers():
    _, rows = read_rows(checklist(SEEDS))
    assert [r["captured_on"] for r in rows] == ["2026-01-02", "2026-01-05", "2026-01-10"]
    assert all(r["new_price_gbp"] == "" and r["new_in_stock"] == "" for r in rows)
    assert rows[0]["url"] == "https://example.test/f2"


def test_stale_counts_use_the_fourteen_day_rule():
    assert stale_counts(SEEDS, TODAY) == {"fixture_shop": 1, "fixture_other": 1}


def test_apply_changes_only_price_stock_and_date_of_the_filled_rows():
    changed, counts = apply(filled({("fixture_shop", "F1"): ("£9.49", "")}), SEEDS, TODAY)
    assert counts == {"updated": 1, "blank": 2}
    assert set(changed) == {"fixture_shop"}
    _, rows = read_rows(changed["fixture_shop"])
    assert rows[0]["price_gbp"] == "9.49"
    assert rows[0]["captured_on"] == "2026-01-20"
    assert rows[0]["description"] == "Directions: 1 daily, with food"
    assert rows[1] == read_rows(SEEDS["fixture_shop"])[1][1]


def test_same_product_id_at_two_retailers_is_not_confused():
    changed, _ = apply(filled({("fixture_other", "F1"): ("6.00", "0")}), SEEDS, TODAY)
    assert set(changed) == {"fixture_other"}
    row = read_rows(changed["fixture_other"])[1][0]
    assert (row["price_gbp"], row["in_stock"]) == ("6.00", "0")


def test_stock_only_update_keeps_the_price():
    changed, _ = apply(filled({("fixture_shop", "F2"): ("", "no")}), SEEDS, TODAY)
    row = read_rows(changed["fixture_shop"])[1][1]
    assert (row["price_gbp"], row["in_stock"], row["captured_on"]) == ("18.00", "0", "2026-01-20")


@pytest.mark.parametrize("price", ["abc", "0", "9.999", "99.00", "1.00"])
def test_bad_or_implausible_prices_are_refused(price):
    with pytest.raises(SeedRefreshError):
        apply(filled({("fixture_shop", "F1"): (price, "")}), SEEDS, TODAY)


def test_bad_stock_value_and_unknown_rows_are_refused():
    with pytest.raises(SeedRefreshError):
        apply(filled({("fixture_shop", "F1"): ("", "maybe")}), SEEDS, TODAY)
    unknown = filled({("fixture_shop", "F1"): ("9.00", "")}).replace(
        ",F1,Fixture Zinc", ",F9,Fixture Zinc"
    )
    with pytest.raises(SeedRefreshError):
        apply(unknown, SEEDS, TODAY)


def test_real_seed_files_produce_a_checklist():
    seeds = seed_refresh.load_seeds()
    _, rows = read_rows(checklist(seeds))
    assert len(rows) == sum(len(read_rows(text)[1]) for text in seeds.values())
    assert all(r["url"].startswith("https://") for r in rows)
