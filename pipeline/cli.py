"""Command-line entry point for the pipeline (brief §8). Used by the Makefile.

Phase 0: only `golden` does anything. Every other subcommand exists so the Makefile
targets are wired up, but reports that it has not been built yet and exits non-zero —
a command that silently does nothing would look like a successful run.
"""

import argparse
import sys

from pipeline.golden import GOLDEN_PATH, load_golden_labels

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
    labels = load_golden_labels()
    print(f"Golden set: {len(labels)} labels in {GOLDEN_PATH.as_posix()}")
    if not labels:
        print("Nothing to run yet - labels arrive with the rules table in Phase 1.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "golden":
        return run_golden()
    _help, phase = NOT_BUILT_YET[args.command]
    print(f"'{args.command}' is not built yet - it arrives in Phase {phase} (docs/BRIEF.md §17).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
