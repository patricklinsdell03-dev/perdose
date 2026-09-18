"""Brief Â§7.2: affiliate feeds are mapped by column name, reject non-GBP rows, and a broken
feed stops only its own retailer."""

import gzip
from datetime import date
from pathlib import Path

import pytest

from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.ingest import feeds
from pipeline.ingest.run import Feed, RawListing, Retailer, Shipping, ingest, load_exclusions

FEED = Path("tests/fixtures/fixture_awin_feed.csv")
RUN_DATE = date(2026, 9, 17)
AWIN_MAP = feeds.column_map_for("awin_csv", {})


def fixture_retailer(**feed):
    return Retailer(
        id="fixture_feed",
        name="Fixture Feed",
        enabled=True,
        feed=Feed(type="awin_csv", **feed),
        shipping=Shipping(rule="unknown"),
    )


def read(text, column_map=AWIN_MAP):
    return list(feeds.read_feed(text, column_map, RUN_DATE, RawListing))


def test_rows_are_mapped_by_column_name():
    results = read(FEED.read_text(encoding="utf-8"))
    listings = [listing for listing, _ in results if listing]
    first = listings[0]
    assert (first.merchant_pid, first.price_gbp, first.ean) == ("fixture_f1", 8.49, "0000000000024")
    assert first.url == "https://example.invalid/aw/1"
    assert first.captured_on == RUN_DATE
    assert listings[1].price_gbp == 5.99 and listings[1].in_stock is False  # "£5.99", stock 0


def test_column_order_does_not_matter():
    lines = FEED.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    assert header[0] == "aw_deep_link"
    text = "product_name,search_price,merchant_product_id,aw_deep_link\nFixture Zinc 15mg,4.50,z9,https://example.invalid/z\n"
    ((listing, problem),) = read(text)
    assert problem is None and listing.title == "Fixture Zinc 15mg"


def test_non_gbp_and_invalid_rows_are_rejected_not_fatal():
    problems = [problem for _, problem in read(FEED.read_text(encoding="utf-8")) if problem]
    assert sorted(problems) == ["invalid_row", "not_gbp"]


def test_missing_required_column_stops_the_feed_with_a_clear_message():
    with pytest.raises(feeds.FeedError, match="price_gbp \\(their column 'search_price'\\)"):
        read("product_name,merchant_product_id,aw_deep_link\nx,1,https://example.invalid\n")


def test_retailer_column_map_overrides_the_default():
    column_map = feeds.column_map_for("awin_csv", {"price_gbp": "store_price"})
    text = "product_name,store_price,merchant_product_id,aw_deep_link\nFixture Zinc 15mg,4.50,z9,https://example.invalid/z\n"
    ((listing, _),) = read(text, column_map)
    assert listing.price_gbp == 4.5


def test_gzipped_feeds_are_detected(monkeypatch):
    payload = gzip.compress(FEED.read_bytes())
    monkeypatch.setattr(Path, "read_bytes", lambda self: payload)
    assert "Fixture Magnesium Citrate" in feeds.fetch_feed_text(None, "anything.csv.gz", False)


def test_missing_url_variable_is_a_feed_error_that_never_shows_a_url(monkeypatch):
    monkeypatch.delenv("FIXTURE_FEED_URL", raising=False)
    with pytest.raises(feeds.FeedError, match="FIXTURE_FEED_URL is not set"):
        feeds.fetch_feed_text("FIXTURE_FEED_URL", None, False)


def test_ingest_from_a_feed_keeps_relevant_gbp_rows_only():
    conn = connect(":memory:")
    counts = ingest(
        conn, load_registry(), [fixture_retailer(path=FEED.as_posix())], load_exclusions(),
        RUN_DATE, raw_dir=None,
    )  # fmt: skip
    assert counts == {"fixture_feed": {"kept": 2, "dropped": 1, "not_gbp": 1, "invalid_row": 1}}
    rows = conn.execute(
        "SELECT listing_id, last_seen, in_stock FROM listings ORDER BY 1"
    ).fetchall()
    assert rows == [
        ("fixture_feed:fixture_f1", "2026-09-17", 1),
        ("fixture_feed:fixture_f2", "2026-09-17", 0),
    ]


def test_a_broken_feed_is_skipped_and_others_carry_on(capsys):
    conn = connect(":memory:")
    broken = fixture_retailer(url_env="FIXTURE_UNSET_FEED_URL").model_copy(
        update={"id": "fixture_broken"}
    )
    counts = ingest(
        conn, load_registry(), [broken, fixture_retailer(path=FEED.as_posix())], load_exclusions(),
        RUN_DATE, raw_dir=None,
    )  # fmt: skip
    assert "fixture_broken" not in counts and counts["fixture_feed"]["kept"] == 2
    assert "WARNING: fixture_broken" in capsys.readouterr().out


def test_feed_listings_unseen_for_14_days_are_hidden():
    conn = connect(":memory:")
    retailers = [fixture_retailer(path=FEED.as_posix())]
    ingest(conn, load_registry(), retailers, load_exclusions(), date(2026, 9, 1), raw_dir=None)
    conn.execute("UPDATE listings SET in_stock = 1")
    gone = retailers[0].model_copy(update={"feed": Feed(type="awin_csv", url_env="FIXTURE_UNSET")})
    ingest(conn, load_registry(), [gone], load_exclusions(), date(2026, 9, 20), raw_dir=None)
    assert conn.execute("SELECT SUM(in_stock) FROM listings").fetchone()[0] == 0


def test_google_format_feed_splits_price_and_currency():
    text = Path("tests/fixtures/fixture_awin_google_feed.csv").read_text(encoding="utf-8")
    results = read(text, feeds.column_map_for("awin_google_csv", {}))
    listings = [listing for listing, _ in results if listing]
    problems = [problem for _, problem in results if problem]
    assert problems == ["not_gbp"]  # the 9.00 EUR row
    assert [(x.merchant_pid, x.price_gbp, x.in_stock) for x in listings] == [
        ("g1", 12.5, True),
        ("g3", 4.99, False),
    ]
    assert listings[0].ean == "0000000000031" and listings[0].url == "https://example.invalid/aw/g1"


@pytest.mark.parametrize(
    ("price", "currency", "expected"),
    [
        ("22.00 EUR", "", ("22.00", "EUR")),
        ("GBP 1,299.00", "", ("1299.00", "GBP")),
        ("£9.99", "", ("9.99", "GBP")),
        ("9.99", "gbp", ("9.99", "GBP")),
        ("9.99", "", ("9.99", "")),
    ],
)
def test_split_price(price, currency, expected):
    assert feeds._split_price(price, currency) == expected


def test_shared_feed_is_split_by_advertiser_id():
    text = (
        "advertiser_id,id,title,aw_deep_link,price,availability\n"
        "11,a1,Fixture Zinc 15mg,https://example.invalid/a1,4.00 GBP,in_stock\n"
        "22,b1,Fixture Iron 14mg,https://example.invalid/b1,5.00 GBP,in_stock\n"
    )
    column_map = feeds.column_map_for("awin_google_csv", {})
    mine = [
        x for x, _ in feeds.read_feed(text, column_map, RUN_DATE, RawListing, advertiser_id="22")
    ]
    assert [x.merchant_pid for x in mine] == ["b1"]
    everyone = [x for x, _ in feeds.read_feed(text, column_map, RUN_DATE, RawListing)]
    assert len(everyone) == 2
    with pytest.raises(feeds.FeedError, match="split on"):
        list(
            feeds.read_feed(
                "id,title,aw_deep_link,price\n", column_map, RUN_DATE, RawListing, advertiser_id="1"
            )
        )
