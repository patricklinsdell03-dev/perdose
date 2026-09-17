"""Command-line entry point for the pipeline (brief §8). Used by the Makefile.

So far only `golden` does anything. Every other subcommand exists so the Makefile
targets are wired up, but reports that it has not been built yet and exits non-zero —
a command that silently does nothing would look like a successful run.
"""

import argparse
import sys

from pipeline.compounds import load_registry
from pipeline.golden import (
    GOLDEN_PATH,
    MIN_LABELS_PER_COMPOUND,
    PASS_THRESHOLD,
    coverage_gaps,
    load_golden_labels,
    run_calc_only,
)

# subcommand -> (help text, phase in brief §17 that builds it)
NOT_BUILT_YET = {
    "ingest": ("pull feeds / read seed CSVs -> data/raw", 3),
    "normalise": ("LLM extraction -> data/perdose.sqlite (cached)", 2),
    "price": ("dedupe, per-dose prices, ranking flags", 3),
    "export": ("write data/export/*.json for the site", 3),
    "content": ("draft a learn page + evidence.json", 9),
    "content-check": ("claim linter + frontmatter check on content/", 9),
    "review": ("export needs_review rows to data/review/<date>.csv", 5),
    "review-apply": ("turn a filled-in review CSV into product overrides", 5),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, _phase) in NOT_BUILT_YET.items():
        cmd = sub.add_parser(name, help=help_text)
        if name == "content":
            cmd.add_argument("--compound", default="")
    sub.add_parser("golden", help="run the golden label set, print pass/fail table")
    return parser


def run_golden() -> int:
    registry = load_registry()
    labels = load_golden_labels()
    print(f"Golden set: {len(labels)} labels in {GOLDEN_PATH.as_posix()}")
    print("Mode: calc-only (reference extractions -> rules -> calculator; no LLM)\n")
    results = run_calc_only(registry, labels)
    for label in labels:
        problems = results[label["id"]]
        print(f"  {label['id']}  {'PASS' if not problems else 'FAIL'}  {label['title'][:70]}")
        for problem in problems:
            print(f"         - {problem}")

    passed = sum(1 for problems in results.values() if not problems)
    rate = passed / len(labels) if labels else 0.0
    print(f"\n{passed}/{len(labels)} passed ({rate:.0%}); threshold {PASS_THRESHOLD:.0%}")
    gaps = coverage_gaps(registry, labels)
    for compound_id, count in gaps.items():
        print(f"  {compound_id}: only {count} golden labels (needs {MIN_LABELS_PER_COMPOUND})")
    return 0 if rate >= PASS_THRESHOLD and not gaps else 1


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
    args = build_parser().parse_args(argv)
    if args.command == "golden":
        return run_golden()
    _help, phase = NOT_BUILT_YET[args.command]
    print(f"'{args.command}' is not built yet - it arrives in Phase {phase} (docs/BRIEF.md §17).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
