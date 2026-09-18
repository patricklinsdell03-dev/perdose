"""`make content` end to end with a fake research service and a fake AI: no network, no key,
no spending. Studies and answers are invented fixtures."""

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.compounds import load_registry
from pipeline.content.ai import ContentAI
from pipeline.content.config import load_content_config
from pipeline.content.reader import ReadingOut, StudyOut
from pipeline.content.run import ContentError, draft
from pipeline.content.writer import PageOut
from pipeline.content_check import split_page
from pipeline.settings import load_llm_config
from tests.content_fixtures import READING, FixtureClient, fixture_http, page_prose

REGISTRY = load_registry()
CONFIG = load_content_config()
LLM = load_llm_config()
TODAY = date(2026, 9, 18)


def run(tmp_path, answers, config=CONFIG, compound="magnesium", **kwargs):
    client = FixtureClient(answers)
    ai = ContentAI(LLM, config.prompt_version, client=client, cache_dir=tmp_path / "ai")
    report = draft(
        compound,
        today=TODAY,
        registry=REGISTRY,
        config=config,
        llm=LLM,
        ai=ai,
        http_client=fixture_http(),
        content_dir=tmp_path / "content",
        export_dir=Path("data/export"),
        literature_cache=tmp_path / "literature",
        **kwargs,
    )
    return report, client


def test_a_draft_page_and_its_evidence_are_written(tmp_path):
    report, client = run(tmp_path, [READING, page_prose()])
    assert [r["output_format"] for r in client.requests] == [ReadingOut, PageOut]
    assert all(r["model"] == "claude-sonnet-5" for r in client.requests)
    assert client.requests[0]["output_config"] == {"effort": "high"}

    page = (tmp_path / "content/magnesium/learn.md").read_text(encoding="utf-8")
    assert split_page(page)[0]["review_status"] == "draft"
    evidence = json.loads((tmp_path / "content/magnesium/evidence.json").read_text("utf-8"))
    assert all("abstract" not in study for study in evidence["studies"])
    assert {t["id"]: t["grade"] for t in evidence["topics"]} == {
        "outcome-a": "Strong",
        "outcome-b": "Moderate",
    }
    assert report.relevant == 4
    assert any("only 2 topics" in p for p in report.problems)
    assert any("PMID 99999999" in p for p in report.problems)
    assert evidence["draft_problems"] == report.problems
    # two answers of 10,000 tokens in and 2,000 out at $2 / $10 per million, at 0.75 £/$
    assert report.cost_gbp == pytest.approx(0.06)
    assert (report.calls, report.reused) == (2, 0)


def test_a_second_run_reuses_the_saved_answers(tmp_path):
    run(tmp_path, [READING, page_prose()])
    report, client = run(tmp_path, [])
    assert client.requests == [] and (report.calls, report.reused) == (0, 2)
    page = (tmp_path / "content/magnesium/learn.md").read_text(encoding="utf-8")
    assert split_page(page)[0]["content_version"] == 2


def test_an_approved_page_is_never_overwritten(tmp_path):
    folder = tmp_path / "content/magnesium"
    folder.mkdir(parents=True)
    (folder / "learn.md").write_text("---\nreview_status: approved\n---\nBody\n", "utf-8")
    with pytest.raises(ContentError, match="approved"):
        run(tmp_path, [READING, page_prose()])


def test_the_cap_stops_the_run_before_any_spending(tmp_path):
    budget = CONFIG.budget.model_copy(update={"max_gbp_per_page": 0.001})
    config = CONFIG.model_copy(update={"budget": budget})
    with pytest.raises(ContentError, match="cap"):
        run(tmp_path, [READING, page_prose()], config=config)
    assert not (tmp_path / "content").exists()


def test_a_dry_run_spends_nothing_and_writes_nothing(tmp_path):
    report, client = run(tmp_path, [], dry_run=True)
    assert client.requests == [] and not (tmp_path / "content").exists()
    assert 0 < report.estimate_gbp < CONFIG.budget.max_gbp_per_page
    assert {s.pmid for s in report.studies} >= {"90000001", "90000021"}


def test_unknown_supplement_and_nothing_relevant_are_reported(tmp_path):
    with pytest.raises(ContentError, match="unknown supplement"):
        run(tmp_path, [], compound="unobtainium")
    nothing = ReadingOut(
        topics=[],
        studies=[
            StudyOut.model_validate(
                {
                    **s.model_dump(),
                    "relevant": False,
                    "topic_id": None,
                    "not_relevant_reason": "fixture",
                }
            )
            for s in READING.studies
        ],
    )
    with pytest.raises(ContentError, match="none of the"):
        run(tmp_path, [nothing])
