from pipeline.db import SCHEMA, connect

EXPECTED_TABLES = {
    "listings",
    "extractions",
    "products",
    "product_actives",
    "offers",
    "offer_prices",
}


def _columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_schema_creates_every_table():
    conn = connect(":memory:")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_schema_is_idempotent():
    conn = connect(":memory:")
    conn.executescript(SCHEMA)


def test_no_unit_suffixed_columns():
    # CLAUDE.md rule 10: one base unit per compound, never baked into a column name.
    conn = connect(":memory:")
    for table in EXPECTED_TABLES:
        for column in _columns(conn, table):
            assert not column.endswith(("_mg", "_mcg", "_iu")), f"{table}.{column}"


def test_a_product_can_carry_several_actives():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO products (product_id, name, multi_ingredient, needs_review, created_at,"
        " updated_at) VALUES ('fixture_d3_k2', 'fixture', 0, 0, '2026-09-17', '2026-09-17')"
    )
    for compound, unit in (("vitamin_d3", "IU"), ("vitamin_k2", "mcg")):
        conn.execute(
            "INSERT INTO product_actives VALUES ('fixture_d3_k2', ?, 'f', 'c', 1, ?,"
            " 'stated_elemental', 0, 1)",
            (compound, unit),
        )
    assert conn.execute("SELECT COUNT(*) FROM product_actives").fetchone()[0] == 2
