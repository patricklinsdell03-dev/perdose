"""Amazon Product Advertising API 5 (brief v1.8: Amazon is a core source).

What we take from Amazon: for each product (ASIN) the Buy Box offer — the price a shopper sees
on click-through — plus who sells it and whether Amazon fulfils it. One listing per ASIN.
Amazon's terms: prices are refreshed daily (the cron) and never shown older than that; every
link carries the partner tag (DetailPageURL already does).

Access needs three environment variables (Patrick's Associates account, granted API access
after 3 qualifying sales): AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG. Nothing
in this module prints them. Requests are signed with AWS Signature Version 4.

The parser (`parse_search_response`) is exercised by tests on a fixture in Amazon's documented
response shape; the live call cannot be tested until access exists.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import time
from collections.abc import Iterator
from datetime import date

import httpx
from pydantic import ValidationError

from pipeline.ingest.feeds import FeedError

HOST = "webservices.amazon.co.uk"
REGION = "eu-west-1"
MARKETPLACE = "www.amazon.co.uk"
SERVICE = "ProductAdvertisingAPI"
SEARCH_PATH = "/paapi5/searchitems"
SEARCH_INDEX = "HealthPersonalCare"
RESOURCES = [
    "ItemInfo.Title",
    "ItemInfo.ByLineInfo",
    "ItemInfo.Features",
    "ItemInfo.ExternalIds",
    "ItemInfo.ProductInfo",
    "Images.Primary.Large",
    "Offers.Listings.Price",
    "Offers.Listings.Availability.Type",
    "Offers.Listings.MerchantInfo",
    "Offers.Listings.DeliveryInfo.IsAmazonFulfilled",
    "Offers.Listings.DeliveryInfo.IsPrimeEligible",
]
MAX_PAGES = 3  # 10 items per page; 3 pages per search term
REQUESTS_PER_SECOND = 1  # PA-API's starting quota


class SellerRule:
    """Which third-party sellers count as reliable and reputable (pending Patrick's line;
    DECISIONS.md 2026-09-18). Amazon itself and Amazon-fulfilled sellers always pass."""

    def __init__(self, min_feedback_rating: float = 4.5, min_feedback_count: int = 100):
        self.min_feedback_rating = min_feedback_rating
        self.min_feedback_count = min_feedback_count

    def accepts(self, listing: dict) -> bool:
        merchant = listing.get("MerchantInfo") or {}
        delivery = listing.get("DeliveryInfo") or {}
        if delivery.get("IsAmazonFulfilled") or (merchant.get("Name") or "").lower() == "amazon":
            return True
        rating = merchant.get("FeedbackRating")
        count = merchant.get("FeedbackCount")
        return (
            rating is not None
            and count is not None
            and rating >= self.min_feedback_rating
            and count >= self.min_feedback_count
        )


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signed_headers(payload: str, access_key: str, secret_key: str, now: dt.datetime) -> dict:
    """AWS Signature Version 4 for a PA-API POST. Pure function so it can be tested."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    headers = {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        "host": HOST,
        "x-amz-date": amz_date,
        "x-amz-target": "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
    }
    signed = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        ["POST", SEARCH_PATH, "", canonical_headers, signed, payload_hash]
    )
    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    k_date = _sign(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _sign(k_date, REGION)
    k_service = _sign(k_region, SERVICE)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed}, Signature={signature}"
    )
    return headers


def search_payload(keywords: str, partner_tag: str, page: int) -> dict:
    return {
        "Keywords": keywords,
        "SearchIndex": SEARCH_INDEX,
        "ItemPage": page,
        "ItemCount": 10,
        "Resources": RESOURCES,
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Marketplace": MARKETPLACE,
    }


def _text(node, *path):
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def parse_search_response(
    data: dict, run_date: date, listing_model, seller_rule: SellerRule | None = None
) -> Iterator:
    """Yields (listing | None, problem | None) per item, like feeds.read_feed."""
    rule = seller_rule or SellerRule()
    for item in _text(data, "SearchResult", "Items") or []:
        offers = _text(item, "Offers", "Listings") or []
        if not offers:
            yield None, "no_offer"
            continue
        offer = offers[0]  # the Buy Box
        price = _text(offer, "Price")
        if not price or price.get("Currency") != "GBP" or price.get("Amount") is None:
            yield None, "not_gbp"
            continue
        if not rule.accepts(offer):
            yield None, "seller_rule"
            continue
        features = _text(item, "ItemInfo", "Features", "DisplayValues") or []
        eans = _text(item, "ItemInfo", "ExternalIds", "EANs", "DisplayValues") or []
        try:
            yield (
                listing_model.model_validate(
                    {
                        "merchant_pid": item.get("ASIN"),
                        "ean": eans[0] if eans else None,
                        "brand": _text(item, "ItemInfo", "ByLineInfo", "Brand", "DisplayValue"),
                        "title": _text(item, "ItemInfo", "Title", "DisplayValue"),
                        "description": " | ".join(features),
                        "url": item.get("DetailPageURL"),
                        "image_url": _text(item, "Images", "Primary", "Large", "URL"),
                        "price_gbp": price["Amount"],
                        "in_stock": _text(offer, "Availability", "Type") in (None, "Now"),
                        "captured_on": run_date,
                    }
                ),
                None,
            )
        except ValidationError:
            yield None, "invalid_row"


def _credentials() -> tuple[str, str, str]:
    values = [
        os.environ.get(k) for k in ("AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_PARTNER_TAG")
    ]
    if not all(values):
        raise FeedError("AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY / AMAZON_PARTNER_TAG not all set")
    return values[0], values[1], values[2]  # type: ignore[return-value]


def search(keywords: str, page: int, client: httpx.Client | None = None) -> dict:
    """One SearchItems call. Raises FeedError on any HTTP problem (never echoing keys)."""
    access_key, secret_key, partner_tag = _credentials()
    payload = json.dumps(search_payload(keywords, partner_tag, page))
    headers = signed_headers(payload, access_key, secret_key, dt.datetime.now(dt.UTC))
    try:
        response = (client or httpx).post(
            f"https://{HOST}{SEARCH_PATH}", content=payload, headers=headers, timeout=30
        )
    except httpx.HTTPError as error:
        raise FeedError(f"Amazon request failed ({type(error).__name__})") from None
    if response.status_code == 429:
        raise FeedError("Amazon rate limit hit (429); try again later")
    if response.status_code >= 400:
        raise FeedError(f"Amazon returned HTTP {response.status_code}")
    return response.json()


def search_terms(registry) -> list[str]:
    """One search per compound name plus its most specific aliases (up to three)."""
    terms = []
    for compound in registry.compounds:
        terms.append(compound.name)
        terms += [a for a in compound.aliases if " " in a][:2]  # multi-word aliases are forms
    return list(dict.fromkeys(t.lower() for t in terms))


def fetch_all(registry, run_date: date, listing_model, seller_rule: SellerRule | None = None):
    """Every search term, MAX_PAGES pages each, at PA-API's rate. Yields like read_feed.
    Duplicate ASINs across searches are collapsed by the caller's upsert."""
    seen: set[str] = set()
    with httpx.Client() as client:
        for term in search_terms(registry):
            for page in range(1, MAX_PAGES + 1):
                data = search(term, page, client)
                time.sleep(1 / REQUESTS_PER_SECOND)
                got = 0
                for listing, problem in parse_search_response(
                    data, run_date, listing_model, seller_rule
                ):
                    got += 1
                    if listing is not None and listing.merchant_pid in seen:
                        continue
                    if listing is not None:
                        seen.add(listing.merchant_pid)
                    yield listing, problem
                if got < 10:
                    break
