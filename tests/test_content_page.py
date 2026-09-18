"""Brief §20.2: assembling a learn page. The prose is an invented fixture; what is tested is
the code's part - figures, grades, sources, fixed lines, links - and that the result passes
`make content-check`."""

from datetime import date

from pipeline.compounds import load_registry
from pipeline.content.config import load_content_config
from pipeline.content.grade import Reading as GradeInput
from pipeline.content.grade import grade
from pipeline.content.page import (
    amount_text,
    build_page,
    copied_phrases,
    forms_table,
    link_citations,
)
from pipeline.content.reader import Topic, check_reading
from pipeline.content.writer import CardPlan
from pipeline.content_check import (
    ANECDOTE_HEADER,
    GP_LINE,
    check_page,
    load_banned,
    sections_of,
    split_page,
)
from tests.content_fixtures import READING, fixture_studies, page_prose

REGISTRY = load_registry()
MAGNESIUM = REGISTRY.get("magnesium")
RULES = load_content_config().grading
STUDIES = fixture_studies()
BY_PMID = {s.pmid: s for s in STUDIES}
EXPORT = {
    "classes": [
        {
            "id": "mg_glycinate",
            "ranked": [
                {"amount_per_serving": 100.0, "amount_unit": "mg"},
                {"amount_per_serving": 200.0, "amount_unit": "mg"},
            ],
        }
    ]
}
THREE = [
    ("outcome-a", "Outcome A", ["90000001", "90000005", "90000011"]),
    ("outcome-b", "Outcome B", ["90000002"]),
    ("outcome-c", "Outcome C", ["90000011"]),
]


def assemble(topics=THREE, export=EXPORT, prose=None):
    _, readings = check_reading(READING, [s for s in STUDIES if s.role == "research"])
    plans = []
    for topic_id, label, pmids in topics:
        studies = [BY_PMID[p] for p in pmids]
        inputs = [
            GradeInput(s.is_review, readings[s.pmid].participants, readings[s.pmid].finding)
            for s in studies
        ]
        plans.append(CardPlan(Topic(topic_id, label), grade(inputs, RULES), studies))
    return build_page(
        compound=MAGNESIUM,
        prose=prose or page_prose(tuple(t[0] for t in topics)),
        plans=plans,
        readings=readings,
        studies=STUDIES,
        export=export,
        today=date(2026, 9, 18),
        model_id="fixture-model",
        prompt_version="content-test",
        content_version=1,
    )


def test_assembled_page_passes_content_check():
    text, problems = assemble()
    assert problems == ["removed a citation of PMID 99999999 (not a study it was given)"]
    known = {s.pmid for s in STUDIES}
    assert check_page(text, "magnesium", load_banned(), [], True, known) == []


def test_frontmatter_is_a_draft_with_its_sources():
    meta, body = split_page(assemble()[0])
    assert meta["review_status"] == "draft" and meta["reviewed_by"] is None
    assert meta["compound_id"] == "magnesium" and meta["content_version"] == 1
    assert [s["pmid"] for s in meta["sources"]][:2] == ["90000021", "90000001"]
    assert "99999999" not in body
    assert "PMID" not in meta["at_a_glance"]


def test_code_writes_grades_sources_and_fixed_lines():
    text, _ = assemble()
    sections = sections_of(split_page(text)[1])
    research = sections["What the research says"]
    strong = (
        "### Outcome A\n\n**Evidence: Strong** · 2 reviews · "
        "1,200 participants in the largest review"
    )
    assert strong in research
    assert "**Evidence: Moderate** · 1 review · 480 participants" in research
    assert "**Evidence: Insufficient** · no clear studies" in research  # its quote failed
    assert "[PMID 90000002](https://pubmed.ncbi.nlm.nih.gov/90000002/)" in research
    assert "[How we grade evidence](/methodology/#grading)" in research
    assert sections["What people report"].strip().startswith(ANECDOTE_HEADER)
    assert sections["Things to know"].strip().endswith(GP_LINE)
    assert "- - " not in sections["Things to know"]  # the model's own bullet is removed
    compare = sections["Compare prices"].strip()
    assert compare == "[Compare Magnesium prices per dose](/c/magnesium/)"


def test_without_prices_the_page_links_to_the_a_z():
    text, _ = assemble(export=None)
    assert "[Browse every supplement we compare](/a-z/)" in text
    assert "not in our price tables yet" in text


def test_forms_table_figures_come_from_the_rules_and_our_data():
    table = forms_table(MAGNESIUM, {"mg_glycinate": "Fixture | note."}, EXPORT)
    lines = table.splitlines()
    assert lines[0] == (
        "| Form | What's different | Elemental magnesium by weight "
        "| Per serving, on products we list |"
    )
    glycinate = next(line for line in lines if line.startswith("| Bisglycinate"))
    assert "about 11.7 %" in glycinate and "100 mg to 200 mg" in glycinate
    assert "Fixture / note." in glycinate  # a pipe would break the table
    other = next(line for line in lines if line.startswith("| Blends"))
    assert "stated on the label" in other and "not in our price tables yet" in other
    creatine = forms_table(REGISTRY.get("creatine"), {}, None).splitlines()[0]
    assert "by weight" not in creatine


def test_citations_become_links_and_strangers_are_removed():
    text, unknown = link_citations("Text [PMID 1234567, PMID 7654321].", {"1234567"})
    assert text == "Text ([PMID 1234567](https://pubmed.ncbi.nlm.nih.gov/1234567/))."
    assert unknown == ["7654321"]
    assert link_citations("Text (PMID 9999999).", set()) == ("Text.", ["9999999"])


def test_amounts_display_like_the_site():
    assert amount_text(5000, "mg") == "5 g"
    assert amount_text(100, "mcg") == "100 µg"
    assert amount_text(1000, "IU") == "1,000 IU"
    assert amount_text(112.5, "mg") == "112.5 mg"
    assert amount_text(2.5, "mg") == "2.5 mg"


def test_word_for_word_copying_is_caught():
    abstract = BY_PMID["90000011"].abstract
    copied = "We note that in this trial 120 adults were randomised to compound or placebo."
    assert copied_phrases(copied, [abstract]) == [
        "in this trial 120 adults were randomised to compound or placebo"
    ]
    assert copied_phrases("Trials measured outcome A in adults.", [abstract]) == []
