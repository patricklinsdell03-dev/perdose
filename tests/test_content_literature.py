"""Brief §20.3: finding studies in Europe PMC. Network calls are replaced by a fixture
transport that answers from tests/fixtures/fixture_europepmc.json (invented records)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline.compounds import load_registry
from pipeline.content.config import load_content_config
from pipeline.content.literature import (
    LiteratureError,
    Study,
    build_queries,
    clean_text,
    excluded,
    find_studies,
    parse_study,
    search_terms,
)

REGISTRY = load_registry()
CONFIG = load_content_config().literature
TODAY = date(2026, 9, 18)
FIXTURE = json.loads(Path("tests/fixtures/fixture_europepmc.json").read_text(encoding="utf-8"))


def group_of(request: httpx.Request) -> str:
    query = request.url.params["query"]
    if 'PUB_TYPE:"review"' in query:
        return "background"
    if 'PUB_TYPE:"randomized controlled trial"' in query:
        return "trials"
    return "reviews_recent" if request.url.params["sort"].startswith("P_PDATE") else "reviews_cited"


def fixture_client(calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(group_of(request))
        return httpx.Response(200, json={"resultList": {"result": FIXTURE[group_of(request)]}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_abstract_html_is_cleaned():
    text = "<h4>Background</h4>Fixture &amp; text.<br/><h4>Results</h4>More   text."
    assert clean_text(text) == "Background: Fixture & text. Results: More text."


def test_search_terms_use_the_name_unless_configured():
    assert search_terms(REGISTRY.get("magnesium"), CONFIG) == ["Magnesium"]
    assert search_terms(REGISTRY.get("vitamin_b1"), CONFIG) == ["Thiamine"]
    assert "vitamin D" in search_terms(REGISTRY.get("vitamin_d3"), CONFIG)


def test_queries_limit_titles_years_and_study_types():
    queries = build_queries(REGISTRY.get("magnesium"), CONFIG, TODAY)
    reviews, sort, _ = queries["reviews_cited"]
    assert 'TITLE:"Magnesium"' in reviews
    assert "PUB_YEAR:[2012 TO 2026]" in reviews
    assert 'PUB_TYPE:"meta-analysis"' in reviews and "supplement*" in reviews
    assert sort == "CITED desc"
    assert queries["reviews_recent"][1] == "P_PDATE_D desc"
    trials = queries["trials"][0]
    assert 'PUB_TYPE:"randomized controlled trial" AND NOT' in trials
    assert "supplement*" not in queries["background"][0]


def test_supplement_filter_can_be_switched_off():
    config = CONFIG.model_copy(update={"no_supplement_filter": ["magnesium"]})
    assert "supplement*" not in build_queries(REGISTRY.get("magnesium"), config, TODAY)["trials"][0]


def test_records_parse_and_bad_records_are_skipped():
    records = FIXTURE["reviews_cited"]
    study = parse_study(records[0], "research")
    assert study.pmid == "90000001" and study.year == 2016 and study.design == "meta-analysis"
    assert study.abstract.startswith("Background: Fixture background sentence.")
    assert "p < 0.01" in study.abstract
    assert parse_study(records[1], "research").design == "systematic review"  # type as a string
    assert parse_study(records[3], "research") is None  # no abstract
    assert parse_study({**records[0], "pmid": None}, "research") is None


def test_title_exclusions_match_whole_words():
    assert excluded("Magnesium given to rats", CONFIG.title_exclusions)
    assert excluded("Intravenous magnesium in surgery", CONFIG.title_exclusions)
    assert not excluded("Magnesium separates the fixture", CONFIG.title_exclusions)
    assert not excluded("Soiled fixture", ["soil"])


def test_find_studies_selects_dedupes_and_caches(tmp_path):
    calls: list[str] = []
    compound = REGISTRY.get("magnesium")
    studies, queries = find_studies(compound, CONFIG, TODAY, fixture_client(calls), tmp_path)
    assert sorted(calls) == ["background", "reviews_cited", "reviews_recent", "trials"]
    pmids = [s.pmid for s in studies]
    assert len(pmids) == len(set(pmids))  # the review found by both searches appears once
    assert "90000003" not in pmids  # rats: removed by the title filter
    assert "90000004" not in pmids  # no abstract
    assert {s.pmid for s in studies if s.role == "background"} == {"90000021"}
    assert pmids.index("90000005") < pmids.index("90000011")  # newest review kept, reviews first
    assert set(queries) == {"reviews_cited", "reviews_recent", "trials", "background"}

    again, _ = find_studies(compound, CONFIG, TODAY, fixture_client(calls), tmp_path)
    assert len(calls) == 4  # the same day's search is read from the cache
    assert again == studies


def test_limits_are_respected(tmp_path):
    config = CONFIG.model_copy(update={"max_reviews": 1, "max_trials": 1, "max_background": 0})
    compound = REGISTRY.get("magnesium")
    studies, _ = find_studies(compound, config, TODAY, fixture_client([]), tmp_path)
    assert [s.design for s in studies] == ["meta-analysis", "randomised trial"]
    assert all(isinstance(s, Study) for s in studies)


def test_a_failed_request_is_reported_without_the_url(tmp_path):
    def handler(request):
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(LiteratureError) as error:
        find_studies(REGISTRY.get("magnesium"), CONFIG, TODAY, client, tmp_path)
    assert "ebi.ac.uk" not in str(error.value)
