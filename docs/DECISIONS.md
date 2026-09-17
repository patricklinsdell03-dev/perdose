# Decisions log

Add a row whenever a rule, factor, model id, schema, or scope changes. Cite sources for factor changes.

| Date | Decision | Why | Alternatives considered | Affects |
|---|---|---|---|---|
| 2026-09-17 | Adopt brief v1.4 | — | — | all |
| 2026-09-17 | Model ids confirmed: default `claude-haiku-4-5-20251001`, escalation `claude-sonnet-5`. Checked against the models overview at https://docs.claude.com (redirects to https://platform.claude.com/docs/en/about-claude/models/overview). Both are listed as current Claude API ids. **Watch:** the same page lists Haiku 4.5 retirement as "not sooner than 2026-10-15" — re-check before Phase 2 and choose a successor if one is announced. The structured-output mechanism is not checked yet; that check belongs to Phase 2 (brief §9.2). | CLAUDE.md requires the check before first use | — | `config/llm.yml` |
| 2026-09-17 | `daily.yml` ships with manual trigger only; the cron line is present but commented out until Phase 5. | Until Phase 3 `make all` cannot succeed, so a live cron would fail (and email) every day. Brief §17 puts the working cron in Phase 5. | Enable now and let it fail; make unbuilt commands exit 0 (rejected: a silent no-op looks like a successful run) | `.github/workflows/daily.yml` |
| 2026-09-17 | Pipeline subcommands that are not built yet print "not built yet — Phase N" and exit 1. Only `golden` runs (on an empty set). | Honest failure beats silent success | Exit 0 stubs | `pipeline/cli.py`, `make all` |
| 2026-09-17 | Python project and npm package are named `pipeline` and `site`, not the working site name. | CLAUDE.md: the name lives only in `config/site.yml`. (`data/perdose.sqlite` and `PERDOSE_LIVE_LLM` are kept because the brief names them.) | — | `pyproject.toml`, `site/package.json` |
