"""Assemble a learn page (brief §20.2) and its evidence file.

The AI's prose is slotted into a fixed template. Everything that must be exact is written
here: the forms table and its figures (from compounds.yml and our own price data), each
card's evidence grade (grade.py) and source list, citation links, the fixed lines, and the
link to the price tables. Citations the AI makes to studies it was not given are removed.
"""

import re
from datetime import date

import yaml

from pipeline.compounds import Compound
from pipeline.content.grade import CONFIDENCE, Grade
from pipeline.content.literature import Study
from pipeline.content.reader import StudyReading, Topic
from pipeline.content.writer import CardPlan, PageOut
from pipeline.content_check import ANECDOTE_HEADER, GP_LINE, readable_text

PUBMED = "https://pubmed.ncbi.nlm.nih.gov/{}/"
NO_THREADS = "No community discussions have been summarised for this page yet."
UNIT_LABEL = {"mg": "mg", "mcg": "µg", "IU": "IU"}
CITE = re.compile(r"[\[(]\s*PMID[^\])]*[\])]", re.IGNORECASE)


def _trim(value: float) -> str:
    digits = 2 if value < 10 else 1
    text = f"{value:,.{digits}f}".rstrip("0").rstrip(".")
    return text


def amount_text(value: float, unit: str) -> str:
    """Same display as the site (format.ts): 5000 mg -> "5 g", 100 mcg -> "100 µg"."""
    if unit == "mg" and value >= 1000:
        return f"{_trim(value / 1000)} g"
    if unit == "mcg" and value >= 1000:
        return f"{_trim(value / 1000)} mg"
    return f"{_trim(value)} {UNIT_LABEL.get(unit, unit)}"


def label_amounts(export: dict | None, class_id: str) -> str:
    """The amounts per serving stated on the ranked products we list in this class."""
    for cls in (export or {}).get("classes", []):
        if cls["id"] == class_id:
            amounts = [
                (o["amount_per_serving"], o["amount_unit"])
                for o in cls["ranked"]
                if o["amount_per_serving"] is not None
            ]
            if amounts:
                unit = amounts[0][1]
                low, high = min(a for a, _ in amounts), max(a for a, _ in amounts)
                if low == high:
                    return amount_text(low, unit)
                return f"{amount_text(low, unit)} to {amount_text(high, unit)}"
    return "not in our price tables yet"


def factor_text(factors: list[float]) -> str:
    if not factors:
        return "stated on the label"
    low, high = min(factors), max(factors)
    if low == high:
        return f"about {low * 100:.1f} %"
    return f"about {low * 100:.1f} to {high * 100:.1f} %"


def forms_table(compound: Compound, notes: dict[str, str], export: dict | None) -> str:
    with_factors = compound.normalisation_type == "mineral_elemental" and any(
        f.elemental_factor for f in compound.forms
    )
    quantity = compound.comparison_quantity
    head = ["Form", "What's different"]
    if with_factors:
        head.append(f"{quantity[0].upper()}{quantity[1:]} by weight")
    head.append("Per serving, on products we list")
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for class_id, info in compound.classes.items():
        cells = [info.label, notes.get(class_id, "").replace("|", "/").strip() or "-"]
        if with_factors:
            factors = [
                f.elemental_factor
                for f in compound.forms
                if f.form_class == class_id and f.elemental_factor
            ]
            cells.append(factor_text(factors))
        cells.append(label_amounts(export, class_id))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def link_citations(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """[PMID 123] -> a PubMed link; citations of studies outside `allowed` are removed and
    returned so the run can report them."""
    unknown: list[str] = []

    def replace(match: re.Match) -> str:
        ids = re.findall(r"\d{4,9}", match.group(0))
        unknown.extend(i for i in ids if i not in allowed)
        good = [i for i in dict.fromkeys(ids) if i in allowed]
        return "(" + ", ".join(f"[PMID {i}]({PUBMED.format(i)})" for i in good) + ")"

    linked = CITE.sub(replace, text)
    linked = re.sub(r"\s*\(\)", "", linked)  # a citation that was removed entirely
    linked = re.sub(r"\s+([.,;:])", r"\1", linked)
    return re.sub(r"[ \t]{2,}", " ", linked).strip(), unknown


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def grade_line(grade: Grade) -> str:
    parts = [_plural(n, w) for n, w in ((grade.reviews, "review"), (grade.trials, "trial")) if n]
    line = f"**Evidence: {grade.grade}** · {' and '.join(parts) or 'no clear studies'}"
    if grade.participants:
        largest = grade.participants_from == "largest review"
        where = "in the largest review" if largest else "across the trials"
        line += f" · {grade.participants:,} participants {where}"
    return line


def card_markdown(plan: CardPlan, prose, allowed: set[str]) -> tuple[str, list[str]]:
    unknown: list[str] = []
    lines = [f"### {plan.topic.label}", "", grade_line(plan.grade), ""]
    if prose is not None:
        for label, text in (
            ("Kinds of studies", prose.kinds_of_studies),
            ("What they measured", prose.what_measured),
            ("What they found", prose.what_found),
        ):
            linked, bad = link_citations(text, allowed)
            unknown += bad
            lines.append(f"- **{label}:** {linked}")
    lines.append(
        f"- **How confident to be:** {CONFIDENCE[plan.grade.grade]} "
        "[How we grade evidence](/methodology/#grading)"
    )
    sources = ", ".join(f"[PMID {s.pmid}]({PUBMED.format(s.pmid)})" for s in plan.studies)
    lines.append(f"- **Sources:** {sources}")
    return "\n".join(lines), unknown


def compare_block(compound: Compound, has_prices: bool) -> str:
    if has_prices:
        slug = compound.id.replace("_", "-")
        return f"[Compare {compound.name} prices per dose](/c/{slug}/)"
    return "[Browse every supplement we compare](/a-z/)"


def build_page(
    *,
    compound: Compound,
    prose: PageOut,
    plans: list[CardPlan],
    readings: dict[str, StudyReading],
    studies: list[Study],
    export: dict | None,
    today: date,
    model_id: str,
    prompt_version: str,
    content_version: int,
) -> tuple[str, list[str]]:
    """(the learn.md text, problems to report)."""
    problems: list[str] = []
    allowed = {s.pmid for s in studies if s.role == "background"}
    allowed |= {pmid for pmid, r in readings.items() if r.relevant}

    def report(unknown: list[str]) -> None:
        for pmid in unknown:
            problems.append(f"removed a citation of PMID {pmid} (not a study it was given)")

    def prose_text(text: str) -> str:
        linked, unknown = link_citations(text, allowed)
        report(unknown)
        return linked

    notes = {n.class_id: n.note for n in prose.form_notes}
    by_topic = {card.topic_id: card for card in prose.cards}
    cards = []
    for plan in plans:
        if plan.topic.id not in by_topic:
            problems.append(f"no text was written for the topic {plan.topic.label!r}")
        text, unknown = card_markdown(plan, by_topic.get(plan.topic.id), allowed)
        report(unknown)
        cards.append(text)

    points = [re.sub(r"^[-*•\s]+", "", point) for point in prose.things_to_know]
    things = "\n".join(f"- {prose_text(point)}" for point in points if point)
    sections = {
        "What it is": prose_text(prose.what_it_is),
        "Forms, explained": forms_table(compound, notes, export),
        "How it works": (
            f"**The short version.** {prose_text(prose.how_short)}\n\n"
            f"**A bit more.** {prose_text(prose.how_more)}"
        ),
        "What the research says": "\n\n".join(cards),
        "What people report": f"{ANECDOTE_HEADER}\n\n{NO_THREADS}",
        "Things to know": f"{things}\n\n{GP_LINE}",
        "Compare prices": compare_block(compound, export is not None),
    }
    body = "\n\n".join(f"## {title}\n\n{text}" for title, text in sections.items())

    by_pmid = {s.pmid: s for s in studies}
    cited = [p for p in dict.fromkeys(re.findall(r"PMID (\d+)", body)) if p in by_pmid]
    glance, _ = link_citations(prose.at_a_glance, set())  # no citations in the excerpt
    meta = {
        "compound_id": compound.id,
        "content_version": content_version,
        "generated_at": today.isoformat(),
        "model_id": model_id,
        "prompt_version": prompt_version,
        "review_status": "draft",
        "reviewed_by": None,
        "reviewed_on": None,
        "at_a_glance": glance,
        "sources": [
            {
                "pmid": pmid,
                "title": by_pmid[pmid].title,
                "year": by_pmid[pmid].year,
                "type": by_pmid[pmid].design,
            }
            for pmid in cited
        ],
    }
    head = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100)
    return f"---\n{head}---\n{body}\n", problems


def copied_phrases(text: str, sources: list[str], length: int = 10) -> list[str]:
    """Runs of `length`+ words that appear word for word in a source abstract (the page must
    be in its own words: abstracts belong to their publishers)."""

    def words(value: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", value.lower())

    grams = set()
    for source in sources:
        w = words(source)
        grams.update(tuple(w[i : i + length]) for i in range(len(w) - length + 1))
    w = words(readable_text(re.sub(r"\[PMID \d+\]\([^)]*\)", " ", text)))
    found, i = [], 0
    while i <= len(w) - length:
        if tuple(w[i : i + length]) in grams:
            j = i + length
            while j < len(w) and tuple(w[j - length + 1 : j + 1]) in grams:
                j += 1
            found.append(" ".join(w[i:j]))
            i = j
        else:
            i += 1
    return found


def evidence_record(
    *,
    compound: Compound,
    today: date,
    queries: dict[str, str],
    studies: list[Study],
    readings: dict[str, StudyReading],
    topics: list[Topic],
    grades: dict[str, Grade],
    on_page: list[str],
    model_id: str,
    prompt_version: str,
    draft_problems: list[str],
) -> dict:
    """content/<id>/evidence.json: what was searched, read and graded. No abstracts."""
    topic_rows = []
    for topic in topics:
        grade = grades.get(topic.id)
        row = {"id": topic.id, "label": topic.label, "on_page": topic.id in on_page}
        if grade:
            row.update(
                grade=grade.grade,
                leading_finding=grade.leading_finding,
                agree_share=grade.agree_share,
                reviews=grade.reviews,
                trials=grade.trials,
                participants=grade.participants,
                participants_from=grade.participants_from,
            )
        topic_rows.append(row)
    study_rows = []
    for study in studies:
        reading = readings.get(study.pmid)
        row = {
            "pmid": study.pmid,
            "url": PUBMED.format(study.pmid),
            "doi": study.doi,
            "title": study.title,
            "year": study.year,
            "journal": study.journal,
            "design": study.design,
            "cited_by": study.cited_by,
            "role": study.role,
        }
        if reading is not None:
            row.update(
                relevant=reading.relevant,
                not_relevant_reason=reading.reason,
                topic_id=reading.topic_id,
                outcome_measured=reading.outcome,
                participants=reading.participants,
                trials_included=reading.trials_included,
                finding=reading.finding,
                quotes=reading.quotes,
                notes=reading.notes,
            )
        study_rows.append(row)
    return {
        "compound_id": compound.id,
        "generated_at": today.isoformat(),
        "source": "Europe PMC (europepmc.org), PubMed records",
        "note": "Abstracts are not stored here (publishers' copyright); each study links to "
        "PubMed. Grades are computed by pipeline/content/grade.py from the readings below.",
        "model_id": model_id,
        "prompt_version": prompt_version,
        "queries": queries,
        "topics": topic_rows,
        "studies": study_rows,
        "draft_problems": draft_problems,
    }
