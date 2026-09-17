# Runbook — how to operate the pipeline and site

Stub. Each section is filled in by the phase that builds the thing it describes (brief §14).

## First-time setup

1. Install `uv`, Node.js (LTS), `git` and GNU `make`.
2. `make setup` — installs Python and site dependencies.
3. Copy `.env.example` to `.env` and fill in keys (not needed until Phase 2).
4. `make check` — lint, tests, site type-check and build. Must be green before every commit.

Preview the site locally: `npm --prefix site run dev`.

## Daily commands

See the command list in `CLAUDE.md`. So far `make setup`, `make golden`, `make site` and `make check` work; the rest report which phase builds them.

`make golden` prints a pass/fail line per golden label. Until Phase 2 it runs in calc-only mode: no AI involved, it checks the rules and the price maths against hand-written readings of each label.

## How to add a retailer

Seed-CSV retailer (until live feeds, Phase 6):

1. Create `data/seed/<retailer_id>.csv` with the columns in `data/seed/README.md`. Real product pages only; leave unknowns blank. Put the nutrition/ingredients text in `description` — that is what the AI reads.
2. Add the retailer to `config/retailers.yml` (copy an existing entry; same `id` as the file name).
3. Run `make all`. Check the `ingest:` line shows the rows kept, and `price:` shows how many ranked.
4. Look at the new rows before trusting them (see "Checking a run" below).

## Checking a run

`make all` prints one line per step:

- `ingest: <retailer>: kept N, dropped M` — dropped rows mention no compound, or hit the exclusion list in `config/ingest.yml`.
- `normalise: pending=… extracted=… calls=… escalation_rate=…` — only new or changed listings cost API calls. Escalation above 15 % means the prompt needs attention.
- `price: listings=… products=… ranked_offers=… needs_review=…` — `products` lower than `listings` means listings were matched as the same product (by barcode, or by brand + form + pack + amount + other ingredients). If two different products were merged, add the listing to `split:` in `config/product_overrides.yml`.
- `export: files=… bytes=…` — what the site will read, in `data/export/`.

The data the site shows lives in `data/export/compounds/<compound>.json`: each class has `ranked` (sorted cheapest first), `combinations` (multi-ingredient, hidden until Phase 8) and `unverified` (with the reason).

## How to add a compound

1. Add an entry to `config/compounds.yml` (copy a similar compound). It needs: `id`, `name`, `category`, `tier`, `unit` (mg, mcg or IU), `standard_dose`, `label_convention`, `normalisation_type`, `aliases`, `accepted_cofactors`, and `forms` — each form with an `id`, `names`, a `class`, and an `elemental_factor` (or `null`). Never change an existing `id`.
2. For every non-null `elemental_factor`, add the chemical formula to `config/factor_sources.yml`. The tests recompute the factor from the formula and fail if they disagree by more than 1.5 %.
3. Add at least 3 golden labels for it in `tests/golden/labels.yml` (one straightforward, one awkward, one combination), each with a reference `extraction` and an `expect` block. List the compound under `compounds:` on each.
4. Run `make golden` — every label must pass — then `make check`.
5. (From Phase 6b) add it to `config/priority.yml`.

If the file has a mistake (duplicate id, factor outside 0–1, a form without a class, two forms in one class with different doses), loading fails with a message naming the compound.

## How to re-run a failed day

_To be written in Phase 5._

## The AI label-reader (`make normalise`, `make golden-live`)

- The model and effort levels are in `config/llm.yml`. Patrick chooses the model.
- The key lives in `.env` (`ANTHROPIC_API_KEY=...`), which is never committed.
- `make normalise` only sends listings it has not read before. Results are stored in the database keyed by the listing text and the `prompt_version`. `--force` re-reads everything; the run aborts before spending anything if more than `max_calls_per_run` listings are waiting.
- If the prompt in `pipeline/normalise/prompt.py` changes, bump `prompt_version` in `config/llm.yml`, then run `make golden-live` and commit the refreshed files in `tests/golden/cache/`.
- If the API is down, the run stops early with a warning and keeps what it has. A wrong key or no credit fails loudly.

## How to rotate a key

1. On https://platform.claude.com create a new API key, then delete the old one.
2. Replace the value in your local `.env`.
3. (From Phase 5) replace the `ANTHROPIC_API_KEY` secret in the GitHub repository settings.

## What to do when a feed column name changes

_To be written in Phase 6._

## Working down the unverified queue (`make review` / `make review-apply`)

_To be written in Phase 5._
