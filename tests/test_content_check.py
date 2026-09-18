"""Brief §20.3-20.5: the claim linter. The page below is a structural fixture, not real
content — its "findings" are placeholders and it is never published."""

import pytest

from pipeline.content_check import (
    ANECDOTE_HEADER,
    GP_LINE,
    SECTIONS,
    build_manifest,
    check_page,
    fingerprint,
    load_banned,
    word_count,
)

BANNED = load_banned()
BRANDS = ["Fixture Brand", "Holland & Barrett"]
FILLER = " ".join(["Fixture sentence about forms and label amounts only."] * 12)


def fixture_page(**changes):
    frontmatter = {
        "compound_id": "magnesium",
        "content_version": 1,
        "generated_at": "2026-09-17",
        "model_id": "fixture-model",
        "sources": "[PMID 1, PMID 2]",
        "review_status": "draft",
    }
    frontmatter.update(changes.pop("frontmatter", {}))
    card = "Trials measured a fixture outcome and found a fixture result. Grade: Limited. PMID: 12345\n"
    sections = {
        "What it is": FILLER,
        "Forms, explained": FILLER,
        "How it works": FILLER + " PMID: 111 and PMID: 222.",
        "What the research says": f"### Card one\n{card}\n### Card two\n{card}\n### Card three\n{card}"
        + FILLER,
        "What people report": f"{ANECDOTE_HEADER}\n\nPeople commonly mention taking it in the evening. {FILLER}",
        "Things to know": f"{FILLER}\n\n{GP_LINE}",
        "Compare prices": "[Compare magnesium prices](/c/magnesium/)",
    }
    sections.update(changes)
    head = "\n".join(f"{key}: {value}" for key, value in frontmatter.items())
    body = "\n\n".join(
        f"## {title}\n\n{sections[title]}" for title in SECTIONS if sections[title] is not None
    )
    return f"---\n{head}\n---\n{body}\n"


def problems(**changes):
    return check_page(fixture_page(**changes), "magnesium", BANNED, BRANDS)


def test_a_well_formed_page_passes():
    assert problems() == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Magnesium cures cramps.",
        "It treats insomnia.",
        "This prevents deficiency.",
        "It boosts energy.",
        "A clinically proven dose.",
        "Great for immune support.",
        "You should take 400 mg.",
        "The best supplement for sleep.",
    ],
)
def test_banned_wording_is_refused(sentence):
    found = problems(**{"What it is": FILLER + " " + sentence})
    assert any("banned wording" in p for p in found), sentence


def test_neutral_study_language_is_allowed():
    text = FILLER + " Trials measured sleep-onset time and found a small reduction in one group."
    assert problems(**{"What it is": text}) == []


def test_research_card_without_citation_or_grade_is_refused():
    card = "### Card one\nTrials found something.\n\n### Card two\nGrade: Limited. PMID: 1\n\n### Card three\nGrade: Mixed. PMID: 2\n"
    found = problems(**{"What the research says": card + FILLER})
    assert "research card 'Card one' has no citation (PMID or DOI)" in found
    assert "research card 'Card one' has no evidence grade" in found


def test_anecdotes_must_be_labelled_and_may_not_quote_or_name_anyone():
    assert any("must open with" in p for p in problems(**{"What people report": FILLER}))
    quoted = f'{ANECDOTE_HEADER}\n\nOne person said "this completely changed how I sleep every night". {FILLER}'
    assert any("quote" in p for p in problems(**{"What people report": quoted}))
    named = f"{ANECDOTE_HEADER}\n\nAs u/fixture_user explains, evenings are common. {FILLER}"
    assert any("names a user" in p for p in problems(**{"What people report": named}))


def test_brand_names_are_refused_above_compare_prices():
    found = problems(**{"Forms, explained": FILLER + " Holland & Barrett sell a citrate."})
    assert any("Holland & Barrett" in p for p in found)


def test_gp_line_section_order_and_frontmatter_are_enforced():
    assert any("pharmacist/GP" in p for p in problems(**{"Things to know": FILLER}))
    assert any("in order" in p for p in problems(**{"How it works": None}))
    assert any("missing `model_id`" in p for p in [
        *check_page(fixture_page().replace("model_id: fixture-model\n", ""), "magnesium", BANNED, [])
    ])  # fmt: skip


def test_approved_needs_a_named_reviewer_and_folder_must_match():
    assert any("reviewed_by" in p for p in problems(frontmatter={"review_status": "approved"}))
    ok = {"review_status": "approved", "reviewed_by": "Patrick", "reviewed_on": "2026-09-17"}
    assert problems(frontmatter=ok) == []
    assert any("folder" in p for p in check_page(fixture_page(), "zinc", BANNED, []))


def test_length_is_checked():
    assert any(
        "words" in p for p in problems(**{"What it is": "Short."}, **{"Forms, explained": "Short."})
    )


APPROVED = {"review_status": "approved", "reviewed_by": "Patrick", "reviewed_on": "2026-09-17"}


def test_no_page_is_approved_before_the_grading_rules_are():
    page = fixture_page(frontmatter=APPROVED)
    found = check_page(page, "magnesium", BANNED, BRANDS, rubric_approved=False)
    assert any("grading rules" in p for p in found)
    assert check_page(fixture_page(), "magnesium", BANNED, BRANDS, rubric_approved=False) == []


def test_the_at_a_glance_excerpt_is_checked_too():
    glance = " ".join(["Fixture words describe forms and label amounts only."] * 14)  # 112
    assert problems(frontmatter={"at_a_glance": glance}) == []
    assert any(
        "at_a_glance is 2 words" in p for p in problems(frontmatter={"at_a_glance": "Too short."})
    )
    found = problems(frontmatter={"at_a_glance": glance + " It boosts energy."})
    assert any("in at_a_glance" in p for p in found)


def test_citations_must_be_studies_in_the_evidence_file():
    found = check_page(fixture_page(), "magnesium", BANNED, BRANDS, known_pmids={"111", "222"})
    assert found == ["cites studies that are not in evidence.json: 12345"]
    known = {"111", "222", "12345"}
    assert check_page(fixture_page(), "magnesium", BANNED, BRANDS, known_pmids=known) == []


def test_link_addresses_are_not_counted_as_words():
    assert word_count("See [PMID 1](https://pubmed.ncbi.nlm.nih.gov/1/) and **this**.") == 5


def test_the_manifest_lists_only_approved_pages_that_pass(tmp_path):
    for compound, frontmatter in (("magnesium", APPROVED), ("zinc", APPROVED), ("creatine", {})):
        (tmp_path / compound).mkdir()
        text = fixture_page(frontmatter={**frontmatter, "compound_id": compound})
        # Saved with Windows line endings: the fingerprint must not change.
        (tmp_path / compound / "learn.md").write_bytes(text.replace("\n", "\r\n").encode())
    results = {"magnesium": [], "zinc": ["a problem"], "creatine": []}
    manifest = build_manifest(results, {"status": "approved"}, content_dir=tmp_path)
    assert [page["compound_id"] for page in manifest["pages"]] == ["magnesium"]
    expected = fixture_page(frontmatter={**APPROVED, "compound_id": "magnesium"})
    assert manifest["pages"][0]["sha256"] == fingerprint(expected)
    assert fingerprint("﻿a\r\nb") == fingerprint("a\nb")
    assert manifest["rubric"] == {"status": "approved"}
