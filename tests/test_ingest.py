from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.ingest.run import (
    RawListing,
    ingest,
    is_relevant,
    load_exclusions,
    load_retailers,
)

REGISTRY = load_registry()
EXCLUSIONS = load_exclusions()
FIXTURES = Path("tests/fixtures")
RUN_DATE = date(2026, 9, 17)


def fixture_listing(title, **extra):
    data = {
        "merchant_pid": "fixture_1",
        "title": title,
        "url": "https://example.invalid/p/1",
        "price_gbp": "9.99",
        "in_stock": "1",
        "captured_on": "2026-09-17",
    }
    return RawListing.model_validate({**data, **extra})


def fixture_retailers():
    retailers = load_retailers()
    return [r.model_copy(update={"id": "fixture_retailer"}) for r in retailers[:1]]


def run_ingest(conn):
    return ingest(
        conn, REGISTRY, fixture_retailers(), EXCLUSIONS, RUN_DATE, seed_dir=FIXTURES, raw_dir=None
    )


def test_retailers_config_loads():
    assert {r.id for r in load_retailers()} >= {"bulk", "myprotein", "holland_barrett"}


def test_golden_negatives_are_dropped_at_ingest():
    golden = yaml.safe_load(Path("tests/golden/labels.yml").read_text(encoding="utf-8"))
    for negative in golden["negatives"]:
        assert not is_relevant(fixture_listing(negative["title"]), REGISTRY, EXCLUSIONS)


def test_listing_mentioning_a_compound_is_kept():
    assert is_relevant(fixture_listing("Fixture Zinc Picolinate 15mg"), REGISTRY, EXCLUSIONS)
    assert is_relevant(
        fixture_listing("Fixture Night Formula", description="Contains magnesium citrate"),
        REGISTRY,
        EXCLUSIONS,
    )


def test_ean_is_digits_only_and_length_checked():
    assert fixture_listing("x", ean="5060-343 744493").ean == "5060343744493"
    assert fixture_listing("x", ean="12345").ean is None
    assert fixture_listing("x", ean="").ean is None


@pytest.mark.parametrize("bad", [{"price_gbp": "0"}, {"price_gbp": "-1"}, {"url": "not a url"}])
def test_bad_rows_are_rejected(bad):
    with pytest.raises(ValidationError):
        fixture_listing("Fixture Zinc 15mg", **bad)


def test_ingest_counts_and_idempotence():
    conn = connect(":memory:")
    first = run_ingest(conn)
    second = run_ingest(conn)
    assert first == second == {"fixture_retailer": {"kept": 3, "dropped": 2}}
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 3


def test_first_seen_never_changes_but_price_and_last_seen_update():
    conn = connect(":memory:")
    run_ingest(conn)
    listing_id = "fixture_retailer:fixture_zn_1"
    conn.execute(
        "UPDATE listings SET first_seen = '2026-01-01', price_gbp = 1.0 WHERE listing_id = ?",
        (listing_id,),
    )
    run_ingest(conn)
    row = conn.execute(
        "SELECT first_seen, last_seen, price_gbp FROM listings WHERE listing_id = ?", (listing_id,)
    ).fetchone()
    assert row == ("2026-01-01", "2026-09-17", 5.99)
