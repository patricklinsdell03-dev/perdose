"""AI call 1 (brief §20.3): read each study's abstract into the facts the grade needs.

The model only reads: is the study about the supplement, which topic, how many people, what
it found, each with the exact words from the abstract. Code checks every quote against the
abstract and drops what it cannot find, exactly as the label normaliser does (§9.3).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from pipeline.compounds import Compound
from pipeline.content.literature import Study

Finding = Literal[
    "favours_supplement", "no_clear_difference", "favours_control", "mixed", "unclear"
]


class TopicOut(BaseModel):
    id: str
    label: str


class StudyOut(BaseModel):
    pmid: str
    relevant: bool
    not_relevant_reason: str | None
    topic_id: str | None
    outcome_measured: str | None
    participants: int | None
    participants_quote: str | None
    trials_included: int | None
    trials_included_quote: str | None
    finding: Finding
    finding_quote: str | None


class ReadingOut(BaseModel):
    topics: list[TopicOut]
    studies: list[StudyOut]


SYSTEM = """\
You read research abstracts for a UK website that compares supplement prices. For each study
you record, from its abstract only, what it tells a reader about taking the named supplement.
You never add knowledge that is not in the abstract, never estimate, and never judge the
supplement.

For every study listed (by PMID) fill in:

1. relevant: true only if people took the supplement by mouth and it is the thing being
   tested - on its own, or as the only difference between the groups compared. false for
   injections or infusions, studies of diet or blood levels where no supplement was given,
   animal or laboratory studies, and products that combine it with other active ingredients
   (unless one group took it alone). A review is relevant if it pools such trials. When
   false, give a two-to-four-word not_relevant_reason ("intravenous use", "combination
   product", "diet only", "blood levels only"); when true, not_relevant_reason is null.

2. topics and topic_id: define between 3 and 8 topics, each an outcome that studies of this
   supplement commonly measure. Name each by the outcome measured, in everyday words, never
   as a disease or a treatment: "Blood pressure", "Sleep", "Muscle strength", "Mood scores"
   (not "Hypertension", "Insomnia treatment" or "Depression therapy"). Give each a short id
   in lower case with hyphens ("blood-pressure"). Put every relevant study under the one
   topic that matches its main outcome; studies of the same outcome share a topic. An
   irrelevant study has topic_id null.

3. outcome_measured: the main thing measured, in a few plain words ("resting blood pressure").

4. participants: the total number of people in the study - for a review, the total across
   the trials it pooled - only if the abstract states it; participants_quote copies the exact
   words that state it. For reviews, trials_included and trials_included_quote the same way.
   Leave both number and quote null when the abstract does not state them.

5. finding: what the abstract reports for the main outcome, compared with placebo or no
   supplement:
   - favours_supplement: a statistically significant difference in favour of the supplement
   - no_clear_difference: no statistically significant difference
   - favours_control: a significant difference against the supplement (worse, or harm)
   - mixed: some outcomes, doses or groups differ and others do not
   - unclear: the abstract does not say
   finding_quote copies the exact words from the abstract that show the finding (null only
   when the finding is unclear).

Every quote must be copied exactly, character for character, from that study's abstract, and
be under 30 words. A quote that cannot be found in the abstract is discarded, and so is the
value it supports.
"""


def build_message(compound: Compound, studies: list[Study]) -> str:
    names = ", ".join(dict.fromkeys([compound.name, *compound.aliases[:10]]))
    lines = [f"SUPPLEMENT: {compound.name}", f"Names used on labels: {names}", ""]
    lines.append(f"STUDIES ({len(studies)}):")
    for study in studies:
        lines += ["", f"[PMID {study.pmid}] {study.title} ({study.year}; {study.design})"]
        lines.append(study.abstract)
    return "\n".join(lines)


# --- checking the answer against the abstracts ---------------------------------------------

_DASHES = str.maketrans({"‐": "-", "‑": "-", "–": "-", "—": "-", "−": "-"})
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _plain(text: str) -> str:
    text = text.translate(_DASHES).translate(_QUOTES).lower()
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str | None, abstract: str) -> bool:
    return bool(quote and quote.strip()) and _plain(quote) in _plain(abstract)


def number_in(value: int, quote: str) -> bool:
    """The number itself appears in the quote ("1,200 participants" contains 1200)."""
    digits = re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", quote)
    return re.search(rf"(?<![\d.]){value}(?![\d.])", digits) is not None


@dataclass(frozen=True)
class Topic:
    id: str
    label: str


@dataclass
class StudyReading:
    pmid: str
    relevant: bool
    reason: str | None = None
    topic_id: str | None = None
    outcome: str | None = None
    participants: int | None = None
    trials_included: int | None = None
    finding: str = "unclear"
    quotes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def check_reading(
    answer: ReadingOut, studies: list[Study]
) -> tuple[list[Topic], dict[str, StudyReading]]:
    """Keep only what the abstracts support. Studies the model skipped count as not read."""
    topics: dict[str, Topic] = {}
    for topic in answer.topics:
        slug = re.sub(r"[^a-z0-9]+", "-", topic.id.lower()).strip("-")
        if slug and slug not in topics and topic.label.strip():
            topics[slug] = Topic(slug, topic.label.strip())

    given = {out.pmid.strip(): out for out in answer.studies}
    readings: dict[str, StudyReading] = {}
    for study in studies:
        out = given.get(study.pmid)
        if out is None:
            readings[study.pmid] = StudyReading(study.pmid, False, "not read by the model")
            continue
        reading = StudyReading(
            study.pmid,
            out.relevant,
            None if out.relevant else (out.not_relevant_reason or "not relevant"),
        )
        if out.relevant:
            slug = re.sub(r"[^a-z0-9]+", "-", (out.topic_id or "").lower()).strip("-")
            if slug in topics:
                reading.topic_id = slug
            else:
                reading.notes.append(f"topic {out.topic_id!r} is not one of the topics")
            reading.outcome = (out.outcome_measured or "").strip() or None
            for name in ("participants", "trials_included"):
                value, quote = getattr(out, name), getattr(out, f"{name}_quote")
                if value is None:
                    continue
                if quote_found(quote, study.abstract) and number_in(value, quote):
                    setattr(reading, name, value)
                    reading.quotes[name] = quote.strip()
                else:
                    reading.notes.append(
                        f"{name} {value} dropped: its quote is not in the abstract"
                    )
            if out.finding != "unclear":
                if quote_found(out.finding_quote, study.abstract):
                    reading.finding = out.finding
                    reading.quotes["finding"] = out.finding_quote.strip()
                else:
                    reading.notes.append("finding dropped: its quote is not in the abstract")
        readings[study.pmid] = reading
    return list(topics.values()), readings
