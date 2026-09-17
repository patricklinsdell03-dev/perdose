# PerDose — CLAUDE.md

UK supplement price comparison, normalised to **price per standard dose**. Static site + Python pipeline. Working name "PerDose" (rename later; do not hardcode the name outside `config/site.yml`).

**Read `docs/BRIEF.md` in full before doing anything. It is the spec.** If the brief and this file disagree, the brief wins. Log every decision that changes the brief in `docs/DECISIONS.md`.

## Who you are working with

- Patrick is not a programmer. Explain what you are about to do in two or three plain sentences before any non-trivial change, then do it. No jargon walls.
- Work **one phase at a time** (see brief §17). Do not start a later phase early. At the end of each phase, list what was built, how to run it, and what is still open.
- Ask when a domain rule is ambiguous (elemental factors, form classes, label conventions). Do not guess silently.

## Hard rules (never break these)

1. **Never fabricate data.** No invented products, prices, labels, EANs, retailer names or "example" rows that look real. Seed data comes only from `data/seed/*.csv` that Patrick supplies, or from live affiliate feeds. Test fixtures live under `tests/fixtures/` and are named `fixture_*` so they can never be mistaken for real data.
2. **The model extracts; the code computes.** The LLM only turns label text into structured fields. Every number that reaches a page (mg per serving, price per dose, cost per month) is computed in Python from those fields and the rules in `config/compounds.yml`.
3. **Ambiguous = not ranked.** Any product with `needs_review = true` is shown with an "unverified" badge at the bottom of tables, never in the ranked list.
4. **No health claims anywhere.** Evidence lines are factual, sourced, and about doses and forms — never about treating, curing or preventing anything. Affiliate disclosure on every page.
5. **No secrets in the repo.** `.env` only, `.env.example` committed. If you see a key in a file, stop and say so.
6. **Small commits, tests green.** One task per commit. Run `make check` (lint + tests + build) before every commit. Never commit with failing tests.
7. **Ask before destructive actions**: deleting files, rewriting a module wholesale, changing the SQLite schema, changing `compounds.yml` ids, force-pushing.
8. **British English, GBP, metric.** Dates ISO `YYYY-MM-DD`. Times Europe/London.
9. **Learn pages publish only when approved.** Overview content (brief §20) builds only with `review_status: approved`. Anecdote sections carry aggregate patterns and thread links only — never quotes, usernames, or product/brand names. No automated Reddit crawling.
10. **One base unit per compound.** Amounts are stored in the compound's declared unit (mg, mcg or IU); no `_mg` column names; a product can carry several actives (brief §5.2).

## Stack (details in brief §4)

- Pipeline: Python 3.12, `uv`, `pydantic` v2, `httpx`, `pyyaml`, stdlib `sqlite3`, `anthropic` SDK. Lint `ruff`, tests `pytest`.
- Site: Astro (static output), TypeScript, plain CSS with a small token file. Search: Pagefind. **Design language: "Capsule" (brief §12.4)** — refine within it, never change direction without asking.
- Hosting: Cloudflare Pages (free). Scheduling: GitHub Actions cron.
- LLM: **Patrick chooses the models** (DECISIONS.md 2026-09-17) — never pick or change them without asking. Model ids live in `config/llm.yml` — verify current ids at https://docs.claude.com before first use and record the check in DECISIONS.md.

## Commands

```
make setup      # uv sync + npm install
make ingest     # pull feeds / read seed CSVs -> data/raw
make normalise  # LLM extraction -> data/perdose.sqlite (cached)
make price      # compute per-dose prices, dedupe, export site JSON
make golden     # run the golden label set, print pass/fail table (no LLM calls: calc-only + replay)
make golden-live  # same, but calls the real LLM and saves results to tests/golden/cache/
make content COMPOUND=<id>   # draft a learn page + evidence.json (Phase 9)
make content-check           # claim linter + frontmatter check on content/
make review                  # export needs_review rows to data/review/<date>.csv
make review-apply            # turn filled-in review CSV into config/product_overrides.yml
make seed-refresh            # checklist of seed listings to re-price -> data/review/seed_refresh_<date>.csv
make seed-refresh-apply      # write the checked prices back into data/seed/*.csv (no AI calls)
make site       # astro build -> site/dist
make check      # ruff + pytest + astro check + build
make all        # ingest -> normalise -> price -> site
```

## Repo map

```
config/         compounds.yml, retailers.yml, llm.yml, site.yml, factor_sources.yml, priority.yml, claims_banned.yml
pipeline/       ingest/, normalise/, price/, export/, cli.py
data/           seed/ (Patrick's CSVs), raw/ (feed pulls, gitignored), perdose.sqlite (gitignored), export/ (site JSON, committed)
site/           Astro project
tests/          pytest; tests/golden/labels.yml is the golden set
content/        <compound>/learn.md, evidence.json, threads.yml (Phase 9); REVIEW.md checklist
docs/           BRIEF.md (spec), DECISIONS.md (log), RUNBOOK.md (how to operate)
```

## Core vs bolt-ons (brief §22)

The core is static: no accounts, no sessions, no server-side code, no runtime database. Learn pages, Alerts (Worker), the Stack calculator and the N=1 experiment app are bolt-ons that read core exports and link to core pages; the core never depends on them. Do not add a backend to the core to make a feature easier.

## Scope in one line

Prototype = 10 compounds on seed data (proves the pipeline). Launch = the Appendix F registry (~150 single-ingredient supplements across vitamins, minerals, amino acids, sports, fatty acids, botanicals, nootropic and general-health ingredients) on ≥ 5 live feeds, added in category batches (brief §17 Phase 6b, launch gate). Never add anything from Appendix F.11 (exclusions) without a DECISIONS.md entry.

## Definition of "prototype done" (brief §0)

Search "magnesium", pick "bisglycinate", see a table of real products from at least two retailers sorted by price per 100 mg elemental magnesium, each row linking out via an affiliate link, with unverified products separated. Golden set ≥ 27/30 passing. Site builds in CI and deploys to Cloudflare Pages.
