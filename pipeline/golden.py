"""The golden label set (brief §15, Appendix B). Test inputs, never site data.

Calc-only mode (Phase 1): each label's reference `extraction` goes through the real rules
and calculator and the result is compared with `expect`. From Phase 2 the live LLM
extraction takes the reference's place; the comparison stays the same.
"""

from pathlib import Path

import yaml

from pipeline.compounds import Registry
from pipeline.normalise.rules import NormalisedProduct, ResolvedActive, apply_rules
from pipeline.normalise.schema import Extraction
from pipeline.price import calc

GOLDEN_PATH = Path("tests/golden/labels.yml")
PASS_THRESHOLD = 0.9
MIN_LABELS_PER_COMPOUND = 3
TOLERANCE = 0.01

# expect key -> where to read it on the primary active / the product
ACTIVE_FIELDS = {
    "compound": "compound_id",
    "form": "form_id",
    "form_class": "form_class",
    "amount": "amount_per_serving",
    "amount_unit": "amount_unit",
    "basis": "amount_basis",
    "standard_dose": "standard_dose",
    "is_primary": "is_primary",
    "rank_eligible": "rank_eligible",
}
PRODUCT_FIELDS = {
    "servings": "servings",
    "pack_units": "pack_units",
    "pack_unit_type": "pack_unit_type",
    "units_per_serving": "units_per_serving",
    "multipack": "multipack_count",
    "multi_ingredient": "multi_ingredient",
    "needs_review": "needs_review",
}
PRICE_FIELDS = ("price_per_std_dose", "cost_per_month")


def load_golden_labels(path: Path = GOLDEN_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels = data.get("labels") or []
    if not isinstance(labels, list):
        raise ValueError(f"{path}: 'labels' must be a list")
    return labels


def _same(actual, expected) -> bool:
    if isinstance(expected, bool) or not isinstance(expected, int | float):
        return actual == expected
    if actual is None:
        return False
    return abs(actual - expected) <= TOLERANCE * abs(expected)


def _check_active(active: ResolvedActive | None, expect: dict, where: str) -> list[str]:
    if active is None:
        return [f"{where}: no such active"]
    return [
        f"{where}.{key}: expected {expect[key]!r}, got {getattr(active, attr)!r}"
        for key, attr in ACTIVE_FIELDS.items()
        if key in expect and not _same(getattr(active, attr), expect[key])
    ]


def check_label(label: dict, product: NormalisedProduct) -> list[str]:
    """Every way `product` differs from the label's `expect`. Empty list = pass."""
    expect = label["expect"]
    known = {*ACTIVE_FIELDS, *PRODUCT_FIELDS, *PRICE_FIELDS}
    known |= {"review_reason", "max_confidence", "actives"}
    problems = [f"unknown expect key {key!r}" for key in expect if key not in known]

    problems += _check_active(product.primary, expect, "primary")
    for key, attr in PRODUCT_FIELDS.items():
        if key in expect and not _same(getattr(product, attr), expect[key]):
            problems.append(f"{key}: expected {expect[key]!r}, got {getattr(product, attr)!r}")
    if "review_reason" in expect and expect["review_reason"] not in product.review_reasons:
        problems.append(
            f"review_reason: {expect['review_reason']!r} not in {product.review_reasons}"
        )
    if "max_confidence" in expect and product.confidence > expect["max_confidence"]:
        problems.append(f"confidence {product.confidence} above {expect['max_confidence']}")
    for wanted in expect.get("actives", []):
        found = next((a for a in product.actives if a.compound_id == wanted["compound"]), None)
        problems += _check_active(found, wanted, wanted["compound"])

    if any(key in expect for key in PRICE_FIELDS):
        primary = product.primary
        if not (primary and primary.rank_eligible and product.servings):
            problems.append("price expected but the product is not rank-eligible")
        else:
            price = calc.price_offer(
                label["price_gbp"],
                product.servings,
                primary.amount_per_serving,
                primary.standard_dose,
            )
            for key in PRICE_FIELDS:
                if key in expect and not _same(getattr(price, key), expect[key]):
                    problems.append(f"{key}: expected {expect[key]!r}, got {getattr(price, key)!r}")
    return problems


def run_calc_only(registry: Registry, labels: list[dict] | None = None) -> dict[str, list[str]]:
    """label id -> problems, using each label's reference extraction."""
    results = {}
    for label in load_golden_labels() if labels is None else labels:
        extraction = Extraction.model_validate(label["extraction"])
        product = apply_rules(extraction, registry, label["title"], label.get("description", ""))
        results[label["id"]] = check_label(label, product)
    return results


def coverage_gaps(registry: Registry, labels: list[dict]) -> dict[str, int]:
    """Compounds with fewer than the required golden labels (brief §15 'rule for growth')."""
    counts = {c.id: 0 for c in registry.compounds}
    for label in labels:
        for compound_id in label.get("compounds", []):
            if compound_id in counts:
                counts[compound_id] += 1
    return {cid: n for cid, n in counts.items() if n < MIN_LABELS_PER_COMPOUND}
