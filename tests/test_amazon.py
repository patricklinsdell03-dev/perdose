"""Amazon PA-API adapter: parsing on a fixture in Amazon's documented shape, the seller rule,
and the request signature (pure function, deterministic)."""

import datetime as dt
import json
from datetime import date
from pathlib import Path

from pipeline.compounds import load_registry
from pipeline.ingest import amazon
from pipeline.ingest.run import RawListing

FIXTURE = json.loads(Path("tests/fixtures/fixture_amazon_search.json").read_text(encoding="utf-8"))
RUN_DATE = date(2026, 9, 18)


def test_parse_takes_the_buy_box_and_rejects_bad_offers():
    results = list(amazon.parse_search_response(FIXTURE, RUN_DATE, RawListing))
    listings = [x for x, _ in results if x]
    problems = [p for _, p in results if p]
    assert [x.merchant_pid for x in listings] == ["B0FIXTURE01"]
    assert sorted(problems) == ["no_offer", "not_gbp", "seller_rule"]
    first = listings[0]
    assert (first.price_gbp, first.ean, first.brand) == (14.99, "0000000000048", "Fixture")
    assert first.description == "2 capsules provide 200mg elemental magnesium | 180 capsules"
    assert "tag=fixture-21" in first.url and first.in_stock is True


def test_seller_rule_accepts_amazon_and_amazon_fulfilled_regardless_of_rating():
    rule = amazon.SellerRule()
    assert rule.accepts({"MerchantInfo": {"Name": "Amazon"}})
    assert rule.accepts(
        {
            "MerchantInfo": {"Name": "x", "FeedbackRating": 2.0, "FeedbackCount": 5},
            "DeliveryInfo": {"IsAmazonFulfilled": True},
        }
    )
    assert not rule.accepts(
        {"MerchantInfo": {"Name": "x", "FeedbackRating": 4.9, "FeedbackCount": 50}}
    )
    assert amazon.SellerRule(min_feedback_count=10).accepts(
        {"MerchantInfo": {"Name": "x", "FeedbackRating": 4.9, "FeedbackCount": 50}}
    )


def test_signature_is_deterministic_and_well_formed():
    payload = json.dumps(amazon.search_payload("magnesium", "fixture-21", 1))
    when = dt.datetime(2026, 9, 18, 12, 0, 0, tzinfo=dt.UTC)
    a = amazon.signed_headers(payload, "AKIAFIXTURE", "fixturesecret", when)
    b = amazon.signed_headers(payload, "AKIAFIXTURE", "fixturesecret", when)
    assert a == b
    auth = a["authorization"]
    scope = "AKIAFIXTURE/20260918/eu-west-1/ProductAdvertisingAPI/aws4_request"
    assert auth.startswith(f"AWS4-HMAC-SHA256 Credential={scope}, ")
    assert "SignedHeaders=content-encoding;content-type;host;x-amz-date;x-amz-target" in auth
    assert len(auth.rsplit("Signature=", 1)[1]) == 64
    assert "fixturesecret" not in json.dumps(a)


def test_search_terms_cover_every_compound_without_duplicates():
    terms = amazon.search_terms(load_registry())
    assert "magnesium" in terms and len(terms) == len(set(terms))
    assert len(terms) >= 90
