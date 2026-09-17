"""`make review` / `make review-apply` (brief §12.3): work down the unverified queue without
touching code.

review        -> data/review/<date>.csv, one row per unverified listing, with what the AI read
                 and blank `decision` / `values` columns for Patrick.
review-apply  -> folds the filled-in decisions into config/product_overrides.yml, which
                 `make price` applies on the next run.

Decisions:  approve-with-values | reject | merge-into:<product_id>
Values:     key=value pairs separated by ';' — only the keys in VALUE_KEYS.
"""

import csv
import json
import sqlite3
from datetime import date
from pathlib import Path

import yaml

REVIEW_DIR = Path("data/review")
OVERRIDES_PATH = Path("config/product_overrides.yml")

COLUMNS = [
    "listing_id",
    "product_id",
    "retailer_id",
    "title",
    "url",
    "price_gbp",
    "reasons",
    "form_id",
    "amount_per_serving",
    "amount_unit",
    "amount_refers_to",
    "pack_units",
    "pack_unit_type",
    "units_per_serving",
    "evidence",
    "decision",
    "values",
]
VALUE_KEYS = {
    "form_id": str,
    "amount_per_serving": float,
    "amount_unit": str,
    "amount_refers_to": str,
    "pack_units": int,
    "pack_unit_type": str,
    "units_per_serving": float,
    "multipack_count": int,
}
HEADER = """\
# Manual corrections, applied last by `make price` (brief §11 step 5, §12.3).
# Written by `make review-apply`; safe to edit by hand.
#   merge:   fold one product into another      - { product: <id>, into: <id> }
#   split:   listing ids that must be their own product
#   exclude: listing ids never to show
#   values:  facts a person confirmed from the label, per listing id
"""


class ReviewError(ValueError):
    pass


def export_review(
    conn: sqlite3.Connection, prompt_version: str, today: date, out_dir: Path = REVIEW_DIR
) -> tuple[Path | None, int]:
    rows = conn.execute(
        """
        SELECT l.listing_id, o.product_id, l.retailer_id, l.title, l.url, l.price_gbp,
               p.review_reason, e.extracted_json
        FROM products p
        JOIN offers o ON o.product_id = p.product_id
        JOIN listings l ON l.listing_id = o.listing_id
        LEFT JOIN extractions e ON e.content_hash = l.content_hash AND e.prompt_version = ?
        WHERE p.needs_review = 1
        ORDER BY p.review_reason, l.retailer_id, l.title
        """,
        (prompt_version,),
    ).fetchall()
    if not rows:
        return None, 0

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{today.isoformat()}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for listing_id, product_id, retailer_id, title, url, price, reasons, extracted in rows:
            extraction = json.loads(extracted) if extracted else {}
            active = (extraction.get("actives") or [{}])[0]
            evidence = {**extraction.get("evidence", {}), **active.get("evidence", {})}
            writer.writerow(
                {
                    "listing_id": listing_id,
                    "product_id": product_id,
                    "retailer_id": retailer_id,
                    "title": title,
                    "url": url,
                    "price_gbp": price,
                    "reasons": reasons,
                    "form_id": active.get("form_id"),
                    "amount_per_serving": active.get("amount_per_serving"),
                    "amount_unit": active.get("amount_unit"),
                    "amount_refers_to": active.get("amount_refers_to"),
                    "pack_units": extraction.get("pack_units"),
                    "pack_unit_type": extraction.get("pack_unit_type"),
                    "units_per_serving": extraction.get("units_per_serving"),
                    "evidence": json.dumps(evidence, ensure_ascii=False),
                    "decision": "",
                    "values": "",
                }
            )
    return path, len(rows)


def parse_values(text: str) -> dict:
    values = {}
    for pair in filter(None, (part.strip() for part in text.split(";"))):
        key, sep, raw = pair.partition("=")
        key, raw = key.strip(), raw.strip()
        if not sep or key not in VALUE_KEYS or not raw:
            raise ReviewError(f"cannot read value {pair!r}; allowed keys: {sorted(VALUE_KEYS)}")
        try:
            values[key] = VALUE_KEYS[key](raw)
        except ValueError as error:
            raise ReviewError(f"{key}={raw!r} is not a valid {VALUE_KEYS[key].__name__}") from error
    return values


def latest_review_file(review_dir: Path = REVIEW_DIR) -> Path | None:
    files = sorted(review_dir.glob("*.csv")) if review_dir.exists() else []
    return files[-1] if files else None


def apply_review(csv_path: Path, overrides_path: Path = OVERRIDES_PATH) -> dict[str, int]:
    """Merge the CSV's decisions into the overrides file. Rows with no decision are skipped."""
    existing = {}
    if overrides_path.exists():
        existing = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or {}
    merge = {item["product"]: item["into"] for item in existing.get("merge") or []}
    split = list(existing.get("split") or [])
    exclude = set(existing.get("exclude") or [])
    values = dict(existing.get("values") or {})

    counts = {"approved": 0, "rejected": 0, "merged": 0, "skipped": 0}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            decision = (row.get("decision") or "").strip()
            listing_id = row["listing_id"]
            if not decision:
                counts["skipped"] += 1
            elif decision == "reject":
                exclude.add(listing_id)
                counts["rejected"] += 1
            elif decision.startswith("merge-into:"):
                merge[row["product_id"]] = decision.removeprefix("merge-into:").strip()
                counts["merged"] += 1
            elif decision == "approve-with-values":
                parsed = parse_values(row.get("values") or "")
                if not parsed:
                    raise ReviewError(f"{listing_id}: approve-with-values needs a `values` entry")
                values[listing_id] = parsed
                counts["approved"] += 1
            else:
                raise ReviewError(f"{listing_id}: unknown decision {decision!r}")

    data = {
        "merge": [{"product": product, "into": into} for product, into in sorted(merge.items())],
        "split": split,
        "exclude": sorted(exclude),
        "values": dict(sorted(values.items())),
    }
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    overrides_path.write_text(HEADER + body, encoding="utf-8", newline="\n")
    return counts
