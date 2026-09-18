"""`make content COMPOUND=<id>` (brief §20.3): draft one learn page.

1. find studies in Europe PMC (free)          4. choose 3-6 topics and grade each (rules)
2. estimate the AI cost; stop if over the cap  5. AI call 2: write the prose
3. AI call 1: read each study                  6. assemble, check, save as a DRAFT

Nothing here publishes anything. The page is saved with `review_status: draft`; the site only
builds approved pages that pass `make content-check` (content/REVIEW.md).
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pipeline.compounds import Compound, Registry
from pipeline.content import reader, writer
from pipeline.content.ai import ContentAI, estimate_tokens
from pipeline.content.config import ContentConfig
from pipeline.content.grade import Grade, grade
from pipeline.content.grade import Reading as GradeInput
from pipeline.content.literature import LiteratureError, Study, find_studies
from pipeline.content.page import build_page, copied_phrases, evidence_record
from pipeline.content_check import check_page, load_banned, split_page
from pipeline.settings import LlmConfig

CONTENT_DIR = Path("content")
EXPORT_DIR = Path("data/export")
MIN_CARDS, MAX_CARDS = 3, 6
# Allowances for the cost estimate: answer tokens per study read, and for thinking + prose.
READING_OUT_PER_STUDY, READING_OUT_EXTRA, WRITING_OUT = 150, 4000, 8000


class ContentError(Exception):
    """Why no draft was made, in words for Patrick."""


@dataclass
class DraftReport:
    compound_id: str
    studies: list[Study] = field(default_factory=list)
    relevant: int = 0
    topics: list[tuple[str, str, bool]] = field(default_factory=list)  # label, grade, on page
    estimate_gbp: float | None = None
    cost_gbp: float | None = None
    calls: int = 0
    reused: int = 0
    problems: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)


def estimates(
    llm: LlmConfig, compound: Compound, research: list[Study], every: list[Study]
) -> tuple[float, float] | None:
    """Generous (reading, writing) cost estimates in pounds; None if the model has no price."""
    model = llm.content.id
    reading_in = estimate_tokens(reader.SYSTEM + reader.build_message(compound, research))
    reading_out = READING_OUT_PER_STUDY * len(research) + READING_OUT_EXTRA
    writing_in = estimate_tokens(writer.SYSTEM + "".join(s.abstract for s in every)) + 2000
    reading = llm.cost_gbp(model, reading_in, reading_out)
    writing = llm.cost_gbp(model, writing_in, WRITING_OUT)
    return None if reading is None or writing is None else (reading, writing)


def plan_cards(
    topics: list[reader.Topic],
    readings: dict[str, reader.StudyReading],
    research: list[Study],
    config: ContentConfig,
) -> tuple[dict[str, Grade], list[writer.CardPlan]]:
    """Grade every topic; the page gets the (up to) six with the most evidence behind them."""
    rules = config.grading
    grades: dict[str, Grade] = {}
    candidates = []
    for topic in topics:
        studies = [s for s in research if readings[s.pmid].topic_id == topic.id]
        if not studies:
            continue
        inputs = [
            GradeInput(s.is_review, readings[s.pmid].participants, readings[s.pmid].finding)
            for s in studies
        ]
        grades[topic.id] = result = grade(inputs, rules)
        weight = sum(
            rules.review_weight if s.is_review else rules.trial_weight
            for s in studies
            if readings[s.pmid].finding != "unclear"
        )
        ordered = sorted(studies, key=lambda s: (not s.is_review, -s.year, s.pmid))
        candidates.append((weight, result.participants or 0, topic, result, ordered))
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2].label))
    plans = [writer.CardPlan(topic, result, ordered) for _, _, topic, result, ordered in candidates]
    return grades, plans[:MAX_CARDS]


def draft(
    compound_id: str,
    *,
    today: date,
    registry: Registry,
    config: ContentConfig,
    llm: LlmConfig,
    ai: ContentAI | None = None,
    http_client=None,
    brand_names: list[str] | None = None,
    dry_run: bool = False,
    content_dir: Path = CONTENT_DIR,
    export_dir: Path = EXPORT_DIR,
    literature_cache: Path | None = None,
) -> DraftReport:
    compound = registry.get(compound_id)
    if compound is None:
        raise ContentError(f"unknown supplement {compound_id!r}: use an id from compounds.yml")
    if llm.content is None:
        raise ContentError("config/llm.yml has no `content` model")
    report = DraftReport(compound.id)
    folder = content_dir / compound.id
    page_path, evidence_path = folder / "learn.md", folder / "evidence.json"
    previous = split_page(page_path.read_text(encoding="utf-8"))[0] if page_path.exists() else {}
    if previous.get("review_status") == "approved":
        raise ContentError(
            f"{page_path.as_posix()} is approved; set review_status back to draft to redraft it"
        )

    kwargs = {"cache_dir": literature_cache} if literature_cache else {}
    try:
        studies, queries = find_studies(compound, config.literature, today, http_client, **kwargs)
    except LiteratureError as error:
        raise ContentError(str(error)) from None
    report.studies = studies
    research = [s for s in studies if s.role == "research"]
    background = [s for s in studies if s.role == "background"]
    if not research:
        raise ContentError(
            f"Europe PMC found no reviews or trials for {compound.name}; add better search "
            "words under literature.terms in config/content.yml"
        )
    parts = estimates(llm, compound, research, studies)
    report.estimate_gbp = sum(parts) if parts else None
    if dry_run:
        return report
    if parts is None:
        raise ContentError(f"no price for {llm.content.id} in config/llm.yml; cannot check cost")
    ai = ai or ContentAI(llm, config.prompt_version)
    reading_message = reader.build_message(compound, research)
    reading_cached = ai.cache_path("reading", compound.id, reader.SYSTEM, reading_message).exists()
    spend = (0.0 if reading_cached else parts[0]) + parts[1]
    cap = config.budget.max_gbp_per_page
    if spend > cap:
        raise ContentError(
            f"estimated cost £{spend:.2f} is over the £{cap:.2f} cap per page "
            "(config/content.yml budget); nothing was spent"
        )

    answer = ai.ask("reading", compound.id, reader.SYSTEM, reading_message, reader.ReadingOut)
    topics, readings = reader.check_reading(answer, research)
    report.relevant = sum(1 for r in readings.values() if r.relevant)
    grades, plans = plan_cards(topics, readings, research, config)
    on_page = [plan.topic.id for plan in plans]
    report.topics = [
        (t.label, grades[t.id].grade, t.id in on_page) for t in topics if t.id in grades
    ]
    if not plans:
        raise ContentError(
            f"the AI found none of the {len(research)} studies relevant; nothing was written "
            f"(its readings cost about £{ai.cost_gbp() or 0:.2f} and are saved for a re-run)"
        )
    if len(plans) < MIN_CARDS:
        report.problems.append(
            f"only {len(plans)} topics have relevant studies; the page needs 3 to 6 cards"
        )

    message = writer.build_message(compound, plans, readings, background)
    prose = ai.ask("writing", compound.id, writer.SYSTEM, message, writer.PageOut)

    export_path = export_dir / "compounds" / f"{compound.id}.json"
    export = json.loads(export_path.read_text(encoding="utf-8")) if export_path.exists() else None
    text, problems = build_page(
        compound=compound,
        prose=prose,
        plans=plans,
        readings=readings,
        studies=studies,
        export=export,
        today=today,
        model_id=ai.choice.id,
        prompt_version=config.prompt_version,
        content_version=int(previous.get("content_version") or 0) + 1,
    )
    report.problems += problems
    for phrase in copied_phrases(text, [s.abstract for s in studies]):
        report.problems.append(f"copies an abstract word for word: {phrase!r}")
    known = {s.pmid for s in studies}
    for problem in check_page(text, compound.id, load_banned(), brand_names or [], True, known):
        report.problems.append(f"content-check: {problem}")

    folder.mkdir(parents=True, exist_ok=True)
    page_path.write_text(text, encoding="utf-8", newline="\n")
    record = evidence_record(
        compound=compound,
        today=today,
        queries=queries,
        studies=studies,
        readings=readings,
        topics=topics,
        grades=grades,
        on_page=on_page,
        model_id=ai.choice.id,
        prompt_version=config.prompt_version,
        draft_problems=report.problems,
    )
    evidence_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    report.written = [page_path.as_posix(), evidence_path.as_posix()]
    report.calls, report.reused = ai.tally.calls, ai.tally.cached
    report.cost_gbp = ai.cost_gbp()
    return report
