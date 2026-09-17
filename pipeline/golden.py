"""The golden label set (brief §15, Appendix B). Test inputs, never site data.

Three modes, all judged against the same `expect` block:
- calc-only: each label's hand-written reference `extraction` -> rules -> calculator.
- live: the real LLM reads the label; results are saved to tests/golden/cache/.
- replay: those saved LLM results, so CI can check them without calling the API.
"""

import json
from pathlib import Path

import yaml

from pipeline.compounds import Registry
from pipeline.normalise.rules import NormalisedProduct, ResolvedActive, apply_rules
from pipeline.normalise.schema import Extraction
from pipeline.price import calc

GOLDEN_PATH = Path("tests/golden/labels.yml")
CACHE_DIR = Path("tests/golden/cache")
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


def _check(label: dict, extraction: Extraction, registry: Registry) -> list[str]:
    product = apply_rules(extraction, registry, label["title"], label.get("description", ""))
    return check_label(label, product)


def run_calc_only(registry: Registry, labels: list[dict] | None = None) -> dict[str, list[str]]:
    """label id -> problems, using each label's hand-written reference extraction.
    Tests the rules and the calculator only."""
    labels = load_golden_labels() if labels is None else labels
    return {
        label["id"]: _check(label, Extraction.model_validate(label["extraction"]), registry)
        for label in labels
    }


def run_live(registry: Registry, labels: list[dict], extractor, cache_dir: Path = CACHE_DIR):
    """Real LLM extraction for every label; each result is saved for replay (§15)."""
    results = {}
    cache_dir.mkdir(parents=True, exist_ok=True)
    for label in labels:
        result = extractor.extract(label["title"], label.get("description", ""))
        record = {
            "prompt_version": extractor.config.prompt_version,
            "model_id": result.model_id,
            "escalated": result.escalated,
            "extraction": result.extraction.model_dump(),
        }
        path = cache_dir / f"{label['id']}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        results[label["id"]] = _check(label, result.extraction, registry)
    return results


def run_replay(
    registry: Registry, labels: list[dict], prompt_version: str, cache_dir: Path = CACHE_DIR
) -> dict[str, list[str]]:
    """Saved LLM extractions for the current prompt version. Labels with no saved
    extraction are left out — run `make golden-live` to create them."""
    results = {}
    for label in labels:
        path = cache_dir / f"{label['id']}.json"
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["prompt_version"] == prompt_version:
            extraction = Extraction.model_validate(record["extraction"])
            results[label["id"]] = _check(label, extraction, registry)
    return results


def coverage_gaps(registry: Registry, labels: list[dict]) -> dict[str, int]:
    """Compounds with fewer than the required golden labels (brief §15 'rule for growth')."""
    counts = {c.id: 0 for c in registry.compounds}
    for label in labels:
        for compound_id in label.get("compounds", []):
            if compound_id in counts:
                counts[compound_id] += 1
    return {cid: n for cid, n in counts.items() if n < MIN_LABELS_PER_COMPOUND}
