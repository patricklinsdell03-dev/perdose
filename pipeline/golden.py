"""Loads the golden label set (brief §15, Appendix B). Test inputs, never site data."""

from pathlib import Path

import yaml

GOLDEN_PATH = Path("tests/golden/labels.yml")


def load_golden_labels(path: Path = GOLDEN_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels = data.get("labels") or []
    if not isinstance(labels, list):
        raise ValueError(f"{path}: 'labels' must be a list")
    return labels
