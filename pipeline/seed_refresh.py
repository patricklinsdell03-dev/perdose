"""`make seed-refresh` / `make seed-refresh-apply`: keep hand-collected seed prices honest
until live feeds replace them.

seed-refresh        -> data/review/seed_refresh_<date>.csv: one row per seed listing, oldest
                       first, with blank `new_price_gbp` / `new_in_stock` columns. Open each
                       url, type what the page shows today.
seed-refresh-apply  -> writes those values back into data/seed/<retailer>.csv and stamps the
                       row with the checklist's date. Rows left blank are untouched.

Only price, stock and the capture date ever change here. Label text is never edited, so a
refresh costs no AI calls.
"""

import csv
import io
import re
from datetime import date
from pathlib import Path

SEED_DIR = Path("data/seed")
REVIEW_DIR = Path("data/review")
PREFIX = "seed_refresh_"
STALE_AFTER_DAYS = 14
# A refreshed price this far from the old one is more likely a typo than a sale.
MAX_PRICE_RATIO = 3.0

COLUMNS = [
    "retailer_id",
    "merchant_pid",
    "title",
    "url",
    "captured_on",
    "price_gbp",
    "new_price_gbp",
    "new_in_stock",
]
IN_STOCK = {"1": "1", "yes": "1", "y": "1", "0": "0", "no": "0", "n": "0"}


class SeedRefreshError(ValueError):
    pass


def read_rows(text: str) -> tuple[list[str], list[dict]]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), list(reader)


def write_rows(fieldnames: list[str], rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def checklist(seeds: dict[str, str]) -> str:
    """`seeds` is retailer id -> seed CSV text. Oldest captures first."""
    rows = []
    for retailer_id, text in seeds.items():
        for row in read_rows(text)[1]:
            rows.append(
                {
                    **{key: row.get(key, "") for key in COLUMNS},
                    "retailer_id": retailer_id,
                    "new_price_gbp": "",
                    "new_in_stock": "",
                }
            )
    rows.sort(key=lambda r: (r["captured_on"], r["retailer_id"], r["title"]))
    return write_rows(COLUMNS, rows)


def stale_counts(seeds: dict[str, str], today: date) -> dict[str, int]:
    """Retailer id -> how many seed rows were captured more than STALE_AFTER_DAYS ago."""
    counts = {}
    for retailer_id, text in seeds.items():
        ages = [(today - date.fromisoformat(r["captured_on"])).days for r in read_rows(text)[1]]
        counts[retailer_id] = sum(1 for age in ages if age > STALE_AFTER_DAYS)
    return counts


def _new_price(raw: str, old: str, where: str) -> str:
    cleaned = raw.strip().removeprefix("£")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        raise SeedRefreshError(f"{where}: {raw!r} is not a price like 12.99")
    new, previous = float(cleaned), float(old)
    if new <= 0:
        raise SeedRefreshError(f"{where}: price must be above zero")
    if previous > 0 and not (previous / MAX_PRICE_RATIO <= new <= previous * MAX_PRICE_RATIO):
        raise SeedRefreshError(
            f"{where}: {new:.2f} is more than {MAX_PRICE_RATIO:g}x away from the old price "
            f"{previous:.2f} - check for a typo (edit the seed CSV by hand if it is real)"
        )
    return f"{new:.2f}"


def apply(checklist_text: str, seeds: dict[str, str], checked_on: date) -> tuple[dict, dict]:
    """Returns (updated seed texts for the retailers that changed, counts). Nothing is
    written unless every filled-in row is valid."""
    updates = {}
    counts = {"updated": 0, "blank": 0}
    for row in read_rows(checklist_text)[1]:
        price = (row.get("new_price_gbp") or "").strip()
        stock = (row.get("new_in_stock") or "").strip().lower()
        if not price and not stock:
            counts["blank"] += 1
            continue
        key = (row["retailer_id"], row["merchant_pid"])
        where = f"{key[0]}:{key[1]}"
        if stock and stock not in IN_STOCK:
            raise SeedRefreshError(f"{where}: new_in_stock must be 1 or 0, not {stock!r}")
        if key in updates:
            raise SeedRefreshError(f"{where}: listed twice in the checklist")
        updates[key] = (price, stock, row["price_gbp"], where)

    changed = {}
    for retailer_id in {key[0] for key in updates}:
        if retailer_id not in seeds:
            raise SeedRefreshError(f"no seed file for retailer {retailer_id!r}")
        fieldnames, rows = read_rows(seeds[retailer_id])
        found = set()
        for seed_row in rows:
            key = (retailer_id, seed_row["merchant_pid"])
            if key not in updates:
                continue
            price, stock, _, where = updates[key]
            if price:
                seed_row["price_gbp"] = _new_price(price, seed_row["price_gbp"], where)
            if stock:
                seed_row["in_stock"] = IN_STOCK[stock]
            seed_row["captured_on"] = checked_on.isoformat()
            found.add(key)
        missing = [k for k in updates if k[0] == retailer_id and k not in found]
        if missing:
            raise SeedRefreshError(f"{missing[0][0]}:{missing[0][1]} is not in the seed file")
        changed[retailer_id] = write_rows(fieldnames, rows)
    counts["updated"] = len(updates)
    return changed, counts


def load_seeds(seed_dir: Path = SEED_DIR) -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(seed_dir.glob("*.csv"))}


def latest_checklist(review_dir: Path = REVIEW_DIR) -> Path | None:
    files = sorted(review_dir.glob(f"{PREFIX}*.csv")) if review_dir.exists() else []
    return files[-1] if files else None
