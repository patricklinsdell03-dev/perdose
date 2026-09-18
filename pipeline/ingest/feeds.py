"""Affiliate product feeds (brief §7.2): Awin "create-a-feed" CSV and Impact catalogue CSV.

Both are just CSV files (often gzipped) with different column names, so one reader serves
both: columns are mapped **by name** through the retailer's `column_map`, never by position.
A missing required column stops that retailer only. Feed URLs carry credentials, so they
come from environment variables and are never printed.
"""

import csv
import gzip
import io
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
from pydantic import ValidationError

REQUIRED_FIELDS = ("merchant_pid", "title", "url", "price_gbp")

# our field -> their column. Defaults follow each network's published feed columns; a
# retailer's `column_map` in retailers.yml overrides any of them. Confirm on signup.
DEFAULT_COLUMN_MAPS = {
    "awin_csv": {
        "merchant_pid": "merchant_product_id",
        "ean": "ean",
        "brand": "brand_name",
        "title": "product_name",
        "description": "description",
        "url": "aw_deep_link",
        "image_url": "merchant_image_url",
        "price_gbp": "search_price",
        "in_stock": "in_stock",
        "currency": "currency",
    },
    # Awin's newer advertiser-based feeds use Google Shopping column names. `price` carries
    # the currency in the same cell ("22.00 EUR"), so it is read for both fields and split.
    "awin_google_csv": {
        "merchant_pid": "id",
        "ean": "gtin",
        "brand": "brand",
        "title": "title",
        "description": "description",
        "url": "aw_deep_link",
        "image_url": "image_link",
        "price_gbp": "price",
        "in_stock": "availability",
        "currency": "price",
    },
    "impact_csv": {
        "merchant_pid": "CatalogItemId",
        "ean": "Gtin",
        "brand": "Manufacturer",
        "title": "Name",
        "description": "Description",
        "url": "Url",
        "image_url": "ImageUrl",
        "price_gbp": "CurrentPrice",
        "in_stock": "StockAvailability",
        "currency": "Currency",
    },
}
IN_STOCK_WORDS = {"1", "true", "yes", "y", "in stock", "instock", "in_stock", "available"}
OUT_OF_STOCK_WORDS = {"0", "false", "no", "n", "out of stock", "outofstock", "out_of_stock"}


class FeedError(Exception):
    """This retailer's feed cannot be used today. Other retailers carry on (§18)."""


def column_map_for(feed_type: str, overrides: dict[str, str]) -> dict[str, str]:
    return {**DEFAULT_COLUMN_MAPS[feed_type], **overrides}


def fetch_feed_text(url_env: str | None, path: str | None, gzipped: bool) -> str:
    """The feed as text, from a local file (tests, manual downloads) or the URL in `url_env`."""
    if path:
        raw = Path(path).read_bytes()
    else:
        url = os.environ.get(url_env or "")
        if not url:
            raise FeedError(f"environment variable {url_env} is not set")
        try:
            response = httpx.get(url, timeout=120, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as error:
            # Never include the URL: it carries the API key.
            raise FeedError(f"download failed ({type(error).__name__})") from None
        raw = response.content
    if gzipped or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def _in_stock(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if text in OUT_OF_STOCK_WORDS:
        return False
    return True if text in IN_STOCK_WORDS or text == "" else text.isdigit() and int(text) > 0


def _split_price(price: str, currency: str) -> tuple[str, str]:
    """ "22.00 EUR" / "£9.99" / "9.99" + "GBP" -> ("22.00", "EUR"). A sale price is not
    handled here: feeds give the current selling price in `price` unless told otherwise."""
    parts = price.replace(",", "").split()
    if len(parts) == 2 and parts[1].isalpha():
        price, currency = parts[0], parts[1]
    elif len(parts) == 2 and parts[0].isalpha():
        price, currency = parts[1], parts[0]
    if price.startswith("£"):
        price, currency = price[1:], currency or "GBP"
    return price, currency.upper()


def read_feed(text: str, column_map: dict[str, str], run_date: date, listing_model) -> Iterator:
    """Yields (listing | None, problem | None) per row. `listing_model` is RawListing, passed
    in to avoid a circular import."""
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    missing = [f"{ours} (their column '{column_map[ours]}')" for ours in REQUIRED_FIELDS
               if column_map.get(ours) not in columns]  # fmt: skip
    if missing:
        raise FeedError("required columns missing: " + ", ".join(missing))

    for row in reader:

        def get(field, row=row):
            column = column_map.get(field)
            return (row.get(column) or "").strip() if column in columns else ""

        same_cell = column_map.get("currency") == column_map.get("price_gbp")
        price_text, currency = _split_price(get("price_gbp"), "" if same_cell else get("currency"))
        if currency and currency != "GBP":
            yield None, "not_gbp"
            continue
        try:
            yield (
                listing_model.model_validate(
                    {
                        "merchant_pid": get("merchant_pid"),
                        "ean": get("ean"),
                        "brand": get("brand"),
                        "title": get("title"),
                        "description": get("description"),
                        "url": get("url"),
                        "image_url": get("image_url"),
                        "price_gbp": price_text,
                        "in_stock": _in_stock(get("in_stock")),
                        "captured_on": run_date,
                    }
                ),
                None,
            )
        except ValidationError:
            yield None, "invalid_row"
