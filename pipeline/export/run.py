"""`export` (brief §5.3): SQLite -> data/export/*.json, the only thing the site reads.

Files: compounds.json (rules for explainers/methodology), compounds/<id>.json (one per
compound), index.json (home-page cards), meta.json (counts for the CI regression guard).
Every number here was computed in Python upstream; this module only arranges it.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.compounds import Compound, Registry
from pipeline.ingest.run import Retailer
from pipeline.normalise.rules import find_term

EXPORT_DIR = Path("data/export")
MAX_COMPOUND_FILE_BYTES = 2_000_000  # §5.3
MAX_TOTAL_BYTES = 5_000_000  # §15

REVIEW_REASON_TEXT = {
    "ambiguous_basis": "The label does not say whether the amount is the mineral itself or "
    "the whole compound.",
    "no_elemental_factor": "Only the compound's weight is given, and we have no reliable "
    "conversion for this form.",
    "amount_missing": "We could not find the amount per serving in the listing.",
    "servings_unknown": "We could not work out how many servings are in the pack.",
    "servings_conflict": "The stated number of servings does not match the pack size.",
    "form_unknown": "The listing does not make clear which form this is.",
    "unit_not_convertible": "The amount is in a unit we cannot convert for this ingredient.",
    "extract_basis_unclear": "It is not clear whether the amount is extract or whole herb.",
    "low_confidence": "The listing was hard to read reliably.",
    "no_epa_dha": "Only the oil weight is given, not the EPA and DHA content.",
}


CLAIM_PATTERNS = {
    # "claimed" chips (§12.2): only what the listing itself says, never inferred.
    "vegan": r"(?<!non-)(?<!non )\bvegans?\b",
    "vegetarian": r"\bvegetarians?\b",
    "gluten-free": r"\bgluten[- ]free\b",
    "sugar-free": r"\bsugar[- ]free\b",
}
# "Not suitable for vegetarians", "not suitable for vegetarians or vegans"
NEGATED = r"\b(not|unsuitable)\s+(\w+\s+){0,4}$"


def claimed_flags(text: str) -> list[str]:
    """Dietary claims made in the listing. "Not suitable for vegetarians" is not a claim."""
    lowered = text.lower()
    flags = []
    for flag, pattern in CLAIM_PATTERNS.items():
        for match in re.finditer(pattern, lowered):
            if not re.search(NEGATED, lowered[: match.start()][-40:]):
                flags.append(flag)
                break
    return flags


class ExportTooLarge(Exception):
    pass


def _rules_view(compound: Compound) -> dict:
    """The rules table minus internal notes (§5.3)."""
    classes: dict[str, dict] = {}
    for form in compound.forms:
        entry = classes.setdefault(
            form.form_class,
            {
                "id": form.form_class,
                "label": compound.classes[form.form_class].label,
                "slug": compound.classes[form.form_class].slug,
                "standard_dose": compound.standard_dose_for(form),
                "forms": [],
            },
        )
        entry["forms"].append(
            {"id": form.id, "names": form.names, "elemental_factor": form.elemental_factor}
        )
    return {
        "id": compound.id,
        "name": compound.name,
        "category": compound.category,
        "tier": compound.tier,
        "comparison_quantity": compound.comparison_quantity,
        "unit": compound.unit,
        "standard_dose": compound.standard_dose,
        "label_convention": compound.label_convention,
        "normalisation_type": compound.normalisation_type,
        "aliases": compound.aliases,
        "classes": list(classes.values()),
    }


def _rows_for(conn: sqlite3.Connection, compound_id: str, prompt_version: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT o.listing_id, o.product_id, o.price_list_gbp, o.match_method,
               l.retailer_id, l.url, l.image_url, l.in_stock, l.last_seen, l.title, l.description,
               p.brand, p.name, p.pack_units, p.pack_unit_type, p.units_per_serving,
               p.multipack_count, p.servings, p.tested_flag, p.multi_ingredient,
               p.needs_review, p.review_reason,
               a.form_id, a.form_class, a.amount_per_serving, a.amount_unit, a.amount_basis,
               a.is_primary, a.rank_eligible,
               op.price_per_unit, op.price_per_std_dose, op.cost_per_month, op.days_supply,
               e.extracted_json
        FROM offers o
        JOIN listings l ON l.listing_id = o.listing_id
        JOIN products p ON p.product_id = o.product_id
        JOIN product_actives a ON a.product_id = o.product_id AND a.compound_id = ?
        LEFT JOIN offer_prices op ON op.listing_id = o.listing_id
             AND op.compound_id = a.compound_id AND op.price_basis = 'list'
        LEFT JOIN extractions e ON e.content_hash = l.content_hash AND e.prompt_version = ?
        """,
        (compound_id, prompt_version),
    ).fetchall()
    conn.row_factory = None
    return [dict(row) for row in rows]


def _offer(row: dict, compound_id: str) -> dict:
    extraction = json.loads(row["extracted_json"]) if row["extracted_json"] else {}
    active = next((a for a in extraction.get("actives", []) if a["compound_id"] == compound_id), {})
    other_actives = [
        a["compound_id"] for a in extraction.get("actives", []) if a["compound_id"] != compound_id
    ] + extraction.get("other_actives", [])
    reasons = [r for r in (row["review_reason"] or "").split(", ") if r]
    if not reasons and not row["rank_eligible"]:  # a secondary active with its own problem
        if row["form_class"] == "unknown":
            reasons.append("form_unknown")
        elif row["amount_per_serving"] is None:
            reasons.append("amount_missing")
    return {
        "listing_id": row["listing_id"],
        "product_id": row["product_id"],
        "brand": row["brand"],
        "name": row["name"],
        "retailer_id": row["retailer_id"],
        "url": row["url"],
        "image_url": row["image_url"],
        "price_gbp": row["price_list_gbp"],
        "in_stock": bool(row["in_stock"]),
        "price_date": row["last_seen"],
        "pack": {
            "units": row["pack_units"],
            "unit_type": row["pack_unit_type"],
            "units_per_serving": row["units_per_serving"],
            "multipack_count": row["multipack_count"],
            "servings": row["servings"],
        },
        "form_id": row["form_id"],
        "amount_per_serving": row["amount_per_serving"],
        "amount_unit": row["amount_unit"],
        "amount_basis": row["amount_basis"],
        "is_primary": bool(row["is_primary"]),
        "price_per_unit": row["price_per_unit"],
        "price_per_std_dose": row["price_per_std_dose"],
        "cost_per_month": row["cost_per_month"],
        "days_supply": row["days_supply"],
        "tested_flag": row["tested_flag"],
        "claimed": claimed_flags(f"{row['title']} {row['description'] or ''}"),
        "other_actives": other_actives,
        "review_reasons": [
            {"code": code, "text": REVIEW_REASON_TEXT.get(code, code)} for code in reasons
        ],
        # For the "show the working" panel: the label quotes each number came from.
        "evidence": {**extraction.get("evidence", {}), **active.get("evidence", {})},
        "components": active.get("components", []),
        "branded_extract": active.get("branded_extract"),
    }


def _named_in_title(compound: Compound, row: dict) -> bool:
    terms = [compound.name, *compound.aliases]
    return any(find_term(term, row["name"]) is not None for term in terms)


def _compound_file(compound: Compound, rows: list[dict], generated_at: str) -> dict:
    view = _rules_view(compound)
    classes = []
    for cls in [*view["classes"], {"id": "unknown", "standard_dose": compound.standard_dose}]:
        in_class = [row for row in rows if row["form_class"] == cls["id"]]
        if not in_class:
            continue
        ranked, combinations, unverified = [], [], []
        for row in in_class:
            offer = _offer(row, compound.id)
            if (
                row["needs_review"]
                or not row["rank_eligible"]
                or offer["price_per_std_dose"] is None
            ):
                unverified.append(offer)
            elif row["multi_ingredient"] or not (
                row["is_primary"] or _named_in_title(compound, row)
            ):
                # Combination products, and products where this compound is only a minor
                # extra (60 mg vitamin C inside a zinc tablet). Hidden until the Phase 8 toggle.
                combinations.append(offer)
            else:
                ranked.append(offer)

        def by_price(o):
            return (o["price_per_std_dose"], o["cost_per_month"])

        ranked.sort(key=by_price)
        combinations.sort(key=by_price)
        unverified.sort(key=lambda o: (o["brand"] or "", o["name"]))
        classes.append(
            {
                "id": cls["id"],
                "label": cls.get("label", "Form not stated"),
                "slug": cls.get("slug", "form-not-stated"),
                "standard_dose": cls["standard_dose"],
                "ranked": ranked,
                "combinations": combinations,
                "unverified": unverified,
            }
        )
    return {"generated_at": generated_at, "compound": view, "classes": classes}


def _clear_compound_files(out_dir: Path) -> None:
    """A compound that lost all its products must not keep an old file."""
    for stale in (out_dir / "compounds").glob("*.json"):
        stale.unlink()


def _write(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def export(
    conn: sqlite3.Connection,
    registry: Registry,
    retailers: list[Retailer],
    prompt_version: str,
    out_dir: Path = EXPORT_DIR,
) -> dict:
    generated_at = datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="seconds")
    total = _write(out_dir / "compounds.json", [_rules_view(c) for c in registry.compounds])

    _clear_compound_files(out_dir)

    index, counts = [], {"compounds": {}, "classes": {}}
    seen_products, seen_retailers = set(), set()
    for compound in registry.compounds:
        rows = _rows_for(conn, compound.id, prompt_version)
        if not rows:
            continue
        data = _compound_file(compound, rows, generated_at)
        size = _write(out_dir / "compounds" / f"{compound.id}.json", data)
        if size > MAX_COMPOUND_FILE_BYTES:
            raise ExportTooLarge(f"{compound.id}.json is {size:,} bytes (limit 2 MB)")
        total += size

        class_cards = []
        for cls in data["classes"]:
            ranked = cls["ranked"]
            counts["classes"][cls["id"]] = len(ranked)
            class_cards.append(
                {
                    "id": cls["id"],
                    "label": cls["label"],
                    "slug": cls["slug"],
                    "standard_dose": cls["standard_dose"],
                    "ranked_count": len(ranked),
                    "unverified_count": len(cls["unverified"]),
                    "retailer_count": len({o["retailer_id"] for o in ranked}),
                    "from_price_per_std_dose": ranked[0]["price_per_std_dose"] if ranked else None,
                }
            )
        product_ids = {row["product_id"] for row in rows}
        retailer_ids = {row["retailer_id"] for row in rows}
        seen_products |= product_ids
        seen_retailers |= retailer_ids
        counts["compounds"][compound.id] = len(product_ids)
        index.append(
            {
                "id": compound.id,
                "name": compound.name,
                "category": compound.category,
                "unit": compound.unit,
                "product_count": len(product_ids),
                "retailer_count": len(retailer_ids),
                "classes": class_cards,
            }
        )

    total += _write(out_dir / "index.json", index)
    meta = {
        "generated_at": generated_at,
        "retailers": [
            {"id": r.id, "name": r.name, "shipping": r.shipping.model_dump(exclude_none=True)}
            for r in retailers
            if r.id in seen_retailers
        ],
        "counts": {"products": len(seen_products), **counts},
    }
    total += _write(out_dir / "meta.json", meta)
    if total > MAX_TOTAL_BYTES:
        raise ExportTooLarge(f"export is {total:,} bytes in total (limit 5 MB)")
    return {"files": 3 + len(index), "bytes": total, "products": len(seen_products)}
