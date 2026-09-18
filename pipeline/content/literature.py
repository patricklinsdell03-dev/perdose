"""Research studies for a learn page (brief §20.3), from Europe PMC.

Europe PMC mirrors PubMed and returns each study's publication type, abstract and citation
count in one free request, with no key or account. (The brief also names OpenAlex, which now
needs an account key, and Semantic Scholar, which throttles keyless use: DECISIONS.md.)

Abstracts belong to their publishers, so they are kept only in a local cache under data/raw/
(git-ignored). The AI reads them; they are never committed or published.
"""

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx

from pipeline.compounds import Compound
from pipeline.content.config import LiteratureConfig

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CACHE_DIR = Path("data/raw/literature")
REVIEWS = '(PUB_TYPE:"meta-analysis" OR PUB_TYPE:"systematic review")'
RECENT_REVIEW_SLOTS = 5  # of max_reviews, kept for the newest reviews (few citations yet)


class LiteratureError(Exception):
    """Europe PMC could not be reached or answered with something unexpected."""


@dataclass(frozen=True)
class Study:
    pmid: str
    title: str
    year: int
    journal: str | None
    doi: str | None
    pub_types: tuple[str, ...]
    cited_by: int
    abstract: str
    role: str  # "research" (graded on the page) or "background" (What it is / How it works)

    @property
    def design(self) -> str:
        types = {t.lower() for t in self.pub_types}
        if "meta-analysis" in types:
            return "meta-analysis"
        if "systematic review" in types:
            return "systematic review"
        if "randomized controlled trial" in types:
            return "randomised trial"
        return "review" if "review" in types else "other"

    @property
    def is_review(self) -> bool:
        return self.design in ("meta-analysis", "systematic review")


def clean_text(text: str) -> str:
    """Europe PMC abstracts carry HTML: section headings become 'Background: ...'."""
    text = re.sub(r"<h\d[^>]*>(.*?)</h\d>", r" \1: ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def search_terms(compound: Compound, config: LiteratureConfig) -> list[str]:
    if compound.id in config.terms:
        return config.terms[compound.id]
    return [re.sub(r"\s*\(.*?\)", "", compound.name).strip()]  # "Thiamine (B1)" -> "Thiamine"


def build_queries(
    compound: Compound, config: LiteratureConfig, today: date
) -> dict[str, tuple[str, str, int]]:
    """name -> (query, sort, how many). Titles must name the compound; studies must be
    human-indexed PubMed records with an abstract, in English, from the last `years` years."""
    titles = " OR ".join(f'TITLE:"{term}"' for term in search_terms(compound, config))
    years = f"PUB_YEAR:[{today.year - config.years + 1} TO {today.year}]"
    common = f"SRC:MED AND HAS_ABSTRACT:y AND LANG:eng AND {years}"
    supplement = (
        ""
        if compound.id in config.no_supplement_filter
        else ' AND (TITLE:supplement* OR ABSTRACT:supplement* OR ABSTRACT:"oral")'
    )
    research = f"({titles}){supplement} AND {common}"
    trials = f'{research} AND PUB_TYPE:"randomized controlled trial" AND NOT {REVIEWS}'
    background = f'({titles}) AND {common} AND PUB_TYPE:"review" AND NOT {REVIEWS}'
    return {
        "reviews_cited": (f"{research} AND {REVIEWS}", "CITED desc", 100),
        "reviews_recent": (f"{research} AND {REVIEWS}", "P_PDATE_D desc", 25),
        "trials": (trials, "CITED desc", 100),
        "background": (background, "CITED desc", 25),
    }


def parse_study(record: dict, role: str) -> Study | None:
    pmid = str(record.get("pmid") or "")
    title = clean_text(record.get("title") or "")
    abstract = clean_text(record.get("abstractText") or "")
    try:
        year = int(record.get("pubYear"))
    except (TypeError, ValueError):
        return None
    if not (pmid.isdigit() and title and abstract):
        return None
    types = (record.get("pubTypeList") or {}).get("pubType") or []
    if isinstance(types, str):
        types = [types]
    journal = ((record.get("journalInfo") or {}).get("journal") or {}).get("title")
    return Study(
        pmid=pmid,
        title=title,
        year=year,
        journal=journal,
        doi=record.get("doi"),
        pub_types=tuple(types),
        cited_by=int(record.get("citedByCount") or 0),
        abstract=abstract,
        role=role,
    )


def excluded(title: str, words: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", title, re.IGNORECASE) for word in words)


def fetch(client: httpx.Client, query: str, sort: str, size: int) -> list[dict]:
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": size}
    params["sort"] = sort
    try:
        response = client.get(API, params=params, timeout=60)
        response.raise_for_status()
        return response.json()["resultList"]["result"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise LiteratureError(f"Europe PMC request failed ({type(error).__name__})") from None


def citations_per_year(study: Study, today: date) -> float:
    return study.cited_by / max(1, today.year - study.year + 1)


def select(groups: dict[str, list[Study]], config: LiteratureConfig, today: date) -> list[Study]:
    """The studies the AI reads: the most-cited reviews per year since publication, a few of
    the newest reviews (too new to be cited much), then trials, then background reviews."""

    def best(studies: list[Study], n: int, taken: set[str]) -> list[Study]:
        unique = {s.pmid: s for s in studies if s.pmid not in taken}
        ranked = sorted(unique.values(), key=lambda s: (-citations_per_year(s, today), s.pmid))
        return ranked[:n]

    taken: set[str] = set()
    recent_slots = min(RECENT_REVIEW_SLOTS, config.max_reviews)
    reviews = best(groups["reviews_cited"], config.max_reviews - recent_slots, taken)
    taken |= {s.pmid for s in reviews}
    newest = sorted(
        {s.pmid: s for s in groups["reviews_recent"] + groups["reviews_cited"]}.values(),
        key=lambda s: (-s.year, -s.cited_by, s.pmid),
    )
    reviews += [s for s in newest if s.pmid not in taken][:recent_slots]
    taken |= {s.pmid for s in reviews}
    trials = best(groups["trials"], config.max_trials, taken)
    taken |= {s.pmid for s in trials}
    background = best(groups["background"], config.max_background, taken)
    return reviews + trials + background


def find_studies(
    compound: Compound,
    config: LiteratureConfig,
    today: date,
    client: httpx.Client | None = None,
    cache_dir: Path = CACHE_DIR,
) -> tuple[list[Study], dict[str, str]]:
    """(the selected studies, the queries used). Search results are cached per day, so
    re-running the same day asks Europe PMC nothing."""
    queries = build_queries(compound, config, today)
    path = cache_dir / compound.id / f"{today.isoformat()}.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if cached and cached.get("queries") == {name: q for name, (q, _, _) in queries.items()}:
        groups = {
            name: [Study(**{**s, "pub_types": tuple(s["pub_types"])}) for s in studies]
            for name, studies in cached["groups"].items()
        }
    else:
        owns_client = client is None
        client = client or httpx.Client(headers={"User-Agent": "perdose-content/1"})
        try:
            groups = {}
            for name, (query, sort, size) in queries.items():
                role = "background" if name == "background" else "research"
                parsed = (parse_study(record, role) for record in fetch(client, query, sort, size))
                groups[name] = [
                    s for s in parsed if s and not excluded(s.title, config.title_exclusions)
                ]
        finally:
            if owns_client:
                client.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "queries": {name: q for name, (q, _, _) in queries.items()},
                    "groups": {n: [asdict(s) for s in ss] for n, ss in groups.items()},
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return select(groups, config, today), {name: q for name, (q, _, _) in queries.items()}
