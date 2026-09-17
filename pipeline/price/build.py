"""`make price` (brief Â§8, Â§10, Â§11): extractions -> products, actives, offers, offer prices.

Products keep their ids between runs; actives, offers and prices are rebuilt from scratch each
time, so a rule change or a new extraction always flows through.
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from pipeline.compounds import Registry
from pipeline.normalise.rules import NormalisedProduct, apply_rules
from pipeline.normalise.schema import Extraction
from pipeline.price import calc

OVERRIDES_PATH = Path("config/product_overrides.yml")
EAN_CONFIDENCE = 1.0
KEY_CONFIDENCE = 0.85
NEW_CONFIDENCE = 1.0  # a product matched only to itself


@dataclass
class Overrides:
    """Manual corrections, applied last (Â§11 step 5)."""

    split: set[str]  # listing ids that must be their own product
    merge: dict[str, str]  # product id -> product id it should be folded into


def load_overrides(path: Path = OVERRIDES_PATH) -> Overrides:
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or {}
    merge = {item["product"]: item["into"] for item in data.get("merge") or []}
    return Overrides(split=set(data.get("split") or []), merge=merge)


def slugify(*parts: str | None) -> str:
    text = " ".join(str(p) for p in parts if p)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "product"


def match_key(brand: str | None, product: NormalisedProduct) -> str | None:
    """Â§11 step 2. None when the product is too incomplete to be matched safely."""
    primary = product.primary
    if not (brand and primary and product.pack_units and primary.amount_per_serving):
        return None
    # Everything else in the product is part of its identity: "Zinc 25mg" and "Zinc 25mg +
    # Copper" share brand, form, pack and amount but are different products.
    others = sorted({a.compound_id for a in product.actives if a is not primary})
    others += sorted({slugify(name) for name in product.other_actives})
    parts = [
        slugify(brand),
        primary.compound_id,
        primary.form_id,
        product.pack_units,
        product.pack_unit_type,
        product.multipack_count,
        round(primary.amount_per_serving),
        "+".join(others),
    ]
    return "|".join(str(part) for part in parts)


def _now() -> str:
    return datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="seconds")


def _unique_id(conn: sqlite3.Connection, base: str) -> str:
    candidate, n = base, 1
    while conn.execute("SELECT 1 FROM products WHERE product_id = ?", (candidate,)).fetchone():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def build(conn: sqlite3.Connection, registry: Registry, prompt_version: str, overrides: Overrides):
    """Returns counts for the log."""
    rows = conn.execute(
        """
        SELECT l.listing_id, l.ean, l.brand, l.title, l.description, l.price_gbp,
               e.extracted_json
        FROM listings l
        JOIN extractions e ON e.content_hash = l.content_hash AND e.prompt_version = ?
        ORDER BY l.listing_id
        """,
        (prompt_version,),
    ).fetchall()

    # Matching happens within the run, where each listing's full reading is available. The
    # previous run's listing -> product links are only used to keep ids stable (Â§11 step 4).
    known_listing = dict(conn.execute("SELECT listing_id, product_id FROM offers"))
    by_ean: dict[str, str] = {}
    by_key: dict[str, str] = {}

    conn.execute("DELETE FROM offer_prices")
    conn.execute("DELETE FROM offers")
    conn.execute("DELETE FROM product_actives")

    stats = {"listings": 0, "products": 0, "ranked_offers": 0, "needs_review": 0, "no_active": 0}
    touched: set[str] = set()
    now = _now()

    for listing_id, ean, brand, title, description, price_gbp, extracted_json in rows:
        extraction = Extraction.model_validate_json(extracted_json)
        product = apply_rules(extraction, registry, title, description or "")
        if not product.actives:
            stats["no_active"] += 1
            continue
        stats["listings"] += 1
        key = match_key(brand, product)

        # Â§11: EAN, then key, then a new product. A false merge is a wrong price, so when in
        # doubt a listing stays separate (a duplicate row is only cosmetic).
        split = listing_id in overrides.split
        previous = known_listing.get(listing_id)
        if not split and ean and ean in by_ean:
            product_id, method, confidence = by_ean[ean], "ean", EAN_CONFIDENCE
        elif not split and key and key in by_key:
            product_id, method, confidence = by_key[key], "key", KEY_CONFIDENCE
        else:
            if previous and previous not in touched:
                product_id = previous  # same product as last run: keep its id
            else:
                product_id = _unique_id(conn, slugify(brand, title))
            method, confidence = "key", NEW_CONFIDENCE
        if product_id in overrides.merge:
            product_id, method, confidence = overrides.merge[product_id], "manual", 1.0
        if not split:
            if ean:
                by_ean.setdefault(ean, product_id)
            if key:
                by_key.setdefault(key, product_id)

        if product_id not in touched:  # first listing of a product describes it
            touched.add(product_id)
            conn.execute(
                """
                INSERT INTO products (product_id, ean, brand, name, pack_units, pack_unit_type,
                    units_per_serving, multipack_count, servings, tested_flag, multi_ingredient,
                    needs_review, review_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    ean = excluded.ean, brand = excluded.brand, name = excluded.name,
                    pack_units = excluded.pack_units, pack_unit_type = excluded.pack_unit_type,
                    units_per_serving = excluded.units_per_serving,
                    multipack_count = excluded.multipack_count, servings = excluded.servings,
                    tested_flag = excluded.tested_flag,
                    multi_ingredient = excluded.multi_ingredient,
                    needs_review = excluded.needs_review, review_reason = excluded.review_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    product_id,
                    ean,
                    brand,
                    title,
                    product.pack_units,
                    product.pack_unit_type,
                    product.units_per_serving,
                    product.multipack_count,
                    product.servings,
                    product.tested_flag,
                    int(product.multi_ingredient),
                    int(product.needs_review),
                    ", ".join(product.review_reasons) or None,
                    now,
                    now,
                ),
            )
            for active in product.actives:
                conn.execute(
                    "INSERT OR REPLACE INTO product_actives VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        product_id,
                        active.compound_id,
                        active.form_id,
                        active.form_class,
                        active.amount_per_serving,
                        active.amount_unit,
                        active.amount_basis,
                        int(active.is_primary),
                        int(active.rank_eligible),
                    ),
                )
            stats["products"] += 1
            stats["needs_review"] += int(product.needs_review)

        conn.execute(
            "INSERT INTO offers VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)",
            (listing_id, product_id, price_gbp, method, confidence, now),
        )
        for active in product.actives:
            if active.rank_eligible and product.servings:
                price = calc.price_offer(
                    price_gbp, product.servings, active.amount_per_serving, active.standard_dose
                )
                conn.execute(
                    "INSERT INTO offer_prices VALUES (?, ?, 'list', ?, ?, ?, ?)",
                    (
                        listing_id,
                        active.compound_id,
                        price.price_per_unit,
                        price.price_per_std_dose,
                        price.cost_per_month,
                        price.days_supply,
                    ),
                )
                stats["ranked_offers"] += int(active.is_primary)

    # Products no listing points at any more (e.g. a corrected merge) are dropped.
    conn.execute("DELETE FROM products WHERE product_id NOT IN (SELECT product_id FROM offers)")
    conn.commit()
    return stats
