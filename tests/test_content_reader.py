"""Brief §20.3: the AI's reading of each study is checked against the abstract, the way the
label normaliser's evidence quotes are (§9.3). Fixture studies and answers are invented."""

from pipeline.compounds import load_registry
from pipeline.content.reader import build_message, check_reading, number_in, quote_found
from tests.content_fixtures import READING, fixture_studies

STUDIES = [s for s in fixture_studies() if s.role == "research"]


def test_message_lists_every_study_with_its_abstract():
    message = build_message(load_registry().get("magnesium"), STUDIES)
    assert message.startswith("SUPPLEMENT: Magnesium")
    for study in STUDIES:
        assert f"[PMID {study.pmid}]" in message and study.abstract in message


def test_quotes_must_be_in_the_abstract():
    abstract = "A total of 1,200 participants – from 14 trials – were pooled."
    assert quote_found("1,200 participants - from 14 trials", abstract)  # dash styles agree
    assert quote_found("  A TOTAL of 1,200  participants", abstract)
    assert not quote_found("1,300 participants", abstract)
    assert not quote_found(None, abstract) and not quote_found("  ", abstract)


def test_numbers_must_appear_in_their_quote():
    assert number_in(1200, "a total of 1,200 participants")
    assert number_in(14, "from 14 trials")
    assert not number_in(9, "Nine trials")
    assert not number_in(12, "120 adults")


def test_check_keeps_supported_values_and_drops_the_rest():
    topics, readings = check_reading(READING, STUDIES)
    assert [t.id for t in topics] == ["outcome-a", "outcome-b"]  # "Outcome B" slugged
    first = readings["90000001"]
    assert first.relevant and first.topic_id == "outcome-a"
    assert (first.participants, first.trials_included) == (1200, 14)
    assert first.finding == "favours_supplement" and "finding" in first.quotes

    second = readings["90000002"]
    assert second.topic_id == "outcome-b" and second.participants == 480
    assert second.trials_included is None  # "Nine" is not the number 9
    assert any("trials_included" in note for note in second.notes)

    trial = readings["90000011"]
    assert trial.finding == "unclear"  # its quote is not in the abstract
    assert any("finding dropped" in note for note in trial.notes)

    combo = readings["90000012"]
    assert not combo.relevant and combo.reason == "combination product"


def test_a_study_the_model_skipped_counts_as_not_read():
    answer = READING.model_copy(update={"studies": READING.studies[:1]})
    _, readings = check_reading(answer, STUDIES)
    assert readings["90000002"].reason == "not read by the model"
    assert not readings["90000002"].relevant
