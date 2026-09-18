# Runbook — how to operate the pipeline and site

How to run and look after the pipeline and site, in plain steps (brief §14).

## First-time setup

1. Install `uv`, Node.js (LTS), `git` and GNU `make`.
2. `make setup` — installs Python and site dependencies.
3. Copy `.env.example` to `.env` and fill in keys (not needed until Phase 2).
4. `make check` — lint, tests, site type-check and build. Must be green before every commit.

Preview the site locally: `npm --prefix site run dev`.

## Daily commands

See the command list in `CLAUDE.md`. `make all` runs the whole chain; `make check` is the safety net before any commit. Only `make content` / `make content-check` (learn pages, Phase 9) are not built yet.

`make golden` prints a pass/fail line per golden label, twice: once for the rules and price maths against hand-written readings (must be 100 %), once replaying the saved AI readings (must be at least 90 %). It makes no API calls. `make golden-live` calls the real model.

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

On GitHub: **Actions → daily → Run workflow**. It is safe to run twice: ingest overwrites that day's raw file, listings the AI has already read are not re-sent, and nothing is committed if the data did not change.

On your PC: `make all`, then look at `/ops/` on the local site (`npm --prefix site run dev`, then http://localhost:4321/ops/).

If the run stopped at **"guard: BLOCKED"**, a comparison table that had products yesterday has none today. That usually means a feed broke or a column was renamed, not that every product vanished. Nothing was committed or deployed. Fix the cause and re-run. If the loss is real (a retailer genuinely dropped the range), commit `data/export` by hand to accept it.

The daily schedule itself is switched off until live feeds exist (seed CSVs do not change on their own). To switch it on, uncomment the two `schedule` lines in `.github/workflows/daily.yml`.

## The operator page (`/ops/`)

Not linked from anywhere and hidden from search engines. It shows when the pipeline last ran, how many listings each retailer has and how old their prices are, how many products are unverified and why, how often the AI needed a second attempt, and a "needs attention" list (a table that lost its products, a compound with none, prices more than 3 days old, second-attempt rate over 15 %, unverified over 20 %).

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

## Connecting a live affiliate feed (once a programme approves you)

**Awin — one shared feed for every retailer (preferred).** In Toolbox → Create-a-Feed, tick every advertiser you care about (approved or not — the download only ever contains the ones that have approved you, and fills up as approvals land), choose CSV + gzip + all columns, and copy the link **once** into `.env` as `AWIN_FEED_URL=<link>`. Then each Awin retailer in `config/retailers.yml` gets:

```yaml
feed: { type: awin_google_csv, url_env: AWIN_FEED_URL, gzip: true, advertiser_id: "19863" }
```

with its own Awin advertiser id (shown in the Create-a-Feed advertiser list and in the feed's `advertiser_id` column). The feed is downloaded once per run and split by that id. Prices in a currency other than GBP are dropped and counted as `not_gbp`.

**One link per retailer (older Awin feeds, Impact):**

1. In the network's dashboard (Awin: "Create-a-Feed"; Impact: the catalogue export) generate the product feed **download link** for that retailer. It contains your API key, so treat it like a password.
2. Put it in `.env` on a new line: `AWIN_FEED_URL_MYPROTEIN=<the link>` (and later as a GitHub secret with the same name). Never paste it into chat or any committed file.
3. In `config/retailers.yml` change that retailer's feed from `{ type: seed_csv }` to:

   ```yaml
   feed: { type: awin_csv, url_env: AWIN_FEED_URL_MYPROTEIN, gzip: true }
   ```

   (`impact_csv` for Impact.) Delete or rename its `data/seed/<id>.csv` so the two do not mix.
4. `make ingest`. You should see `ingest: myprotein: kept N, dropped M` - "dropped" are products that are not one of our supplements, which for a full catalogue is most of them. `not_gbp` and `invalid_row` counts are rows the feed itself got wrong.
5. `make all`, then check `/ops/`. New listings are read by the AI once (about 1p each); after that only new or changed listings cost anything. If a feed has more than 5,000 unread listings the run stops and asks you to raise `max_calls_per_run` in `config/llm.yml` - that is the spending guard, not a fault.

A feed listing that disappears for 14 days is hidden automatically.

## What to do when a feed column name changes

The symptom is `WARNING: <retailer>: required columns missing: price_gbp (their column 'search_price'); skipped` - that retailer keeps yesterday's data and everything else carries on.

Open the feed file, find what the column is called now, and override just that column in `config/retailers.yml`:

```yaml
feed:
  type: awin_csv
  url_env: AWIN_FEED_URL_MYPROTEIN
  column_map: { price_gbp: store_price }
```

Our field names are: `merchant_pid`, `ean`, `brand`, `title`, `description`, `url`, `image_url`, `price_gbp`, `in_stock`, `currency`. The defaults for each network are in `pipeline/ingest/feeds.py`.

## Working down the unverified queue (`make review` / `make review-apply`)

1. `make review` writes `data/review/<today>.csv`: one row per unverified listing, with what the AI read, the label quotes, and the reason it was not ranked. (If nothing is unverified it says so and writes nothing.)
2. Open the CSV in Excel. Open the product `url`, look at the real label, and fill in **decision**:
   - `approve-with-values` and put the facts you confirmed in **values**, e.g. `amount_refers_to=elemental` or `form_id=citrate; amount_per_serving=200; amount_unit=mg`. Allowed keys: `form_id`, `amount_per_serving`, `amount_unit`, `amount_refers_to`, `pack_units`, `pack_unit_type`, `units_per_serving`, `multipack_count`.
   - `reject` to hide the listing completely.
   - `merge-into:<product_id>` if it is the same product as another one.
   - leave blank to decide later.
3. Save as CSV, then `make review-apply`. It updates `config/product_overrides.yml` (commit that file) and tells you how many of each it applied. A typo in a decision is refused with a message naming the listing.
4. `make all`. Approved listings now rank; their "show the working" is based on your confirmed values.

## Approving a drafted batch of supplements

Claude drafts new supplements in `config/drafts/batch_NN.yml` (rules), `batch_NN_factor_sources.yml` (the chemistry behind each factor) and `tests/golden/drafts/batch_NN.yml` (three test labels each). Drafts are fully tested but **never reach the site** until you approve them.

To review a batch:

1. Open `config/drafts/batch_NN.yml`. For each supplement check the things only a person can judge: is the **standard dose** a sensible comparison unit, are the **forms grouped** the way a buyer would compare them, do the **labels and URL slugs** read well. Notes in the file explain anything unusual.
2. Spot-check about one in ten test labels in `tests/golden/drafts/batch_NN.yml` against a real product page: does a real label look like that?
3. `make golden DRAFT=batch_NN` shows the batch's results (rules must be 100 %, saved AI readings at least 90 %). It costs nothing. `make golden-live DRAFT=batch_NN` re-reads every label with the real AI (about 1p per label).

Batches 01–03 were approved and made live (2026-09-17/18), so `config/drafts/` is empty until the next batch is drafted.

To approve: tell Claude "approve batch NN" (or do it by hand: move the compounds into `config/compounds.yml`, the formulas into `config/factor_sources.yml`, the labels into `tests/golden/labels.yml` and the saved readings into `tests/golden/cache/`, then `make check`). New supplements only get pages once a retailer's data contains products for them.

## Refreshing the hand-collected prices (`make seed-refresh` / `make seed-refresh-apply`)

Until live feeds are connected, the prices on the site are the ones read by hand on the date shown beside each offer. They go stale. Aim to refresh every two weeks; `/ops/` shows how old each retailer's prices are, and `make seed-refresh` counts the rows older than 14 days.

1. `make seed-refresh` writes `data/review/seed_refresh_<date>.csv` — every seed listing, oldest first.
2. Open it in Excel or Google Sheets. For each row, open the `url` and type today's price into `new_price_gbp` (the normal one-off price — not a subscription price, not the crossed-out price). If it is out of stock, put `0` in `new_in_stock`. Leave rows you did not check blank.
3. `make seed-refresh-apply` writes those values into `data/seed/*.csv` and stamps the rows with the checklist's date. If anything looks like a typo (not a number, or more than 3× away from the old price) it stops and changes nothing.
4. `make all`, then `make check`, then commit. A refresh makes **no AI calls** — label text is untouched.

If a product's label has changed (new strength, new pack size), edit that row in the seed CSV by hand instead; that one listing will be re-read by the AI on the next run.
