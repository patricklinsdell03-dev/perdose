"""`make ingest` (brief §7.4, §8): seed CSVs / feeds -> data/raw/<retailer>/<date>.jsonl -> DB.

Seed CSVs are treated exactly like feeds: every source yields the same RawListing rows, so
swapping in a live feed later only means adding an adapter.
"""

import csv
import re
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipeline.compounds import Registry
from pipeline.normalise.prompt import find_candidates
from pipeline.normalise.rules import find_term
from pipeline.normalise.run import content_hash

RETAILERS_PATH = Path("config/retailers.yml")
INGEST_CONFIG_PATH = Path("config/ingest.yml")
SEED_DIR = Path("data/seed")
RAW_DIR = Path("data/raw")
INACTIVE_AFTER_DAYS = 14


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Feed(_Model):
    type: Literal["seed_csv", "awin_csv", "impact_csv"]
    url_env: str | None = None
    gzip: bool = False
    column_map: dict[str, str] = {}


class Shipping(_Model):
    rule: Literal["free_over", "flat", "unknown"]
    threshold_gbp: float | None = None
    flat_gbp: float | None = None


class Link(_Model):
    template: str = "{url}"


class Retailer(_Model):
    id: str
    name: str
    enabled: bool
    feed: Feed
    link: Link = Link()
    shipping: Shipping
    notes: str | None = None


class RawListing(_Model):
    """One row as received from a retailer, before any interpretation."""

    merchant_pid: str = Field(min_length=1)
    ean: str | None = None
    brand: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    url: str = Field(pattern=r"^https?://")
    image_url: str | None = None
    price_gbp: float = Field(gt=0)
    in_stock: bool
    captured_on: date

    @field_validator("ean", "brand", "description", "image_url", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("ean")
    @classmethod
    def _ean_digits(cls, value):
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        return digits if len(digits) in (8, 12, 13, 14) else None

    @field_validator("price_gbp")
    @classmethod
    def _two_dp(cls, value):
        return round(value, 2)


def load_retailers(path: Path = RETAILERS_PATH) -> list[Retailer]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    retailers = [Retailer.model_validate(r) for r in data["retailers"]]
    ids = [r.id for r in retailers]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate retailer ids")
    return retailers


def load_exclusions(path: Path = INGEST_CONFIG_PATH) -> list[str]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["exclude_title_terms"]


def read_seed_csv(path: Path) -> Iterator[RawListing]:
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            yield RawListing.model_validate(row)


def is_relevant(listing: RawListing, registry: Registry, exclusions: list[str]) -> bool:
    """§7.4: mentions at least one compound alias, and is not an excluded product type."""
    if any(find_term(term, listing.title) is not None for term in exclusions):
        return False
    return bool(find_candidates(registry, listing.title, listing.description or ""))


def upsert_listing(conn: sqlite3.Connection, retailer: Retailer, listing: RawListing) -> None:
    seen = listing.captured_on.isoformat()
    conn.execute(
        """
        INSERT INTO listings (listing_id, retailer_id, merchant_pid, ean, brand, title,
            description, url, image_url, price_gbp, in_stock, first_seen, last_seen, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            ean = excluded.ean, brand = excluded.brand, title = excluded.title,
            description = excluded.description, url = excluded.url,
            image_url = excluded.image_url, price_gbp = excluded.price_gbp,
            in_stock = excluded.in_stock, last_seen = excluded.last_seen,
            content_hash = excluded.content_hash
        """,  # first_seen is deliberately absent from the UPDATE: it never changes.
        (
            f"{retailer.id}:{listing.merchant_pid}",
            retailer.id,
            listing.merchant_pid,
            listing.ean,
            listing.brand,
            listing.title,
            listing.description,
            retailer.link.template.format(url=listing.url),
            listing.image_url,
            listing.price_gbp,
            int(listing.in_stock),
            seen,
            seen,
            content_hash(listing.title, listing.description),
        ),
    )


def ingest(
    conn: sqlite3.Connection,
    registry: Registry,
    retailers: list[Retailer],
    exclusions: list[str],
    run_date: date,
    only: str | None = None,
    seed_dir: Path = SEED_DIR,
    raw_dir: Path | None = RAW_DIR,
) -> dict[str, dict[str, int]]:
    """Returns kept/dropped counts per retailer. A failing retailer is skipped, not fatal."""
    counts: dict[str, dict[str, int]] = {}
    for retailer in retailers:
        if not retailer.enabled or (only and retailer.id != only):
            continue
        if retailer.feed.type != "seed_csv":
            print(f"WARNING: {retailer.id}: feed type {retailer.feed.type} arrives in Phase 6")
            continue
        source = seed_dir / f"{retailer.id}.csv"
        if not source.exists():
            print(f"WARNING: {retailer.id}: {source.as_posix()} not found; skipped")
            continue

        listings = list(read_seed_csv(source))
        kept = [item for item in listings if is_relevant(item, registry, exclusions)]
        if raw_dir is not None:  # idempotent: re-running overwrites that day's file
            raw_file = raw_dir / retailer.id / f"{run_date.isoformat()}.jsonl"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            lines = [item.model_dump_json() for item in listings]
            raw_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for listing in kept:
            upsert_listing(conn, retailer, listing)
        counts[retailer.id] = {"kept": len(kept), "dropped": len(listings) - len(kept)}

    # A feed listing not seen for 14 days is hidden. Seed rows are dated by hand
    # (`captured_on`), so they are exempt — they go stale, they do not disappear.
    feed_ids = [r.id for r in retailers if r.feed.type != "seed_csv"]
    if feed_ids:
        cutoff = (run_date - timedelta(days=INACTIVE_AFTER_DAYS)).isoformat()
        marks = ",".join("?" * len(feed_ids))
        conn.execute(
            f"UPDATE listings SET in_stock = 0 WHERE last_seen < ? AND retailer_id IN ({marks})",
            (cutoff, *feed_ids),
        )
    conn.commit()
    return counts
