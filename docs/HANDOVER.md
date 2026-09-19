# PerDose — handover and plan for the next chat

Written 2026-09-18, updated 2026-09-19 after an unattended run that finished Appendix F's
drafted backlog (batches 5–8). Paste the **opening prompt** at the bottom into a new chat;
everything else here is what that chat needs to know. Read alongside `CLAUDE.md` (rules),
`docs/BRIEF.md` (spec), `docs/DECISIONS.md` (every decision so far — long, but the 2026-09-19
entries at the point this file was last touched cover this run in full) and `docs/RUNBOOK.md`
(how to operate).

## 1. Where things stand

**Live:** https://perdose.co.uk — a Cloudflare Worker serving the static site, rebuilt on every
push to `main` of https://github.com/patricklinsdell03-dev/perdose (GitHub Actions runs
`make check` + the regression guard on every push). Contact address hello@perdose.co.uk
(Cloudflare Email Routing → Patrick's Gmail).

**Data:** still 124 real products from four hand-collected retailers (Bulk, Myprotein,
Holland & Barrett, Healthspan), unchanged this run. **No live feed is delivering products yet —
this is still the single biggest thing blocking real progress** (see §4, Phase 6).

**Registry: 136 compounds live** in `config/compounds.yml` (10 prototype + batches 1–8, each
with ≥ 3 golden labels). Golden set: **415 labels**, calc-only 415/415, saved-AI-reading replay
414/415 (one pre-existing, unrelated miss — `d28`, beta-alanine, from batch 1; not caused by
anything in this run, comfortably above the 90% threshold either way).

**Held back, each with its own open question (docs/DECISIONS.md 2026-09-19 has the full sourced
reasoning for each):**
- `kanna` (batch 5) — unresolved GB Novel Food status and whether the Psychoactive Substances
  Act 2016's exemptions cover it. Not one of the five compounds checked against the FSA/EU Novel
  Food Status Catalogue this run; would need that same check before it could ship.
- `agmatine` (batch 6) — **unauthorised GB novel food**, sourced: EU catalogue entry, absent
  from the GB Register of Novel Food Authorisations, RASFF border-rejection history.
- `dmae` (batch 7) — **unauthorised GB novel food**, same standard of evidence as agmatine.
- `uridine` (batch 7) — no determination found either way in either register; held as
  "unclear" rather than assumed lawful. A good candidate for a follow-up primary-source check.
- `nmn` (batch 8) — **unauthorised GB novel food**; the one pending GB application
  (EffePharm, RP-2116) is still "risk assessment – in progress".
- `lithium_orotate` (batch 8) — **unauthorised GB novel food** (the EU application was formally
  terminated without authorisation) *and* not on the permitted-minerals list in Schedule 1 to
  the Food Supplements (England) Regulations 2003 — two independent bars.

All six are fully drafted (compounds.yml entries, golden labels) and sit in
`config/drafts/batch_0N.yml` with the question spelled out in a `note:` field, ready to merge
in minutes once Patrick has an answer. **Ask him which (if any) he wants resolved**, rather than
re-deriving the legal research — it's already done and sourced.

**Also pending, not a legal question — just money:** two silica golden labels (`k46`, `k47`,
testing this run's ambiguity-handling fix and a missing combination case) are calc-only-verified
but never got a live AI check — **the Anthropic account ran out of API credit mid-run**
(`anthropic.BadRequestError: "Your credit balance is too low..."`, docs/DECISIONS.md 2026-09-19).
Silica already has 3 live-validated labels without these two, so nothing is blocked, but **add
credit at https://platform.claude.com (Plans & Billing) before running anything that calls the
API** (`make golden-live`, `make normalise`, `make content`) — then `make golden-live DRAFT=batch_06
ONLY=k46,k47` and move the two labels + their cache into the live files (both are sitting in
`tests/golden/drafts/batch_06.yml` under a "pending live validation" heading, ready to go).

**Independent-audit pattern (new this run):** every batch this run was checked by a separate
subagent that hadn't drafted it, using the same PASS/FIX/HOLD checklist the "Approving a drafted
batch" section of `docs/RUNBOOK.md` describes for a personal review. It caught real, previously
undetected issues in every single batch — worth using again for any future unattended run, or
even just as a second pair of eyes on a normal one. Full findings for each are in
`docs/DECISIONS.md`.

**Affiliate networks:** unchanged this run — see the 2026-09-18 entries in DECISIONS.md and
`docs/RETAILER_CANDIDATES.md`. Awin publisher account approved (ID 3098456); still waiting on a
GBP-priced feed and the profile fix Patrick was making.

**AI spend:** Claude Sonnet 5 for everything (Patrick's choice; never change models without
asking). Running total logged in DECISIONS.md was ~£5.25 of a £10 self-imposed grant before this
run; this run added roughly another £1.75 (batches 6/7/8 live validation, ~124 calls) before the
account's *actual* balance ran out — see above. The £10 figure is a spending-authorisation
ceiling Patrick set, not a live balance check; don't assume the two track each other.

## 2. Hard rules the next chat must keep

All of `CLAUDE.md`, plus these learned the hard way:
- **Never print, paste or commit any key or feed link.** Check `.env` variables by name/length
  only.
- Patrick edits `.env` himself; Claude never writes secrets into files.
- Nothing is scraped: retailers arrive only through official affiliate feeds. The four seed
  retailers are a stopgap, refreshed by hand (`make seed-refresh`).
- Golden label ids must not collide: `g` = prototype, `d/e/f/h` = batches 1–4, `j` = batch 5,
  `k` = batch 6, `m` = batch 7, `n` = batch 8. Use a fresh letter for the next batch (skip `l`).
- Log every spec-changing decision and every API spend in `docs/DECISIONS.md`.
- Windows tooling: run `uv`/`make` through PowerShell with the machine+user PATH prepended (see
  memory note `windows-tooling-path`); write commit messages to a file and use `git commit -F`
  (PowerShell 5.1 breaks on embedded quotes).
- **A draft batch's golden-label file uses 0-indent `- id:` list items; the live
  `tests/golden/labels.yml` uses 2-space-indented `  - id:` items throughout.** Merging one into
  the other needs a re-indent, or you get a YAML parse error that looks nothing like the actual
  cause (this bit this run once — see docs/DECISIONS.md 2026-09-19, batch 5). `config/compounds.yml`
  drafts don't have this problem; they're already 2-indented.
- `tests/test_golden.py` asserts the *live* golden set's saved-reading cache is **complete** —
  every label in `tests/golden/labels.yml` must have a cache file. A label added to the live set
  without a live AI check (e.g. because credit ran out mid-fix) fails `make check` with
  "saved extractions are incomplete" — hold it back in the draft file instead, as done for k46/k47.
- `make check` must be green before every commit; commit small; push to `main` (that deploys).

## 3. Decisions waiting on Patrick (ask, do not assume)

1. Which of the six held compounds (§1) he wants resolved, and how (kanna/uridine need a
   primary-source check like the one already done for the other four; agmatine/dmae/nmn/
   lithium_orotate need him to decide whether to wait for GB authorisation or drop them for good).
2. Add credit to the Anthropic account before anything that calls the API can run again.
3. Whether to draft the next Appendix F batch (checklist in `docs/RUNBOOK.md`) — Tier 3 is
   getting thin; the registry is close to Appendix F's ~150-compound target (see §21.3/Appendix F
   itself for what's left, mainly a handful of niche botanicals and the CFU/per-gram-macro
   compounds below).
4. **Probiotics**: proposed but not built (Patrick's explicit instruction this run). CFU-based
   comparison needs a new `cfu_count` normalisation type (brief §6.5, "later") and Patrick's
   answer to a few questions only he can settle — see the proposal in this run's chat report, or
   ask Claude to restate it. Digestive enzymes and everything in Appendix F.11 stay excluded.
5. Reapplications on Awin after the profile fix (Patrick clicks; Claude may do it in his Chrome
   only with his explicit say-so).
6. Nothing else is blocked on him unless a feed arrives.

## 4. The plan, phase by phase (brief §17 numbering)

### ▶ NEXT PHASE — Phase 6: first live feed end to end (unchanged bottleneck)

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
   that mention one of the 136 compounds. If it is thousands, tell Patrick the cost (~1p each)
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

### Phase 6b (continues in parallel): registry to launch scope — batches 1–8 done, registry near
Appendix F's target

136 compounds live, 6 held on legal questions (§1). Appendix F's ~150-compound registry is
mostly drafted now; what's left is a handful of niche Tier 3 botanicals never batched, plus the
compounds that genuinely need a new normalisation type:
- **`cfu_count`** for probiotics — proposed, not built (§3 item 4).
- **`per_gram_macro`** — the brief's original plan for collagen/colostrum/carbohydrate powders,
  but all three ended up using `simple_mass` instead (a precedent set for collagen 2026-09-18,
  followed for colostrum/carb powders 2026-09-19) so this type may never actually be needed —
  revisit only if a real compound can't be expressed with the six types already built.
- Digestive enzymes stay explicitly out of scope (brief F.8: "excluded until a type exists").

Do not start a new batch without asking Patrick first (§3 item 3) — Tier 3 is getting thin and
it may be closer to "top up specific gaps" than "another 15-compound batch" from here.

Launch gate (brief §17): ≥ 5 live feeds, the registry, ≥ 10 approved learn pages. Registry side
of the gate (≥ 100 compounds with ≥ 2 products each) still depends entirely on live feeds — 136
compounds are drafted but only the original 10 have any products at all.

### Phase 7 (re-ordered by Patrick, brief v1.8) — unchanged, not started
0. **Amazon live**: adapter exists; needs Associates API access.
0b. **Basket builder** filters, once several live feeds exist.
1–4. Effective price, price history, Alerts, Amazon PA-API — all v1.1+ backlog, unchanged.

### Phase 9: learn pages (brief §20) — unchanged, not started
`make content` is built. Next: Patrick approves the grading rules in `config/content.yml`, then
draft the first page (magnesium is a good first: most data), Patrick reviews it with
`content/REVIEW.md`, a solicitor reads that one page, then the rest.

### Design polish backlog (brief §12.4 refinement list)
The refinement pass of 2026-09-19 (brief v1.10, DECISIONS.md) brought the site up to mock-up B2:
card rows at every width, sticky dose bar, price-page headings, home example card and grouped
cards, header/footer, product and browse pages. Still open: a full design pass on the basket
page; spacing checked with Patrick on real phones. The "Capsule" language is fixed — refine
within it only.

## 5. Useful work while waiting for approvals (no input needed)
- Seed price refresh every ~2 weeks: `make seed-refresh` → fill the CSV → `make seed-refresh-apply`
  → `make all` (no AI calls).
- Re-read `docs/RETAILER_CANDIDATES.md` and check remaining names on Awin as Patrick asks.
- Once credit is added: finish live-validating k46/k47 (§1) — a five-minute job.
- Draft learn pages once the grading rules are approved (ask first: ~10–25p each; only after
  credit is restored).

## 6. Opening prompt for the new chat

```
Read CLAUDE.md, docs/HANDOVER.md, docs/BRIEF.md, docs/DECISIONS.md and docs/RUNBOOK.md in full
before doing anything. I am Patrick, not a programmer: explain in plain English before
non-trivial changes. The work is in C:\Users\patli\Documents\PerDose (git, main branch, pushing
deploys to https://perdose.co.uk).

Current state and rules are in docs/HANDOVER.md. Standing decisions: Claude Sonnet 5 for all AI
calls (never change models without asking); never print or write any key or feed link; no
scraping — retailers come only via affiliate feeds; every compound batch goes live only on my
explicit approval (or an independent audit if I'm not around); log decisions and API spend in
docs/DECISIONS.md; make check green before every commit. My AI budget for this chat is £[X] —
tell me before any step that spends more than 50p, and check the account actually has credit
before assuming it does.

Status of my Awin applications: [paste the latest]. The six held compounds (HANDOVER §1) are
[resolved / still open] — [say which, if any, to unblock].

Start by confirming you have read the four documents with five bullets on the current state,
then tell me the first thing you need from me, then begin.
```
