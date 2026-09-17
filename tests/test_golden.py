"""Phase 0: the golden set loads and is well-formed. The real runner arrives in Phase 1-2."""

from pipeline.golden import load_golden_labels


def test_golden_set_loads():
    labels = load_golden_labels()
    assert isinstance(labels, list)


def test_golden_ids_unique():
    ids = [label["id"] for label in load_golden_labels()]
    assert len(ids) == len(set(ids))
