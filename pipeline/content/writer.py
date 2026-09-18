"""AI call 2 (brief §20.2-20.3): write the prose of a learn page from the studies.

The model writes words only. Code supplies everything that must be exact: the forms table
and its figures, each card's evidence grade and source list, the fixed lines, the links.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from pipeline.compounds import Compound
from pipeline.content.grade import Grade
from pipeline.content.literature import Study
from pipeline.content.reader import StudyReading, Topic


class FormNoteOut(BaseModel):
    class_id: str
    note: str


class CardOut(BaseModel):
    topic_id: str
    kinds_of_studies: str
    what_measured: str
    what_found: str


class PageOut(BaseModel):
    what_it_is: str
    form_notes: list[FormNoteOut]
    how_short: str
    how_more: str
    cards: list[CardOut]
    things_to_know: list[str]
    at_a_glance: str


SYSTEM = """\
You write one page of a UK website that helps people compare supplement prices. The page
explains one supplement in plain British English for a general reader who has already decided
to buy it and wants to understand it. The page is editorial, never advice: it never recommends
taking anything and never says what a supplement does for the reader.

Hard rules - a page that breaks one is rejected:
- Use only facts found in the material provided (the supplement facts and the abstracts).
  Add nothing from memory. If the material does not say something, leave it out.
- Describe research as what studies measured and found ("trials measured resting blood
  pressure and found a small average reduction"), never as what the supplement does ("it
  lowers blood pressure", "helps", "supports", "improves your ...").
- Never use these words or ideas: cure, treat, treatment for, prevent, heal, boost, detox,
  fight, combat, anti-ageing, miracle, superfood, wonder, "clinically proven", "proven to",
  "immune support", "you should take", "we recommend", "best supplement/brand/product".
- Name no brands, products, retailers, companies or branded ingredients.
- Write in your own words: never copy a sentence, or more than six words in a row, from an
  abstract.
- Cite studies only with the PMIDs given, written exactly as [PMID 12345678]. Cite a study
  only where it supports the sentence.
- British spelling (fibre, ageing, randomised, haemoglobin). Write "people" or "adults"
  rather than "patients"; if a study was in people with a condition, name the group neutrally
  ("adults with type 2 diabetes").
- Doses appear only as what studies used ("trials gave 300-400 mg a day"), never as advice.

Write these parts. Word counts are targets; the finished page, including the table, grades
and links the website adds, must stay between 600 and 900 words.
- what_it_is: 2-3 sentences: what the substance is, where it comes from, what it is sold as.
- form_notes: for each form class listed, one sentence (under 20 words) on what distinguishes
  that form, from chemistry and form facts only ("Magnesium bound to the amino acid glycine.").
- how_short: 3-4 sentences, "the short version" of what the body does with it, in everyday
  language, citing at least one study.
- how_more: 100-150 words, "a bit more" on the same, citing at least two different studies.
- cards: one per topic listed, in the order given, each with:
  kinds_of_studies - one sentence on the studies and who took part;
  what_measured - one sentence;
  what_found - one or two sentences on what they broadly found, consistent with the finding
  summary given for that topic, with the size of any effect if an abstract states it.
  Do not state a grade, a verdict or how confident to be: the website adds that.
- things_to_know: 3 or 4 short factual points: side effects the trials reported, groups the
  studies excluded or found differences in, and practical label facts (for example that
  labels give the amount per serving, which may be more than one capsule). No advice.
- at_a_glance: 100-120 words summarising the page for a price-comparison page - what it is,
  the forms sold, what the research broadly shows - in the same neutral style, no citations.
"""

FINDING_WORDS = {
    "favours_supplement": "mostly found a difference in favour of the supplement",
    "no_clear_difference": "mostly found no clear difference",
    "favours_control": "mostly found a difference against the supplement",
    None: "found no consistent result",
}


@dataclass(frozen=True)
class CardPlan:
    topic: Topic
    grade: Grade
    studies: list[Study]  # the relevant studies behind the grade, reviews first


def build_message(
    compound: Compound,
    cards: list[CardPlan],
    readings: dict[str, StudyReading],
    background: list[Study],
) -> str:
    lines = [
        f"SUPPLEMENT: {compound.name}",
        f"Compared on the website by: {compound.comparison_quantity}",
        "",
        "FORM CLASSES (id: label - names seen on labels):",
    ]
    for class_id, info in compound.classes.items():
        names = sorted({n for f in compound.forms if f.form_class == class_id for n in f.names})
        lines.append(f"- {class_id}: {info.label} - {', '.join(names)}")

    lines += ["", "TOPICS (write one card each, in this order):"]
    for number, card in enumerate(cards, 1):
        finding = FINDING_WORDS.get(card.grade.leading_finding, FINDING_WORDS[None])
        lines.append(
            f"{number}. topic_id {card.topic.id} - {card.topic.label}: "
            f"{card.grade.reviews} reviews and {card.grade.trials} trials; the studies {finding}."
        )
        for study in card.studies:
            reading = readings[study.pmid]
            size = (
                f"{reading.participants:,} participants"
                if reading.participants
                else "size not stated"
            )
            lines.append(
                f"   - PMID {study.pmid} ({study.design}, {study.year}, {size}): "
                f"{reading.outcome or 'outcome not stated'} - {reading.finding.replace('_', ' ')}"
            )

    lines += ["", "BACKGROUND REVIEWS (use for what_it_is and the how_ parts only):"]
    lines += [f"- PMID {s.pmid}: {s.title} ({s.year})" for s in background] or ["- none"]

    lines += ["", "ABSTRACTS:"]
    seen: set[str] = set()
    for study in [s for card in cards for s in card.studies] + background:
        if study.pmid in seen:
            continue
        seen.add(study.pmid)
        lines += ["", f"[PMID {study.pmid}] {study.title} ({study.year}; {study.design})"]
        lines.append(study.abstract)
    return "\n".join(lines)
