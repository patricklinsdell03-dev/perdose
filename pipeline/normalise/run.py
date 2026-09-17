"""`make normalise`: extract every listing that has no cached extraction (brief §8, §9.2)."""

import hashlib
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from pipeline.normalise.llm import ExtractionFailed, Extractor

# Wrong key, no credit, bad request: a human must fix these, so the run fails loudly.
FATAL_API_ERRORS = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.BadRequestError,
    anthropic.NotFoundError,
)


class BudgetExceeded(Exception):
    pass


def content_hash(title: str, description: str | None) -> str:
    return hashlib.sha256(f"{title}{description or ''}".encode()).hexdigest()


def pending_listings(conn: sqlite3.Connection, prompt_version: str, force: bool) -> list[tuple]:
    """Distinct (content_hash, title, description) still to extract. Identical text across
    retailers shares one hash, so it is only ever sent once."""
    rows = conn.execute(
        "SELECT content_hash, title, description FROM listings GROUP BY content_hash"
    ).fetchall()
    if force:
        return rows
    done = {
        row[0]
        for row in conn.execute(
            "SELECT content_hash FROM extractions WHERE prompt_version = ?", (prompt_version,)
        )
    }
    return [row for row in rows if row[0] not in done]


def normalise(
    conn: sqlite3.Connection, extractor: Extractor, force: bool = False, limit: int | None = None
) -> dict[str, int | float]:
    config = extractor.config
    pending = pending_listings(conn, config.prompt_version, force)[:limit]
    if len(pending) > config.max_calls_per_run:
        raise BudgetExceeded(
            f"{len(pending)} listings to extract exceeds max_calls_per_run "
            f"({config.max_calls_per_run}); use --limit or raise the cap in config/llm.yml"
        )

    stats = {"pending": len(pending), "extracted": 0, "failed": 0, "outage": 0}
    for hash_, title, description in pending:
        try:
            result = extractor.extract(title, description or "")
        except FATAL_API_ERRORS:
            raise
        except anthropic.APIError as error:
            # Outage or rate limit: keep what we have, the rest waits for the next run (§18).
            print(f"WARNING: LLM unavailable ({type(error).__name__}); stopping this run early.")
            stats["outage"] = 1
            break
        except ExtractionFailed:
            stats["failed"] += 1
            continue
        conn.execute(
            "INSERT OR REPLACE INTO extractions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                hash_,
                config.prompt_version,
                result.model_id,
                result.extraction.model_dump_json(),
                result.extraction.confidence,
                int(result.escalated),
                datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        stats["extracted"] += 1

    stats["calls"] = extractor.calls
    stats["escalation_rate"] = round(extractor.escalation_rate, 3)
    return stats
