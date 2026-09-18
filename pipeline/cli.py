"""Command-line entry point for the pipeline (brief §8). Used by the Makefile."""

import argparse
import os
import sys

import anthropic

from pipeline.compounds import load_registry
from pipeline.golden import (
    CACHE_DIR,
    GOLDEN_PATH,
    MIN_LABELS_PER_COMPOUND,
    PASS_THRESHOLD,
    coverage_gaps,
    load_golden_labels,
    run_calc_only,
    run_live,
    run_replay,
)
from pipeline.settings import load_env, load_llm_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    content = sub.add_parser("content", help="draft a learn page + evidence.json (AI, pennies)")
    content.add_argument("--compound", default="")
    content.add_argument(
        "--dry-run", action="store_true", help="find the studies and estimate the cost only"
    )
    normalise = sub.add_parser("normalise", help="LLM extraction -> data/perdose.sqlite (cached)")
    normalise.add_argument("--force", action="store_true", help="re-extract cached listings")
    normalise.add_argument("--limit", type=int, default=None)
    ingest = sub.add_parser("ingest", help="read seed CSVs / feeds -> data/raw -> listings")
    ingest.add_argument("--retailer", default=None)
    ingest.add_argument("--date", default=None, help="YYYY-MM-DD; default today")
    sub.add_parser("price", help="dedupe, per-dose prices, ranking flags")
    sub.add_parser("export", help="write data/export/*.json for the site")
    sub.add_parser("review", help="export unverified listings to data/review/<date>.csv")
    apply = sub.add_parser("review-apply", help="fold a filled-in review CSV into the overrides")
    apply.add_argument("--file", default=None, help="default: the newest CSV in data/review")
    sub.add_parser("seed-refresh", help="write a price-check list for the seed listings")
    seed_apply = sub.add_parser("seed-refresh-apply", help="write checked prices into data/seed")
    seed_apply.add_argument("--file", default=None, help="default: the newest checklist")
    sub.add_parser("content-check", help="claim linter + structure check on content/*/learn.md")
    guard = sub.add_parser("guard", help="fail if the export lost tables since the last run")
    guard.add_argument("--before", required=True, help="the previous meta.json")
    golden = sub.add_parser("golden", help="run the golden label set, print pass/fail table")
    golden.add_argument("--live", action="store_true", help="call the real LLM (costs pennies)")
    golden.add_argument("--draft", default=None, help="test a drafted batch, e.g. batch_01")
    golden.add_argument("--only", default=None, help="comma-separated label ids (live re-runs)")
    return parser


def _make_extractor(registry=None):
    from pipeline.normalise.llm import Extractor

    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY found. Copy .env.example to .env and add your key.")
        return None
    return Extractor(load_llm_config(), registry or load_registry())


def _print_results(heading: str, labels: list[dict], results: dict[str, list[str]]) -> float:
    print(f"\n{heading}")
    for label in labels:
        if label["id"] not in results:
            continue
        problems = results[label["id"]]
        print(f"  {label['id']}  {'PASS' if not problems else 'FAIL'}  {label['title'][:70]}")
        for problem in problems:
            print(f"         - {problem}")
    passed = sum(1 for problems in results.values() if not problems)
    rate = passed / len(results) if results else 0.0
    print(f"  {passed}/{len(results)} passed ({rate:.0%})")
    return rate


def run_golden(live: bool, draft: str | None = None, only: str | None = None) -> int:
    from pathlib import Path

    labels_path, cache_dir, draft_path = GOLDEN_PATH, CACHE_DIR, None
    if draft:
        draft_path = Path("config/drafts") / f"{draft}.yml"
        labels_path = Path("tests/golden/drafts") / f"{draft}.yml"
        cache_dir = Path("tests/golden/drafts/cache") / draft
    registry = load_registry(draft=draft_path)
    labels = load_golden_labels(labels_path)
    if only:
        wanted = {item.strip() for item in only.split(",")}
        labels = [label for label in labels if label["id"] in wanted]
    print(f"Golden set: {len(labels)} labels in {labels_path.as_posix()}")

    calc_rate = _print_results(
        "Calc-only (hand-written readings -> rules -> calculator; must be 100%)",
        labels,
        run_calc_only(registry, labels),
    )
    ok = calc_rate == 1.0

    if live or os.environ.get("PERDOSE_LIVE_LLM") == "1":
        extractor = _make_extractor(registry)
        if extractor is None:
            return 1
        results = run_live(registry, labels, extractor, cache_dir)
        heading = f"Live LLM ({extractor.config.models.default.id}; threshold {PASS_THRESHOLD:.0%})"
        ok &= _print_results(heading, labels, results) >= PASS_THRESHOLD
        print(f"  API calls: {extractor.calls}; escalation rate: {extractor.escalation_rate:.0%}")
    else:
        results = run_replay(registry, labels, load_llm_config().prompt_version, cache_dir)
        if results:
            heading = f"Replay of saved LLM extractions (threshold {PASS_THRESHOLD:.0%})"
            ok &= _print_results(heading, labels, results) >= PASS_THRESHOLD
        else:
            print("\nNo saved LLM extractions yet - run `make golden-live` once a key is set.")

    gaps = {} if draft else coverage_gaps(registry, labels)
    for compound_id, count in gaps.items():
        print(f"  {compound_id}: only {count} golden labels (needs {MIN_LABELS_PER_COMPOUND})")
    return 0 if ok and not gaps else 1


def run_normalise(force: bool, limit: int | None) -> int:
    from pipeline.db import connect
    from pipeline.normalise.run import BudgetExceeded, normalise

    extractor = _make_extractor()
    if extractor is None:
        return 1
    try:
        stats = normalise(connect(), extractor, force=force, limit=limit)
    except BudgetExceeded as error:
        print(f"ABORTED: {error}")
        return 1
    print("normalise: " + ", ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


def run_ingest(retailer: str | None, run_date: str | None) -> int:
    from datetime import date

    from pipeline.db import connect
    from pipeline.ingest.run import ingest, load_exclusions, load_retailers

    load_env()  # feed URLs live in .env
    when = date.fromisoformat(run_date) if run_date else date.today()
    counts = ingest(
        connect(), load_registry(), load_retailers(), load_exclusions(), when, only=retailer
    )
    for retailer_id, count in counts.items():
        print(f"ingest: {retailer_id}: " + ", ".join(f"{k} {v}" for k, v in count.items()))
    if not counts:
        print("ingest: no retailer data found")
        return 1
    return 0


def run_price() -> int:
    from pipeline.db import connect
    from pipeline.price.build import build, load_overrides

    stats = build(connect(), load_registry(), load_llm_config().prompt_version, load_overrides())
    print("price: " + ", ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


def run_export() -> int:
    from pipeline.db import connect
    from pipeline.export.run import ExportTooLarge, export
    from pipeline.ingest.run import load_retailers

    try:
        stats = export(
            connect(), load_registry(), load_retailers(), load_llm_config().prompt_version
        )
    except ExportTooLarge as error:
        print(f"ABORTED: {error}")
        return 1
    print("export: " + ", ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


def run_review() -> int:
    from datetime import date

    from pipeline.db import connect
    from pipeline.review import export_review

    path, count = export_review(connect(), load_llm_config().prompt_version, date.today())
    if path is None:
        print("review: nothing is unverified - no file written")
        return 0
    print(f"review: {count} unverified listings -> {path.as_posix()}")
    print("Fill in the `decision` (and `values`) columns, then run `make review-apply`.")
    return 0


def run_review_apply(file: str | None) -> int:
    from pathlib import Path

    from pipeline.review import ReviewError, apply_review, latest_review_file

    path = Path(file) if file else latest_review_file()
    if path is None or not path.exists():
        print("review-apply: no review CSV found; run `make review` first")
        return 1
    try:
        counts = apply_review(path)
    except ReviewError as error:
        print(f"review-apply: {error}")
        return 1
    print(f"review-apply: {path.as_posix()}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Run `make price` to apply them.")
    return 0


def run_seed_refresh() -> int:
    from datetime import date

    from pipeline import seed_refresh

    seeds = seed_refresh.load_seeds()
    today = date.today()
    path = seed_refresh.REVIEW_DIR / f"{seed_refresh.PREFIX}{today.isoformat()}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(seed_refresh.checklist(seeds), encoding="utf-8", newline="\n")
    for retailer_id, stale in seed_refresh.stale_counts(seeds, today).items():
        print(f"  {retailer_id}: {stale} rows older than {seed_refresh.STALE_AFTER_DAYS} days")
    print(f"seed-refresh: checklist -> {path.as_posix()}")
    print("Open each url, fill in new_price_gbp / new_in_stock, then `make seed-refresh-apply`.")
    return 0


def run_seed_refresh_apply(file: str | None) -> int:
    from datetime import date
    from pathlib import Path

    from pipeline import seed_refresh

    path = Path(file) if file else seed_refresh.latest_checklist()
    if path is None or not path.exists():
        print("seed-refresh-apply: no checklist found; run `make seed-refresh` first")
        return 1
    try:
        checked_on = date.fromisoformat(path.stem.removeprefix(seed_refresh.PREFIX))
    except ValueError:
        checked_on = date.today()
    try:
        changed, counts = seed_refresh.apply(
            path.read_text(encoding="utf-8"), seed_refresh.load_seeds(), checked_on
        )
    except seed_refresh.SeedRefreshError as error:
        print(f"seed-refresh-apply: {error} (nothing was changed)")
        return 1
    for retailer_id, text in changed.items():
        target = seed_refresh.SEED_DIR / f"{retailer_id}.csv"
        target.write_text(text, encoding="utf-8", newline="\n")
    print(f"seed-refresh-apply: updated={counts['updated']}, left blank={counts['blank']}")
    print("Run `make all` to rebuild the site with the new prices (no AI calls needed).")
    return 0


def _brand_names() -> list[str]:
    from pipeline.content_check import brand_names
    from pipeline.export.run import EXPORT_DIR
    from pipeline.ingest.run import load_retailers

    return brand_names(EXPORT_DIR, {r.name for r in load_retailers()})


def run_content(compound_id: str, dry_run: bool) -> int:
    from datetime import date

    from pipeline.content.ai import DraftingFailed
    from pipeline.content.config import load_content_config
    from pipeline.content.run import ContentError, draft

    if not compound_id:
        print("Usage: make content COMPOUND=<id>  (ids are in config/compounds.yml)")
        return 1
    load_env()
    if not dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY found. Copy .env.example to .env and add your key.")
        return 1
    try:
        report = draft(
            compound_id,
            today=date.today(),
            registry=load_registry(),
            config=load_content_config(),
            llm=load_llm_config(),
            brand_names=_brand_names(),
            dry_run=dry_run,
        )
    except ContentError as error:
        print(f"content: {error}")
        return 1
    except DraftingFailed as error:
        print(f"content: {error}. Answers already received are saved; run it again to retry.")
        return 1
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise  # explained by main()
    except anthropic.APIError as error:
        print(
            f"content: the AI service returned an error ({type(error).__name__}). Answers "
            "already received are saved, so running it again later only pays for the rest."
        )
        return 1

    research = [s for s in report.studies if s.role == "research"]
    print(
        f"content: {report.compound_id}: {len(report.studies)} studies from Europe PMC "
        f"({len(research)} reviews and trials, {len(report.studies) - len(research)} background)"
    )
    if dry_run:
        for s in report.studies:
            print(f"  {s.design:18} {s.year} cited {s.cited_by:>4}  PMID {s.pmid}  {s.title[:70]}")
        estimate = "unknown" if report.estimate_gbp is None else f"about £{report.estimate_gbp:.2f}"
        print(f"Estimated AI cost to draft this page: {estimate}. Nothing was spent.")
        return 0
    print(f"  relevant to taking it as a supplement: {report.relevant} of {len(research)}")
    for label, grade, on_page in report.topics:
        print(f"  topic: {label} - {grade}" + ("" if on_page else " (not on the page)"))
    cost = "unknown" if report.cost_gbp is None else f"about £{report.cost_gbp:.2f}"
    print(f"  AI calls: {report.calls} new, {report.reused} reused; cost {cost}")
    print("  wrote " + " and ".join(report.written) + " (review_status: draft)")
    if report.problems:
        print(f"  to fix before approval ({len(report.problems)}):")
        for problem in report.problems:
            print(f"    - {problem}")
    print("Next: review the draft with content/REVIEW.md. Nothing is published until approved.")
    return 0


def run_content_check() -> int:
    import json
    from pathlib import Path

    from pipeline.content.config import load_content_config
    from pipeline.content.grade import describe, weighting_note
    from pipeline.content_check import MANIFEST_PATH, build_manifest, check_all, split_page

    grading = load_content_config().grading
    results = check_all(_brand_names(), rubric_approved=grading.status == "approved")
    rubric = {
        "status": grading.status,
        "grades": describe(grading),
        "weighting": weighting_note(grading),
    }
    manifest = build_manifest(results, rubric)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    if not results:
        print("content-check: no learn pages yet (content/<compound>/learn.md)")
        return 0
    failed = 0
    for compound_id, problems in results.items():
        page = Path("content") / compound_id / "learn.md"
        meta = split_page(page.read_text(encoding="utf-8"))[0]
        approved = meta.get("review_status") == "approved"
        if problems and approved:
            failed += 1
        state = "PASS" if not problems else ("FAIL" if approved else "DRAFT")
        print(f"  {compound_id}  {state}{' (approved)' if approved and not problems else ''}")
        for problem in problems:
            print(f"         - {problem}")
    publishable = len(manifest["pages"])
    print(f"content-check: {len(results)} pages, {publishable} approved and publishable")
    if failed:
        print(f"content-check: {failed} APPROVED page(s) fail the checks and will not be published")
    return 1 if failed else 0


def run_guard(before: str) -> int:
    from pathlib import Path

    from pipeline.export.run import EXPORT_DIR
    from pipeline.guard import check_files

    problems = check_files(Path(before), EXPORT_DIR / "meta.json")
    for problem in problems:
        print(f"guard: {problem}")
    print("guard: BLOCKED - do not deploy" if problems else "guard: ok")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
    args = build_parser().parse_args(argv)
    try:
        if args.command == "golden":
            return run_golden(args.live, args.draft, args.only)
        if args.command == "normalise":
            return run_normalise(args.force, args.limit)
        if args.command == "ingest":
            return run_ingest(args.retailer, args.date)
        if args.command == "price":
            return run_price()
        if args.command == "export":
            return run_export()
        if args.command == "review":
            return run_review()
        if args.command == "review-apply":
            return run_review_apply(args.file)
        if args.command == "seed-refresh":
            return run_seed_refresh()
        if args.command == "seed-refresh-apply":
            return run_seed_refresh_apply(args.file)
        if args.command == "content":
            return run_content(args.compound, args.dry_run)
        if args.command == "content-check":
            return run_content_check()
        if args.command == "guard":
            return run_guard(args.before)
    except anthropic.AuthenticationError:
        print(
            "\nThe API rejected the key (401). Check .env: the whole key must be on one line, "
            "as ANTHROPIC_API_KEY=sk-ant-..., and must not have been deleted on the console."
        )
        return 1
    except anthropic.PermissionDeniedError as error:
        print(f"\nThe API refused the request (403): {error.message}")
        return 1
    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    sys.exit(main())
