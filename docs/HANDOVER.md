# PerDose — handover and plan for the next chat

Written 2026-09-18 at the end of the first build session. Paste the **opening prompt** at the
bottom into a new chat; everything else here is what that chat needs to know. Read alongside
`CLAUDE.md` (rules), `docs/BRIEF.md` (spec, v1.7), `docs/DECISIONS.md` (every decision so far)
and `docs/RUNBOOK.md` (how to operate).

## 1. Where things stand

**Live:** https://perdose.co.uk — a Cloudflare Worker serving the static site, rebuilt on every
push to `main` of https://github.com/patricklinsdell03-dev/perdose (GitHub Actions runs
`make check` + the regression guard on every push). Contact address hello@perdose.co.uk
(Cloudflare Email Routing → Patrick's Gmail).

**Data:** 99 real products from four retailers (Bulk, Myprotein, Holland & Barrett, Healthspan),
all hand-collected from product pages on 2026-09-17 (`data/seed/*.csv`). They cover only the
original 10 compounds, so the site shows 10 price-comparison compounds. **No live feed is
delivering products yet.**

**Registry:** 90 compounds live in `config/compounds.yml` (10 prototype + batches 1–4), each with
≥ 3 golden labels (277 labels; rules 277/277, saved AI readings 276/277). **Batch 5 (20 more) is
drafted in `config/drafts/batch_05.yml`, validated 60/60, and awaits Patrick's "approve batch 5".**
A compound only gets pages once a retailer's data contains products for it; the A–Z page lists
every known compound and marks the rest "awaiting retailer data".

**Affiliate networks:** Awin publisher account approved (ID 3098456). 1 programme joined
(Optimum Nutrition UK — its feed is priced in EUR, so nothing is kept until they supply GBP;
Patrick has messaged them). 25 pending. 4 rejected on 2026-09-18 because the Awin profile had
no website URL ("No URL given"): Pharmacy2U, Lloyds Pharmacy, Healthspan, Healthspan Elite.
Patrick is fixing the profile (Account → Promotional Spaces: name PerDose, URL
https://perdose.co.uk, type Comparison Engine), then reapplying. Impact.com marketplace declined
(new site); verification tag left in the page header. Full status: `docs/RETAILER_CANDIDATES.md`.

**AI spend:** Claude Sonnet 5 for everything (Patrick's choice; never change models without
asking). Under the current £5 grant about £3.75 is used, itemised in DECISIONS.md. Each new
batch of 20 compounds costs ~65p to validate; a first feed of ~N relevant products costs ~1p
per product, once (readings are cached).

**Learn pages (Phase 9) — tooling built 2026-09-18, second session; no page drafted yet. Patrick's decision: draft pages inside Claude Code sessions (his subscription), not via `make content` API calls — see DECISIONS.md.**
`make content COMPOUND=<id>` drafts a page from Europe PMC research (estimate ~19p for
magnesium; hard cap 50p a page; `DRY=1` is free). `make content-check` is part of `make check`
and writes `data/export/learn.json`; the site publishes only approved pages listed there with a
matching fingerprint. The evidence-grading rules in `config/content.yml` are a **proposal
awaiting Patrick** — no page can be approved before they are. Checklist: `content/REVIEW.md`.

## 2. Hard rules the next chat must keep

All of `CLAUDE.md`, plus these learned the hard way:
- **Never print, paste or commit the Awin feed link or any key.** The feed link contains the
  API key. Check `.env` variables by name/length only. (Two keys were exposed in chat this
  session; Patrick has been asked to regenerate the Awin key.)
- Patrick edits `.env` himself; Claude never writes secrets into files.
- Nothing is scraped: retailers arrive only through official affiliate feeds (brief v1.6/1.7).
  The four seed retailers are a stopgap, refreshed by hand (`make seed-refresh`).
- Every batch is drafted, validated (rules 100 %, live model ≥ 90 %), and goes live only on
  Patrick's explicit approval. Golden label ids must not collide: g = prototype, d/e/f/h/j =
  batches 1–5; use a fresh letter per batch (k, m, n …).
- Log every spec-changing decision and every API spend in `docs/DECISIONS.md`.
- Windows tooling: run `uv`/`make` through PowerShell with the machine+user PATH prepended
  (see memory note `windows-tooling-path`); never run bare `python` in Bash (Store stub hangs);
  regex-heavy edits via the Edit tool or a Python script, not sed/perl (they eat backslashes);
  PowerShell `Set-Content -Encoding utf8` adds a BOM — write files with .NET or Python instead.
- `make check` must be green before every commit; commit small; push to `main` (that deploys).

## 3. Decisions waiting on Patrick (ask, do not assume)

1. "approve batch 5" (20 compounds, already validated).
2. Whether to keep drafting while no feed delivers products (batch 6 ≈ 65p; ~£1.25 of the
   grant remains — ask before exceeding £5).
3. Reapplications on Awin after the profile fix (Patrick clicks; Claude may do it in his Chrome
   only with his explicit say-so, as on 2026-09-18).
4. Learn pages: approve (or change) the grading rules in `config/content.yml`; say which
   supplements to draft first and the budget (~10–25p each); whether to build the "What people
   report" thread summaries (needs his curated threads and a Reddit-terms check).
5. Nothing else is blocked on him unless a feed arrives.

## 4. The plan, phase by phase (brief §17 numbering)

### ▶ NEXT PHASE — Phase 6: first live feed end to end

Trigger: any Awin programme approves Patrick (he gets an email; the programme moves to "Joined").
Until then, the only useful work is section 5 below.

Steps, in order:
1. Patrick builds ONE shared Awin feed (Toolbox → Create-a-Feed, tick every advertiser of
   interest, CSV + gzip + all columns) and puts the link in `.env` as `AWIN_FEED_URL=` (the
   pipeline already supports one shared feed split by `advertiser_id`; see RUNBOOK
   "Connecting a live affiliate feed").
2. Add the approved retailer to `config/retailers.yml` (copy the `optimum_nutrition` entry;
   set its Awin advertiser id, `ships_from: GB`, shipping rule from its site, notes).
3. `make ingest` — read the `kept / dropped / not_gbp / invalid_row` counts. Kept = products
   that mention one of the 90 compounds. If it is thousands, tell Patrick the cost (~1p each)
   before `make normalise`; `config/llm.yml` `max_calls_per_run` (5000) is the hard stop.
4. `make normalise` → `make price` → inspect every new compound table with the export
   (`data/export/compounds/<id>.json`): dedupe correctness, unverified rate, claimed chips,
   combinations vs ranked, display names. Fix rule bugs with tests; use
   `config/product_overrides.yml` / `make review` for one-offs.
5. `make check`, commit, push. Check https://perdose.co.uk/ops/ (noindex) after deploy.
6. Once **two** live retailers work with no regressions, retire their seed CSVs (Phase 6 ✅ in
   the brief). Switch on the daily cron: uncomment the `schedule` lines in
   `.github/workflows/daily.yml`, add `AWIN_FEED_URL` and `ANTHROPIC_API_KEY` as GitHub Actions
   secrets (Patrick does this in the repo settings).
7. Expect surprises the seed data never showed: multipacks, bundles, EUR prices, missing
   descriptions, "sold by" marketplace sellers on H&B/Boots. Each is a rules/test change plus a
   DECISIONS row. Ambiguous = unverified, never guessed.

### Phase 6b (continues in parallel): registry to launch scope
- Approve batch 5 → 110 compounds. Draft batch 6 (≈20, all on existing rules): BCAA, EAA,
  ornithine, agmatine, betaine HCl, uridine, DMAE, beta-glucan, zinc carnosine, PHGG,
  glucomannan, inulin, sea moss, black seed oil, flaxseed oil (ALA), evening primrose (GLA),
  CLA, glycerol, lithium orotate, sodium bicarbonate, silica. Same recipe: `config/drafts/
  batch_06.yml` + `_factor_sources.yml` + 60 labels (ids `k01–k60`) via a scratchpad
  generator, `make golden DRAFT=batch_06`, `make golden-live DRAFT=batch_06` (~65p),
  fix misses with `ONLY=`, Patrick approves, merge (see RUNBOOK "Approving a drafted batch").
- After batch 6 the remaining Appendix F items need new normalisation types
  (`per_gram_macro` for collagen/colostrum/carb powders, `cfu_count` for probiotics,
  `per_serving` for electrolytes/multivitamins) — brief Phase 10; do not start without
  Patrick.
- Launch gate (brief §17): ≥ 5 live feeds, the registry, ≥ 10 approved learn pages.

### Phase 7: v1.1 items (brief §19, in order) — only after Phase 6 has two live retailers
1. Effective price with retailer sitewide codes (`config/promos.yml`, toggle on tables).
2. Price history (`data/history.sqlite`, sparklines, "lowest in 90 days").
3. Alerts via a Cloudflare Worker + KV (bolt-on; core stays static).
4. Amazon via Product Advertising API once Associates qualifies (currently excluded).

### Phase 9: learn pages (brief §20) — can run any time, but every page needs Patrick's
approval (`review_status: approved`) and must pass `make content-check`. `make content` is
built (2026-09-18; RUNBOOK "Learn pages"). Next: Patrick approves the grading rules, then draft
the first page (magnesium is a good first: most data), Patrick reviews it with
`content/REVIEW.md`, a solicitor reads that one page (brief §20.5), then the other nine.
Not built: the "What people report" thread summaries (placeholder text for now). No health
claims, no quotes/usernames/brands in anecdote sections, no automated Reddit crawling.

### Design polish backlog (brief §12.4 refinement list)
Best-row emphasis on phones; zero-results/empty states; spacing and dark-mode contrast on
real phones with Patrick; the "Capsule" language is fixed — refine within it only.

## 5. Useful work while waiting for approvals (no input needed)
- Seed price refresh every ~2 weeks: `make seed-refresh` → fill the CSV → `make seed-refresh-apply`
  → `make all` (no AI calls).
- Draft batch 6 (ask first: it spends ~65p).
- Re-read `docs/RETAILER_CANDIDATES.md` and check remaining names on Awin as Patrick asks.
- Draft learn pages once the grading rules are approved (ask first: ~10–25p each).

## 6. Opening prompt for the new chat

```
Read CLAUDE.md, docs/HANDOVER.md, docs/BRIEF.md (v1.7), docs/DECISIONS.md and docs/RUNBOOK.md
in full before doing anything. I am Patrick, not a programmer: explain in plain English before
non-trivial changes. The work is in C:\Users\patli\Documents\PerDose (git, main branch,
pushing deploys to https://perdose.co.uk).

Current state and rules are in docs/HANDOVER.md. Standing decisions: Claude Sonnet 5 for all
AI calls (never change models without asking); never print or write any key or feed link;
no scraping — retailers come only via affiliate feeds; every compound batch goes live only on
my explicit approval; log decisions and API spend in docs/DECISIONS.md; make check green
before every commit. My AI budget for this chat is £[X] — tell me before any step that
spends more than 50p.

The next phase is Phase 6, the first live feed end to end (HANDOVER §4). Status of my Awin
applications: [paste the latest — which programmes are Joined / Pending / Rejected, and
whether AWIN_FEED_URL is set in .env]. Batch 5 is [approved / not yet approved].

Start by confirming you have read the five documents with five bullets on the current
state, then tell me the first thing you need from me, then begin.
```
