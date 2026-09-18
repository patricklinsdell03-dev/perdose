"""SQLite storage (brief §5.2). The schema is the brief's, verbatim.

Changing it needs Patrick's OK (CLAUDE.md rule 7). Amounts are stored in each compound's
base unit with the unit alongside — there are no `_mg` columns (rule 10).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/perdose.sqlite")

SCHEMA = """
-- One row per retailer listing as received (a "listing" is retailer-specific).
CREATE TABLE IF NOT EXISTS listings (
  listing_id      TEXT PRIMARY KEY,   -- f"{retailer_id}:{merchant_product_id}"
  retailer_id     TEXT NOT NULL,
  merchant_pid    TEXT NOT NULL,
  ean             TEXT,               -- GTIN/EAN if provided, digits only
  brand           TEXT,
  title           TEXT NOT NULL,
  description     TEXT,
  url             TEXT NOT NULL,      -- affiliate deep link
  image_url       TEXT,
  price_gbp       REAL NOT NULL,
  in_stock        INTEGER NOT NULL,   -- 1/0
  first_seen      TEXT NOT NULL,      -- ISO date
  last_seen       TEXT NOT NULL,
  content_hash    TEXT NOT NULL       -- sha256(title + description) -> drives extraction cache
);

-- One row per (content_hash, prompt_version). The LLM's structured output, verbatim.
CREATE TABLE IF NOT EXISTS extractions (
  content_hash    TEXT NOT NULL,
  prompt_version  TEXT NOT NULL,
  model_id        TEXT NOT NULL,
  extracted_json  TEXT NOT NULL,      -- Extraction schema (§9.3) as JSON
  confidence      REAL NOT NULL,      -- 0..1 from the model
  escalated       INTEGER NOT NULL,   -- 1 if the escalation model was used
  created_at      TEXT NOT NULL,
  PRIMARY KEY (content_hash, prompt_version)
);

-- The canonical product (retailer-independent). Many listings -> one product.
CREATE TABLE IF NOT EXISTS products (
  product_id      TEXT PRIMARY KEY,   -- slug, stable once created
  ean             TEXT,
  brand           TEXT,
  name            TEXT NOT NULL,      -- cleaned display name
  pack_units      INTEGER,            -- capsules/tablets/grams/ml in ONE pack
  pack_unit_type  TEXT,               -- 'capsule'|'tablet'|'softgel'|'gummy'|'gram'|'ml'|'sachet'|'drop'
  units_per_serving REAL,
  multipack_count INTEGER NOT NULL DEFAULT 1,
  servings        REAL,               -- computed: pack_units * multipack_count / units_per_serving
  tested_flag     TEXT,               -- 'informed_sport'|'third_party'|null (label claim only in v1)
  multi_ingredient INTEGER NOT NULL,  -- 1 if any active beyond the primary's accepted cofactors
  needs_review    INTEGER NOT NULL,   -- 1 -> unverified only, never ranked
  review_reason   TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

-- One row per (product, compound). A "D3 + K2" product has two rows.
CREATE TABLE IF NOT EXISTS product_actives (
  product_id      TEXT NOT NULL REFERENCES products(product_id),
  compound_id     TEXT NOT NULL,      -- from compounds.yml
  form_id         TEXT NOT NULL,
  form_class      TEXT NOT NULL,      -- comparability class (§6.3)
  amount_per_serving REAL,            -- in the compound's base unit (mg, mcg or IU)
  amount_unit     TEXT NOT NULL,      -- always equal to the compound's declared unit
  amount_basis    TEXT NOT NULL,      -- 'stated_elemental'|'estimated_from_compound'|'stated_total'|'stated_component_sum'|'stated_extract'|'stated_compound'|'stated_constituent'
  is_primary      INTEGER NOT NULL,   -- 1 for the headline active (title order decides)
  rank_eligible   INTEGER NOT NULL,   -- 0 if needs_review, amount null, or class has no standard dose
  PRIMARY KEY (product_id, compound_id)
);

-- Links listings to products (built by dedupe, §11). Price fields are per pack.
CREATE TABLE IF NOT EXISTS offers (
  listing_id      TEXT PRIMARY KEY REFERENCES listings(listing_id),
  product_id      TEXT NOT NULL REFERENCES products(product_id),
  price_list_gbp  REAL NOT NULL,      -- as in the feed
  price_effective_gbp REAL,           -- after retailer sitewide code; NULL in v1
  promo_id        TEXT,               -- config/promos.yml id; NULL in v1
  match_method    TEXT NOT NULL,      -- 'ean'|'key'|'llm'|'manual'
  match_confidence REAL NOT NULL,
  updated_at      TEXT NOT NULL
);

-- Per (offer, active) derived prices. Ranking reads this table.
CREATE TABLE IF NOT EXISTS offer_prices (
  listing_id      TEXT NOT NULL REFERENCES offers(listing_id),
  compound_id     TEXT NOT NULL,
  price_basis     TEXT NOT NULL,      -- 'list'|'effective'
  price_per_unit  REAL NOT NULL,      -- GBP per 1 unit of the comparison quantity
  price_per_std_dose REAL NOT NULL,
  cost_per_month  REAL NOT NULL,
  days_supply     REAL NOT NULL,
  PRIMARY KEY (listing_id, compound_id, price_basis)
);

CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
CREATE INDEX IF NOT EXISTS idx_actives_compound_class ON product_actives(compound_id, form_class);
CREATE INDEX IF NOT EXISTS idx_offer_prices_compound ON offer_prices(compound_id, price_per_std_dose);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open the database (":memory:" for tests), creating the tables if needed."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
