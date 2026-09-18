"""Shared fixtures for the learn-page tests: invented studies (tests/fixtures/
fixture_europepmc.json), invented AI answers, and a fake API client. Nothing here is real
research or real content."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from pipeline.content.literature import parse_study
from pipeline.content.reader import ReadingOut
from pipeline.content.writer import PageOut

FIXTURE = json.loads(Path("tests/fixtures/fixture_europepmc.json").read_text(encoding="utf-8"))
FILL = "Fixture words describe forms and label amounts only."  # 8 words, no banned wording


def fixture_studies():
    research = [
        parse_study(r, "research")
        for name in ("reviews_cited", "reviews_recent", "trials")
        for r in FIXTURE[name]
    ]
    background = [parse_study(r, "background") for r in FIXTURE["background"]]
    unique = {s.pmid: s for s in research + background if s and "rats" not in s.title}
    return list(unique.values())


def group_of(request: httpx.Request) -> str:
    query = request.url.params["query"]
    if 'PUB_TYPE:"review"' in query:
        return "background"
    if 'PUB_TYPE:"randomized controlled trial"' in query:
        return "trials"
    return "reviews_recent" if request.url.params["sort"].startswith("P_PDATE") else "reviews_cited"


def fixture_http(calls: list[str] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(group_of(request))
        return httpx.Response(200, json={"resultList": {"result": FIXTURE[group_of(request)]}})

    return httpx.Client(transport=httpx.MockTransport(handler))


def study(pmid, topic, participants, p_quote, finding, f_quote, trials=None, t_quote=None):
    return {
        "pmid": pmid,
        "relevant": True,
        "not_relevant_reason": None,
        "topic_id": topic,
        "outcome_measured": f"fixture {topic}",
        "participants": participants,
        "participants_quote": p_quote,
        "trials_included": trials,
        "trials_included_quote": t_quote,
        "finding": finding,
        "finding_quote": f_quote,
    }


READING = ReadingOut.model_validate(
    {
        "topics": [
            {"id": "outcome-a", "label": "Outcome A"},
            {"id": "Outcome B", "label": "Outcome B"},
        ],
        "studies": [
            study(
                "90000001",
                "outcome-a",
                1200,
                "A total of 1,200 participants from 14 trials were pooled",
                "favours_supplement",
                "Supplementation lowered outcome A compared with placebo",
                14,
                "1,200 participants from 14 trials",
            ),
            study(
                "90000002",
                "outcome-b",
                480,
                "Nine trials with 480 participants were included",
                "no_clear_difference",
                "No clear difference in outcome B was found",
                9,
                "Nine trials with 480 participants",  # "Nine" is a word: the 9 is dropped
            ),
            study(
                "90000005",
                "outcome-a",
                300,
                "Six trials with 300 participants",
                "favours_supplement",
                "Supplementation lowered outcome A",
            ),
            study(
                "90000011",
                "outcome-a",
                120,
                "120 adults were randomised",
                "favours_supplement",
                "an invented quote that is not in the abstract",
            ),
            {
                **study("90000012", None, None, None, "unclear", None),
                "relevant": False,
                "not_relevant_reason": "combination product",
            },
        ],
    }
)


def page_prose(topic_ids=("outcome-a", "outcome-b"), repeat=4):
    body = " ".join([FILL] * repeat)
    return PageOut.model_validate(
        {
            "what_it_is": f"{body} [PMID 90000021].",
            "form_notes": [
                {"class_id": "mg_glycinate", "note": "Fixture note on a glycine form."},
                {"class_id": "mg_citrate", "note": "Fixture note on a citrate form."},
            ],
            "how_short": f"{body} [PMID 90000021].",
            "how_more": f"{body} {body} [PMID 90000021] and [PMID 90000001, PMID 99999999].",
            "cards": [
                {
                    "topic_id": topic,
                    "kinds_of_studies": f"{body}",
                    "what_measured": "Fixture trials measured a fixture outcome.",
                    "what_found": f"They found a fixture result [PMID 90000001]. {body}",
                }
                for topic in topic_ids
            ],
            "things_to_know": [f"- {body}", body, body],
            "at_a_glance": " ".join([FILL] * 14),
        }
    )


class FixtureClient:
    """Stands in for anthropic.Anthropic(): answers from a queue, records each request."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=10_000, output_tokens=2_000)
        return SimpleNamespace(
            parsed_output=self.answers.pop(0), stop_reason="end_turn", usage=usage
        )
