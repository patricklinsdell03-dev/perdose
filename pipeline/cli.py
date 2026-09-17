"""Command-line entry point for the pipeline (brief §8). Used by the Makefile.

Subcommands whose phase has not arrived yet exist so the Makefile targets are wired up,
but they report that and exit non-zero — a command that silently does nothing would look
like a successful run.
"""

import argparse
import os
import sys

import anthropic

from pipeline.compounds import load_registry
from pipeline.golden import (
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

# subcommand -> (help text, phase in brief §17 that builds it)
NOT_BUILT_YET = {
    "content": ("draft a learn page + evidence.json", 9),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, _phase) in NOT_BUILT_YET.items():
        cmd = sub.add_parser(name, help=help_text)
        if name == "content":
            cmd.add_argument("--compound", default="")
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
    sub.add_parser("content-check", help="claim linter + structure check on content/*/learn.md")
    guard = sub.add_parser("guard", help="fail if the export lost tables since the last run")
    guard.add_argument("--before", required=True, help="the previous meta.json")
    golden = sub.add_parser("golden", help="run the golden label set, print pass/fail table")
    golden.add_argument("--live", action="store_true", help="call the real LLM (costs pennies)")
    return parser


def _make_extractor():
    from pipeline.normalise.llm import Extractor

    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY found. Copy .env.example to .env and add your key.")
        return None
    return Extractor(load_llm_config(), load_registry())


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


def run_golden(live: bool) -> int:
    registry = load_registry()
    labels = load_golden_labels()
    print(f"Golden set: {len(labels)} labels in {GOLDEN_PATH.as_posix()}")

    calc_rate = _print_results(
        "Calc-only (hand-written readings -> rules -> calculator; must be 100%)",
        labels,
        run_calc_only(registry, labels),
    )
    ok = calc_rate == 1.0

    if live or os.environ.get("PERDOSE_LIVE_LLM") == "1":
        extractor = _make_extractor()
        if extractor is None:
            return 1
        results = run_live(registry, labels, extractor)
        heading = f"Live LLM ({extractor.config.models.default.id}; threshold {PASS_THRESHOLD:.0%})"
        ok &= _print_results(heading, labels, results) >= PASS_THRESHOLD
        print(f"  API calls: {extractor.calls}; escalation rate: {extractor.escalation_rate:.0%}")
    else:
        results = run_replay(registry, labels, load_llm_config().prompt_version)
        if results:
            heading = f"Replay of saved LLM extractions (threshold {PASS_THRESHOLD:.0%})"
            ok &= _print_results(heading, labels, results) >= PASS_THRESHOLD
        else:
            print("\nNo saved LLM extractions yet - run `make golden-live` once a key is set.")

    gaps = coverage_gaps(registry, labels)
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


def run_content_check() -> int:
    import json

    from pipeline.content_check import check_all
    from pipeline.export.run import EXPORT_DIR
    from pipeline.ingest.run import load_retailers

    names = {r.name for r in load_retailers()}
    for path in (EXPORT_DIR / "compounds").glob("*.json"):
        for cls in json.loads(path.read_text(encoding="utf-8"))["classes"]:
            for group in ("ranked", "combinations", "unverified"):
                names |= {offer["brand"] for offer in cls[group] if offer["brand"]}
    results = check_all(sorted(names))
    if not results:
        print("content-check: no learn pages yet (content/<compound>/learn.md)")
        return 0
    for compound_id, problems in results.items():
        print(f"  {compound_id}  {'PASS' if not problems else 'FAIL'}")
        for problem in problems:
            print(f"         - {problem}")
    failed = sum(1 for problems in results.values() if problems)
    print(f"content-check: {len(results) - failed}/{len(results)} pages pass")
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
            return run_golden(args.live)
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
    _help, phase = NOT_BUILT_YET[args.command]
    print(f"'{args.command}' is not built yet - it arrives in Phase {phase} (docs/BRIEF.md §17).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
