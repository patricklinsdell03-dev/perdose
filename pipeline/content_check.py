"""`make content-check` (brief §20.3-20.5): the claim linter and structure check for learn pages.

A learn page is `content/<compound>/learn.md`: YAML frontmatter, then seven sections in a
fixed order. This checker involves no AI. It refuses banned wording, research cards with no
citation, anecdote sections that quote people or name brands, and pages marked approved
without a named reviewer. Only pages that pass AND are `review_status: approved` may build:
the check writes them (with a fingerprint of their text) to `data/export/learn.json`, and the
site builds a learn page only when it is listed there with a matching fingerprint.
"""

import hashlib
import json
import re
from pathlib import Path

import yaml

CONTENT_DIR = Path("content")
BANNED_PATH = Path("config/claims_banned.yml")
MANIFEST_PATH = Path("data/export/learn.json")

SECTIONS = [
    "What it is",
    "Forms, explained",
    "How it works",
    "What the research says",
    "What people report",
    "Things to know",
    "Compare prices",
]
FRONTMATTER_KEYS = [
    "compound_id",
    "content_version",
    "generated_at",
    "model_id",
    "sources",
    "review_status",
]
ANECDOTE_HEADER = "These are anecdotes people have shared, not evidence."
GP_LINE = (
    "If you take medication, are pregnant, or have a health condition, "
    "check with a pharmacist or GP first."
)
CITATION = re.compile(r"PMID:?\s*\d+|doi\.org/\S+|\bdoi:\s*\S+", re.IGNORECASE)
GRADES = {"Strong", "Moderate", "Limited", "Mixed", "Insufficient"}
MIN_WORDS, MAX_WORDS = 600, 900
GLANCE_MIN_WORDS, GLANCE_MAX_WORDS = 100, 120


def load_banned(path: Path = BANNED_PATH) -> list[tuple[re.Pattern, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [(re.compile(item["pattern"], re.IGNORECASE), item["why"]) for item in data["banned"]]


def split_page(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def sections_of(body: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+?)\s*$", body, flags=re.MULTILINE)
    return {
        title.strip(): content for title, content in zip(parts[1::2], parts[2::2], strict=False)
    }


def readable_text(markdown: str) -> str:
    """What a reader sees: link addresses, emphasis marks and table rules removed."""
    return re.sub(r"[\[\]*|#`]", " ", re.sub(r"\]\([^)]*\)", "]", markdown))


def word_count(markdown: str) -> int:
    return len(re.findall(r"\b\w+\b", readable_text(markdown)))


def _names_brand(text: str, brand_names: list[str]) -> list[str]:
    lowered = text.lower()
    return [
        name
        for name in brand_names
        if len(name) > 3 and re.search(rf"(?<![a-z]){re.escape(name.lower())}(?![a-z])", lowered)
    ]


def check_page(
    text: str,
    compound_id: str,
    banned,
    brand_names: list[str],
    rubric_approved: bool = True,
    known_pmids: set[str] | None = None,
) -> list[str]:
    """Every reason this page may not be published. Empty list = passes."""
    problems: list[str] = []
    meta, body = split_page(text)

    if not meta:
        problems.append("no frontmatter block")
    for key in FRONTMATTER_KEYS:
        if key not in meta:
            problems.append(f"frontmatter: missing `{key}`")
    if meta.get("compound_id") not in (None, compound_id):
        problems.append(
            f"frontmatter: compound_id is {meta['compound_id']!r}, folder is {compound_id!r}"
        )
    status = meta.get("review_status")
    if status not in (None, "draft", "approved"):
        problems.append(f"frontmatter: review_status must be draft or approved, not {status!r}")
    if status == "approved" and not (meta.get("reviewed_by") and meta.get("reviewed_on")):
        problems.append("frontmatter: an approved page needs reviewed_by and reviewed_on")
    if status == "approved" and not rubric_approved:
        problems.append(
            "the evidence grading rules (config/content.yml `grading`) are still a proposal: "
            "they must be approved before any page is"
        )

    sections = sections_of(body)
    if list(sections) != SECTIONS:
        problems.append(f"sections must be exactly, in order: {', '.join(SECTIONS)}")

    for pattern, why in banned:
        for match in pattern.finditer(body):
            line = body.count("\n", 0, match.start()) + 1
            problems.append(f"banned wording {match.group(0)!r} (body line {line}): {why}")

    research = sections.get("What the research says", "")
    cards = re.split(r"^### +(.+?)\s*$", research, flags=re.MULTILINE)
    titles, contents = cards[1::2], cards[2::2]
    if research and not 3 <= len(titles) <= 6:
        problems.append(f"research section has {len(titles)} cards; needs 3 to 6")
    for title, content in zip(titles, contents, strict=False):
        if not CITATION.search(content):
            problems.append(f"research card {title!r} has no citation (PMID or DOI)")
        if not any(re.search(rf"\b{grade}\b", content) for grade in GRADES):
            problems.append(f"research card {title!r} has no evidence grade")

    mechanism = sections.get("How it works", "")
    if mechanism and len(CITATION.findall(mechanism)) < 2:
        problems.append("'How it works' needs at least two citations")

    anecdotes = sections.get("What people report", "")
    if anecdotes:
        if ANECDOTE_HEADER not in anecdotes:
            problems.append(f"anecdote section must open with: {ANECDOTE_HEADER!r}")
        if re.search(r"[“\"][^”\"]{25,}[”\"]", anecdotes):
            problems.append("anecdote section appears to quote someone; patterns only, no quotes")
        if re.search(r"\bu/\w+|@\w{3,}", anecdotes):
            problems.append("anecdote section names a user")

    # No product, brand or retailer names above the final "Compare prices" block (§20.5).
    above = body.split("## Compare prices")[0]
    for name in _names_brand(above, brand_names):
        problems.append(f"names a brand or retailer above 'Compare prices': {name!r}")

    if GP_LINE not in sections.get("Things to know", ""):
        problems.append("'Things to know' must end with the fixed pharmacist/GP line")

    words = word_count(body)
    if body.strip() and not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words; the template is {MIN_WORDS}-{MAX_WORDS}")

    # The 100-120-word excerpt shown on the compound's price page (§12.1).
    glance = meta.get("at_a_glance")
    if glance:
        for pattern, why in banned:
            for match in pattern.finditer(glance):
                problems.append(f"banned wording {match.group(0)!r} in at_a_glance: {why}")
        for name in _names_brand(glance, brand_names):
            problems.append(f"at_a_glance names a brand or retailer: {name!r}")
        count = word_count(glance)
        if not GLANCE_MIN_WORDS <= count <= GLANCE_MAX_WORDS:
            problems.append(
                f"at_a_glance is {count} words; it should be {GLANCE_MIN_WORDS}-{GLANCE_MAX_WORDS}"
            )

    if known_pmids is not None:
        cited = set(re.findall(r"PMID:?\s*(\d+)", body, re.IGNORECASE))
        unknown = sorted(cited - known_pmids)
        if unknown:
            problems.append(f"cites studies that are not in evidence.json: {', '.join(unknown)}")
    return problems


def evidence_pmids(folder: Path) -> set[str] | None:
    path = folder / "evidence.json"
    if not path.exists():
        return None
    return {study["pmid"] for study in json.loads(path.read_text(encoding="utf-8"))["studies"]}


def check_all(
    brand_names: list[str], content_dir: Path = CONTENT_DIR, rubric_approved: bool = True
) -> dict[str, list[str]]:
    banned = load_banned()
    return {
        page.parent.name: check_page(
            page.read_text(encoding="utf-8"),
            page.parent.name,
            banned,
            brand_names,
            rubric_approved=rubric_approved,
            known_pmids=evidence_pmids(page.parent),
        )
        for page in sorted(content_dir.glob("*/learn.md"))
    }


def brand_names(export_dir: Path, retailer_names: set[str]) -> list[str]:
    """Retailer names plus every brand in the exported price tables."""
    names = set(retailer_names)
    for path in (export_dir / "compounds").glob("*.json"):
        for cls in json.loads(path.read_text(encoding="utf-8"))["classes"]:
            for group in ("ranked", "combinations", "unverified"):
                names |= {offer["brand"] for offer in cls[group] if offer["brand"]}
    return sorted(names)


def fingerprint(text: str) -> str:
    """sha256 of the page text with Windows line endings and a byte-order mark removed, so the
    same page gives the same fingerprint on Patrick's PC and on the build server."""
    return hashlib.sha256(text.lstrip("﻿").replace("\r\n", "\n").encode()).hexdigest()


def build_manifest(
    results: dict[str, list[str]], rubric: dict, content_dir: Path = CONTENT_DIR
) -> dict:
    """The pages the site may publish: approved and passing every check (brief §20.4)."""
    pages = []
    for compound_id, problems in sorted(results.items()):
        text = (content_dir / compound_id / "learn.md").read_text(encoding="utf-8")
        meta, _ = split_page(text)
        if problems or meta.get("review_status") != "approved":
            continue
        pages.append(
            {
                "compound_id": compound_id,
                "sha256": fingerprint(text),
                "content_version": meta.get("content_version"),
                "reviewed_by": meta.get("reviewed_by"),
                "reviewed_on": str(meta.get("reviewed_on")),
            }
        )
    return {"rubric": rubric, "pages": pages}
