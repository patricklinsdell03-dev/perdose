"""Regression guard (brief §14): a bad data day must not deploy.

Compares the export's counts with the previous run's. Any comparison table that had ranked
products before and has none now fails the run, as does a large overall drop.
"""

import json
from pathlib import Path

MAX_PRODUCT_DROP = 0.5  # losing more than half of all products in a day is never normal


def classes_lost(before: dict, after: dict) -> list[str]:
    old = before.get("counts", {}).get("classes", {})
    new = after.get("counts", {}).get("classes", {})
    return sorted(cls for cls, count in old.items() if count > 0 and new.get(cls, 0) == 0)


def check(before: dict, after: dict) -> list[str]:
    """Reasons to block the deploy. Empty list = safe."""
    problems = [
        f"class {cls} had ranked products before and has none now"
        for cls in classes_lost(before, after)
    ]
    old_total = before.get("counts", {}).get("products", 0)
    new_total = after.get("counts", {}).get("products", 0)
    if old_total and new_total < old_total * (1 - MAX_PRODUCT_DROP):
        problems.append(f"products fell from {old_total} to {new_total}")
    return problems


def check_files(before_path: Path, after_path: Path) -> list[str]:
    if not before_path.exists() or not before_path.read_text(encoding="utf-8").strip():
        return []  # first run: nothing to compare with
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))
    return check(before, after)
