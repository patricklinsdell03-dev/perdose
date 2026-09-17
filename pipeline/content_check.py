"""`make content-check` (brief §20.3-20.5): the claim linter and structure check for learn pages.

A learn page is `content/<compound>/learn.md`: YAML frontmatter, then seven sections in a
fixed order. This checker involves no AI. It refuses banned wording, research cards with no
citation, anecdote sections that quote people or name brands, and pages marked approved
without a named reviewer. Only pages that pass AND are `review_status: approved` may build.
"""

import re
from pathlib import Path

import yaml

CONTENT_DIR = Path("content")
BANNED_PATH = Path("config/claims_banned.yml")

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


def check_page(text: str, compound_id: str, banned, brand_names: list[str]) -> list[str]:
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
    above = body.split("## Compare prices")[0].lower()
    for name in brand_names:
        if len(name) > 3 and re.search(rf"(?<![a-z]){re.escape(name.lower())}(?![a-z])", above):
            problems.append(f"names a brand or retailer above 'Compare prices': {name!r}")

    if GP_LINE not in sections.get("Things to know", ""):
        problems.append("'Things to know' must end with the fixed pharmacist/GP line")

    words = len(re.findall(r"\b\w+\b", body))
    if body.strip() and not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words; the template is {MIN_WORDS}-{MAX_WORDS}")
    return problems


def check_all(brand_names: list[str], content_dir: Path = CONTENT_DIR) -> dict[str, list[str]]:
    banned = load_banned()
    return {
        page.parent.name: check_page(
            page.read_text(encoding="utf-8"), page.parent.name, banned, brand_names
        )
        for page in sorted(content_dir.glob("*/learn.md"))
    }
