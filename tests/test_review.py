"""Brief §12.3: the review round trip — unverified listing -> CSV -> decision -> ranked."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from pipeline import review
from pipeline.compounds import load_registry
from pipeline.db import connect
from pipeline.guard import check
from pipeline.price.build import Overrides, build, load_overrides
from tests.test_dedupe import PROMPT, add_listing, fixture_extraction

REGISTRY = load_registry()


class MemoryFile:
    """Stands in for a Path so the round trip needs no disk (temp dirs are locked down here)."""

    def __init__(self, text=""):
        self.text = text

    def exists(self):
        return bool(self.text)

    def read_text(self, encoding="utf-8"):
        return self.text

    def write_text(self, text, encoding="utf-8", newline=None):
        self.text = text

    def open(self, mode="r", newline="", encoding="utf-8"):
        if "w" not in mode:
            return io.StringIO(self.text)
        owner = self

        class Writer(io.StringIO):
            def close(self):
                owner.text = self.getvalue()
                super().close()

        return Writer()

    def as_posix(self):
        return "memory.csv"


class MemoryDir:
    def __init__(self):
        self.file = MemoryFile()

    def mkdir(self, parents=False, exist_ok=False):
        pass

    def __truediv__(self, name):
        return self.file


def fixture_ambiguous_db():
    """One clean listing and one whose amount is ambiguous (unverified)."""
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    add_listing(conn, "fixture_b", "2", 9.00, brand="Fixture Other", amount=250)
    ambiguous = fixture_extraction(250)
    ambiguous["actives"][0]["amount_refers_to"] = "unclear"
    conn.execute(
        "UPDATE extractions SET extracted_json = ? WHERE content_hash ="
        " (SELECT content_hash FROM listings WHERE listing_id = 'fixture_b:2')",
        (json.dumps(ambiguous),),
    )
    return conn


def fill_in(csv_text, decision, values=""):
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    for row in rows:
        row["decision"], row["values"] = decision, values
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=review.COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def ranked(conn):
    return {row[0] for row in conn.execute("SELECT listing_id FROM offer_prices")}


def test_round_trip_approve_with_values_makes_the_listing_ranked():
    conn = fixture_ambiguous_db()
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))
    assert ranked(conn) == {"fixture_a:1"}

    out = MemoryDir()
    path, count = review.export_review(conn, PROMPT, date(2026, 9, 17), out_dir=out)
    assert count == 1
    exported = list(csv.DictReader(io.StringIO(out.file.text)))
    assert exported[0]["listing_id"] == "fixture_b:2"
    assert exported[0]["reasons"] == "ambiguous_basis"
    assert "250mg magnesium" in exported[0]["evidence"]

    filled = MemoryFile(fill_in(out.file.text, "approve-with-values", "amount_refers_to=elemental"))
    overrides_file = MemoryFile()
    counts = review.apply_review(filled, overrides_file)
    assert counts["approved"] == 1

    overrides = yaml.safe_load(overrides_file.text)
    assert overrides["values"] == {"fixture_b:2": {"amount_refers_to": "elemental"}}
    build(conn, REGISTRY, PROMPT, load_overrides(overrides_file))
    assert ranked(conn) == {"fixture_a:1", "fixture_b:2"}
    assert conn.execute("SELECT SUM(needs_review) FROM products").fetchone()[0] == 0


def test_reject_removes_the_listing_everywhere():
    conn = fixture_ambiguous_db()
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))
    out = MemoryDir()
    review.export_review(conn, PROMPT, date(2026, 9, 17), out_dir=out)
    overrides_file = MemoryFile()
    review.apply_review(MemoryFile(fill_in(out.file.text, "reject")), overrides_file)
    build(conn, REGISTRY, PROMPT, load_overrides(overrides_file))
    assert [r[0] for r in conn.execute("SELECT listing_id FROM offers")] == ["fixture_a:1"]


def test_nothing_unverified_writes_no_file():
    conn = connect(":memory:")
    add_listing(conn, "fixture_a", "1", 14.99)
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))
    assert review.export_review(conn, PROMPT, date(2026, 9, 17), out_dir=MemoryDir()) == (None, 0)


def test_apply_keeps_existing_overrides_and_skips_blank_rows():
    existing = MemoryFile("split: ['fixture_x:9']\nexclude: ['fixture_y:1']\n")
    conn = fixture_ambiguous_db()
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))
    out = MemoryDir()
    review.export_review(conn, PROMPT, date(2026, 9, 17), out_dir=out)
    counts = review.apply_review(MemoryFile(out.file.text), existing)  # nothing filled in
    data = yaml.safe_load(existing.text)
    assert counts == {"approved": 0, "rejected": 0, "merged": 0, "skipped": 1}
    assert data["split"] == ["fixture_x:9"] and data["exclude"] == ["fixture_y:1"]


@pytest.mark.parametrize(
    ("decision", "values"),
    [("approve", ""), ("approve-with-values", ""), ("approve-with-values", "price=1"),
     ("approve-with-values", "pack_units=lots")],
)  # fmt: skip
def test_bad_decisions_are_refused_with_a_clear_error(decision, values):
    conn = fixture_ambiguous_db()
    build(conn, REGISTRY, PROMPT, Overrides(split=set(), merge={}))
    out = MemoryDir()
    review.export_review(conn, PROMPT, date(2026, 9, 17), out_dir=out)
    with pytest.raises(review.ReviewError):
        review.apply_review(MemoryFile(fill_in(out.file.text, decision, values)), MemoryFile())


def test_real_overrides_file_loads():
    if Path("config/product_overrides.yml").exists():
        load_overrides()


# --- regression guard (brief §14) -------------------------------------------------------


def meta(products, **classes):
    return {"counts": {"products": products, "classes": classes}}


def test_guard_passes_when_nothing_is_lost():
    assert check(meta(71, mg_glycinate=4), meta(70, mg_glycinate=3, mg_citrate=1)) == []


def test_guard_blocks_when_a_table_empties():
    problems = check(meta(71, mg_glycinate=4, zn_citrate=2), meta(69, mg_glycinate=4, zn_citrate=0))
    assert problems == ["class zn_citrate had ranked products before and has none now"]


def test_guard_blocks_a_large_overall_drop():
    assert check(meta(71, a=40), meta(30, a=20)) == ["products fell from 71 to 30"]


def test_guard_allows_the_first_ever_run():
    assert check({}, meta(71, a=4)) == []
