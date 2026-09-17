# PerDose — Build Brief

Version 1.5 · 2026-09-17 · Owner: Patrick · Builder: Claude Code

**Changelog v1.1 (applied before any code exists):** amounts are stored in each compound's base unit (no `_mg` columns); a product carries a **list of actives** (many-to-many) so combination products index under every active from day one; **generic normalisation types** replace per-compound special cases; export is **one JSON file per compound**; new **§20 overview content layer** and **§21 scaling to hundreds of compounds**; phases 7–10 restructured; every new compound must ship with ≥ 3 golden labels.

**Changelog v1.2:** scope raised. The **prototype** stays at 10 compounds (it proves the normaliser). The **first public build ("Launch")** is the full registry in **Appendix F** — ~150 compounds across vitamins, minerals, amino acids, fatty acids, sports & performance, botanicals, nootropic and general-health ingredients — added in category batches once live feeds are in. New launch gate in §17, browse/A–Z routes in §12, retailer coverage targets in §7, synthetic golden labels allowed (§15), exclusion list (Appendix F.11).

**Changelog v1.3:** core/bolt-on boundary made explicit (§22): the core is a static site with **no accounts and no server-side code**; Learn (§20), Alerts, Stack Calculator and the N=1 experiment engine are separate bolt-ons. Core QoL additions in §12.2 ("your dose" recalculation, practical pick, per-pack sort, claimed dietary flags, share cards). Operator tooling (§12.3 `/ops/`, `make review`). LLM-assisted dedupe moved out of v1 (§11). Revenue options consolidated in §23 with what is deliberately excluded.

**Changelog v1.5 (2026-09-17):** user-facing design language adopted — "Capsule" (§12.4), chosen by Patrick from two rounds of mock-ups; flagged as needing a refinement pass before launch. Build-time decisions that changed earlier sections (Astro 7, Sonnet 5 as the model, 37-label golden set, seed data collected by Claude) are recorded in DECISIONS.md rather than rewritten here.

**Changelog v1.4:** competitive check recorded in §24 — the concept is not unique; the UK implementation is. Positioning rules added so the build defends the actual moat (automated per-dose normalisation across many retailers, updated daily) rather than the idea.

---

## 0. Summary and definition of done

**What it is.** A UK website where someone searches for a supplement (e.g. "magnesium"), picks a form (e.g. "bisglycinate"), and sees every product we know about ranked by **price per standard dose** — not price per tub, not price per "serving" as the brand defines it. Every row links out through an affiliate link. Prices refresh daily from affiliate product feeds.

**Why it can exist now.** Supplement labels are chaotic: compound mass vs elemental mass, "2 capsules provide", IU vs µg, fish-oil mass vs EPA+DHA, extract ratios, branded standardised extracts. Normalising that by hand across thousands of SKUs was never economic. An LLM extraction step plus a rules table makes it a pipeline.

**Prototype done means all of the following are true:**

1. `make all` runs end to end on the seed CSVs without manual steps.
2. The site has a compound page for all 10 launch compounds and a form page for every form that has ≥ 1 product.
3. On `/c/magnesium/bisglycinate/`, real products from ≥ 2 retailers appear, sorted ascending by price per 100 mg elemental magnesium, each with a working affiliate link, "last updated" date, and an unverified section beneath the ranked table.
4. The golden label set passes ≥ 27 / 30 (see Appendix B).
5. `make check` is green; GitHub Actions builds and deploys to Cloudflare Pages on push and on the daily cron.
6. Methodology, About and Affiliate Disclosure pages exist with the copy points in §16.

**Launch scope (first public build) is bigger than the prototype.** Scope is the product: someone searching for almost any single-ingredient supplement sold in the UK should find a page. Launch = the Appendix F registry live (target ≥ 100 compounds with ≥ 2 products each, ≥ 5 retailers), reached by adding compounds in category batches after the 10-compound prototype proves the pipeline. The prototype is a two-week gate, not the product.

**Prototype explicitly does not include:** price history, alerts/email capture, discount-code-adjusted "effective price", Amazon, combination products in the ranked tables (they are indexed in the data from day one; the UI toggle is Phase 8), the overview/learn content (§20, Phase 9), protein powders, a user account of any kind.

---

## 1. Goals, non-goals, principles

### Goals
- Be the most trustworthy UK answer to "what's the cheapest [compound] per dose, in the form I want?"
- Run in the background: daily automated refresh, near-zero hosting cost, minimal maintenance.
- Earn through affiliate links; be sellable as an asset (clean code, clean data, documented).

### Non-goals (v1)
- Recommending what to take. We compare prices of things people have already decided to buy.
- Ranking by "quality". We surface a testing flag; we do not score products.
- Covering everything. 10 compounds, single-ingredient products only.
- Any dynamic backend. The site is static files.

### Principles
- **Model extracts, code computes.** See CLAUDE.md rule 2.
- **Honest uncertainty.** Every derived number carries a confidence and a basis ("label-stated" vs "estimated from compound mass"). Ambiguous rows are never ranked.
- **Explainable rows.** A user can expand any row and see the exact arithmetic.
- **Boring technology.** Static site, SQLite, YAML config, cron. Nothing that needs babysitting.

---

## 2. Users and core flows

**Primary user:** someone in the UK who already takes (or has decided to take) a specific supplement and wants the cheapest sensible option. They arrive from Google with queries like "cheapest magnesium glycinate uk", "vitamin d3 4000iu best value", "creatine per gram price".

**Flow A — search → compound → form → buy**
1. Land on `/` or directly on `/c/magnesium/` from search.
2. Compound page shows: short explainer (what the forms are, what "standard dose" means here), form tabs, and the ranked table for the default form.
3. Click a form tab → `/c/magnesium/bisglycinate/`.
4. Table: product, retailer, pack (e.g. "180 caps · 90 servings"), elemental per serving, **price per 100 mg**, cost per month at standard dose, tested badge, link. Sort default = price per standard dose ascending. Filters: retailer, tested only, in stock only, min pack size.
5. Expand a row → shows the arithmetic and the label text it was derived from.
6. Click → affiliate deep link, new tab.

**Flow B — product page** (`/p/<slug>/`): one product, all retailers selling it, per-dose price at each. (v1 shows the table; price history is v1.1.)

**Flow C — methodology** (`/methodology/`): how we compute, elemental factors used, what "unverified" means, how often prices update.

---

## 3. Architecture

```
 affiliate feeds (Awin CSV, Impact catalogue)      seed CSVs (Patrick)
                 │                                        │
                 ▼                                        ▼
        pipeline/ingest  ──► data/raw/<retailer>/<date>.jsonl (gitignored)
                 │
                 ▼
        pipeline/normalise ──► LLM (Haiku; Sonnet on escalation), cached by content hash
                 │            ──► SQLite: products, extractions, offers
                 ▼
        pipeline/price ──► per-dose maths, dedupe, ranking flags
                 │
                 ▼
        pipeline/export ──► data/export/*.json (committed, small)
                 │
                 ▼
        site/ (Astro) reads data/export at build ──► site/dist ──► Cloudflare Pages
```

- **GitHub Actions** runs `make all` daily at 06:10 Europe/London, commits `data/export/*` if changed, and Cloudflare Pages auto-deploys from `main`.
- No runtime server. No database at runtime. Search is Pagefind (static index built at `astro build`).

---

## 4. Tech stack

| Layer | Choice | Version / notes | Why |
|---|---|---|---|
| Pipeline language | Python | 3.12 | Best LLM/data tooling; easy to read |
| Env & deps | `uv` | latest | Fast, lockfile, no venv fuss |
| Models/validation | `pydantic` | v2 | Strict schemas for LLM output |
| HTTP | `httpx` | latest | Feeds download |
| Config | `pyyaml` | latest | Human-editable rules |
| Storage | `sqlite3` (stdlib) | — | Single file, zero ops |
| LLM | `anthropic` SDK | latest | See §9 |
| Lint/format | `ruff` | latest | One tool |
| Tests | `pytest` | latest | Golden set + unit tests |
| Site | Astro | 5.x, `output: 'static'` | Fast static pages, content collections |
| Styling | Plain CSS + tokens | — | No framework to maintain |
| Search | Pagefind | latest | Static, zero backend |
| Hosting | Cloudflare Pages | free tier | Free, fast, Git-connected |
| CI | GitHub Actions | — | Cron + build |

**Do not add** a database service, an auth provider, Tailwind, React, or any paid SaaS in v1. If something seems to need one, write the case in DECISIONS.md and ask.

---

## 5. Data model

### 5.1 Config files

- `config/compounds.yml` — the rules table (Appendix A). One entry per compound; forms; elemental factors; standard dose; label conventions; aliases.
- `config/retailers.yml` — one entry per retailer: id, display name, feed type, feed URL env var, affiliate link template, commission note, shipping rule, enabled flag.
- `config/llm.yml` — model ids, temperature (0), max tokens, escalation threshold, cache dir.
- `config/site.yml` — site name, base URL, tagline, disclosure text, contact email.

### 5.2 SQLite schema (`data/perdose.sqlite`)

```sql
-- One row per retailer listing as received (a "listing" is retailer-specific).
CREATE TABLE listings (
  listing_id      TEXT PRIMARY KEY,   -- f"{retailer_id}:{merchant_product_id}"
  retailer_id     TEXT NOT NULL,
  merchant_pid    TEXT NOT NULL,
  ean             TEXT,               -- GTIN/EAN if provided, digits only
  brand           TEXT,
  title           TEXT NOT NULL,
  description     TEXT,
  url             TEXT NOT NULL,      -- affiliate deep link
  image_url       TEXT,
  price_gbp       REAL NOT NULL,
  in_stock        INTEGER NOT NULL,   -- 1/0
  first_seen      TEXT NOT NULL,      -- ISO date
  last_seen       TEXT NOT NULL,
  content_hash    TEXT NOT NULL       -- sha256(title + description) -> drives extraction cache
);

-- One row per (content_hash, prompt_version). The LLM's structured output, verbatim.
CREATE TABLE extractions (
  content_hash    TEXT NOT NULL,
  prompt_version  TEXT NOT NULL,
  model_id        TEXT NOT NULL,
  extracted_json  TEXT NOT NULL,      -- Extraction schema (§9.3) as JSON
  confidence      REAL NOT NULL,      -- 0..1 from the model
  escalated       INTEGER NOT NULL,   -- 1 if Sonnet was used
  created_at      TEXT NOT NULL,
  PRIMARY KEY (content_hash, prompt_version)
);

-- The canonical product (retailer-independent). Many listings -> one product.
CREATE TABLE products (
  product_id      TEXT PRIMARY KEY,   -- slug, stable once created
  ean             TEXT,
  brand           TEXT,
  name            TEXT NOT NULL,      -- cleaned display name
  pack_units      INTEGER,            -- capsules/tablets/grams/ml in ONE pack
  pack_unit_type  TEXT,               -- 'capsule'|'tablet'|'softgel'|'gummy'|'gram'|'ml'|'sachet'|'drop'
  units_per_serving REAL,
  multipack_count INTEGER NOT NULL DEFAULT 1,
  servings        REAL,               -- computed: pack_units * multipack_count / units_per_serving
  tested_flag     TEXT,               -- 'informed_sport'|'third_party'|null (label claim only in v1)
  multi_ingredient INTEGER NOT NULL,  -- 1 if it has any active beyond the primary's accepted cofactors
  needs_review    INTEGER NOT NULL,   -- 1 -> unverified only, never ranked
  review_reason   TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

-- One row per (product, compound). A "D3 + K2" product has two rows; a plain magnesium product has one.
CREATE TABLE product_actives (
  product_id      TEXT NOT NULL REFERENCES products(product_id),
  compound_id     TEXT NOT NULL,      -- from compounds.yml
  form_id         TEXT NOT NULL,
  form_class      TEXT NOT NULL,      -- comparability class (§6.3)
  amount_per_serving REAL,            -- in the compound's base unit (mg, mcg or IU) — see §10
  amount_unit     TEXT NOT NULL,      -- 'mg'|'mcg'|'IU', always equal to the compound's declared unit
  amount_basis    TEXT NOT NULL,      -- 'stated_elemental'|'estimated_from_compound'|'stated_total'|'stated_component_sum'|'stated_extract'|'stated_compound'
  is_primary      INTEGER NOT NULL,   -- 1 for the headline active (title order decides)
  rank_eligible   INTEGER NOT NULL,   -- 0 if needs_review, amount null, or class has no standard dose
  PRIMARY KEY (product_id, compound_id)
);

-- Links listings to products (built by dedupe, §11). Price fields are per pack.
CREATE TABLE offers (
  listing_id      TEXT PRIMARY KEY REFERENCES listings(listing_id),
  product_id      TEXT NOT NULL REFERENCES products(product_id),
  price_list_gbp  REAL NOT NULL,      -- as in the feed
  price_effective_gbp REAL,           -- after retailer sitewide code; NULL in v1 (v1.1 fills it)
  promo_id        TEXT,               -- config/promos.yml id; NULL in v1
  match_method    TEXT NOT NULL,      -- 'ean'|'key'|'llm'|'manual'
  match_confidence REAL NOT NULL,
  updated_at      TEXT NOT NULL
);

-- Per (offer, active) derived prices. Ranking reads this table.
CREATE TABLE offer_prices (
  listing_id      TEXT NOT NULL REFERENCES offers(listing_id),
  compound_id     TEXT NOT NULL,
  price_basis     TEXT NOT NULL,      -- 'list'|'effective'
  price_per_unit  REAL NOT NULL,      -- £ per 1 unit of the comparison quantity (per mg / per mcg / per IU)
  price_per_std_dose REAL NOT NULL,
  cost_per_month  REAL NOT NULL,
  days_supply     REAL NOT NULL,
  PRIMARY KEY (listing_id, compound_id, price_basis)
);

CREATE INDEX idx_offers_product ON offers(product_id);
CREATE INDEX idx_actives_compound_class ON product_actives(compound_id, form_class);
CREATE INDEX idx_offer_prices_compound ON offer_prices(compound_id, price_per_std_dose);
```

### 5.3 Site export (`data/export/`)

- `compounds.json` — the rules table minus internal notes, for rendering explainers and factors on the methodology page.
- `compounds/<compound_id>.json` — **one file per compound**: its classes, the products carrying that active (with per-active amounts), and their offers with `offer_prices` for that compound. A combination product therefore appears in two files. Size guard: < 2 MB per file (fail the build if exceeded; split by class if it ever happens).
- `index.json` — per-compound card data for the home page: product count, retailer count, "from £X per standard dose" per class.
- `meta.json` — `{ "generated_at": ISO, "retailers": [...], "counts": {...} }`. The regression guard in CI compares today's counts with yesterday's.

---

## 6. Compound rules — how comparison works

### 6.1 The comparison quantity
Each compound defines **what we count** (the "comparison quantity") and a **standard dose** to normalise price to:

| Compound | Comparison quantity | Standard dose | Display |
|---|---|---|---|
| Magnesium | elemental magnesium | 100 mg | "per 100 mg magnesium" |
| Zinc | elemental zinc | 15 mg | "per 15 mg zinc" |
| Vitamin D3 | cholecalciferol | 1,000 IU (25 µg) | "per 1,000 IU" |
| Vitamin K2 | menaquinone by class | MK-7: 100 µg | "per 100 µg MK-7" |
| Omega-3 | EPA + DHA combined | 1,000 mg | "per 1,000 mg EPA+DHA" |
| Creatine | creatine monohydrate mass | 5 g | "per 5 g" |
| Ashwagandha | root extract mass, by class | 600 mg | "per 600 mg extract" |
| Vitamin C | ascorbic acid equivalent | 1,000 mg | "per 1,000 mg" |
| Vitamin B12 | cobalamin by class | 1,000 µg | "per 1,000 µg" |
| L-theanine | L-theanine | 200 mg | "per 200 mg" |

The standard dose is a **comparison unit, not a recommendation**. Say so on every page.

### 6.2 Elemental factors
Where a label gives only the compound's mass (e.g. "magnesium bisglycinate 500 mg") we estimate the elemental amount as `mass × elemental_factor`, set `amount_basis = estimated_from_compound`, and show it as "≈ 70 mg (estimated)". Factors are in Appendix A and on the methodology page. If the label states elemental ("providing 100 mg magnesium", "elemental", "as magnesium", "NRV %"), the stated value wins and `amount_basis = stated_elemental`.

### 6.3 Form classes (comparability)
Products are only ranked **within a class**. A class is a set of forms that a reasonable buyer treats as interchangeable on price. Examples: `magnesium/bisglycinate` and `magnesium/glycinate` are the same class (`mg_glycinate`); `creatine/monohydrate` and `creatine/hcl` are different classes and never appear in the same table. The page structure follows classes, not raw form strings.

### 6.4 Label conventions
Per compound, `label_convention` tells the normaliser what an unqualified number most likely means:

- `elemental_default` — industry near-universally states elemental (zinc, vitamin D3, B12, K2, theanine, vitamin C). An unqualified number is elemental with `confidence ≥ 0.8`.
- `ambiguous` — both conventions common (magnesium). An unqualified number with no cue words → `needs_review = true`, reason `ambiguous_basis`, unless a heuristic in §9.5 resolves it.
- `compound_default` — the compound mass is the convention (creatine monohydrate, ashwagandha extract).

### 6.5 Normalisation types (the generic engine)
Every compound declares a `normalisation_type`. The rules engine (§9.5) dispatches on the type; compound entries only supply parameters. This is what makes adding compound #200 a YAML edit rather than new code.

| Type | Comparison quantity comes from | Parameters used | v1 compounds |
|---|---|---|---|
| `mineral_elemental` | stated elemental amount, else compound mass × `elemental_factor` (works for any active carried in a salt/chelate: choline, carnitine, HMB, citrulline malate too) | `elemental_factor` per form, `label_convention`, heuristics | magnesium, zinc |
| `vitamin_unit` | stated amount with unit conversion | `unit`, `unit_conversions`, class per form | vitamin_d3, vitamin_k2, vitamin_b12 |
| `oil_components` | sum of named components | `components_sum: [EPA, DHA]` | omega_3 |
| `extract_standardised` | extract mass; class by branded extract / stated standardisation | `branded_classes`, `standardisation_component` | ashwagandha |
| `simple_mass` | stated amount of the active | `unit` | creatine, vitamin_c, l_theanine |
| `per_serving` (later) | the serving itself (sachet/scoop) for multi-active-by-design products | `serving_label` | electrolytes, multivitamins, BCAA/EAA blends, greens (Phase 10) |
| `cfu_count` (later) | colony-forming units | — | probiotics (Phase 10) |
| `per_gram_macro` (later) | grams of protein/collagen | — | collagen, protein (not planned) |

A new type is only added when a compound cannot be expressed with the existing ones; log it in DECISIONS.md.

---

## 7. Retailers and feeds

### 7.1 Prototype: seed CSVs
Until feeds are approved, Patrick supplies `data/seed/<retailer_id>.csv` built by hand from real product pages. Template in Appendix D. The pipeline treats seed CSVs exactly like feeds (same `listings` rows), so nothing changes later except the ingest adapter.

### 7.2 Affiliate feeds (v1 launch)
Apply on day one. Typical approval times: Awin merchants days to two weeks; Impact similar; Amazon Product Advertising API only after the first qualifying sales through Amazon Associates.

- **Awin** (targets: Myprotein, Bulk, Holland & Barrett, Boots, Nutrition Geeks — confirm each merchant's network on signup). Use Awin's product feed download ("create-a-feed") URL stored in `AWIN_FEED_URL_<RETAILER>`. Feeds are CSV (often gzipped). Map columns by **name**, not position; expected names include product name, description, price, EAN, deep link, image URL, stock flag, merchant product id. Log any unmapped required column and stop for that retailer.
- **Impact** (targets: iHerb and others). Catalogue export; same mapping approach.
- **Amazon** — v1.1. Do not scrape Amazon.

### 7.3 `config/retailers.yml` entry shape

```yaml
- id: myprotein
  name: Myprotein
  enabled: true
  feed:
    type: awin_csv          # awin_csv | impact_csv | seed_csv
    url_env: AWIN_FEED_URL_MYPROTEIN
    gzip: true
    column_map:              # our field -> their column name
      merchant_pid: merchant_product_id
      ean: ean
      brand: brand_name
      title: product_name
      description: description
      url: aw_deep_link
      image_url: merchant_image_url
      price_gbp: search_price
      in_stock: in_stock
  link:
    template: "{url}"        # feeds usually already carry the affiliate deep link
  shipping:
    rule: free_over          # free_over | flat | unknown
    threshold_gbp: 45
    flat_gbp: 3.99
  notes: "Permanent discount codes; list prices inflated. Effective price is v1.1."
```

### 7.35 Retailer coverage targets (launch)
"Something for everybody" fails on thin retailer coverage before it fails on compound count. Launch needs **≥ 5 live feeds**; aim for 8. Candidate UK retailers to apply to (confirm each one's affiliate network and feed availability on signup — networks change): Myprotein, Bulk, Holland & Barrett, Boots, Nutrition Geeks, iHerb, Healthspan, Nature's Best, Simply Supplements, Vitabiotics, Nutravita, Lindens, Cytoplan, Viridian, Solgar (via stockists), The Protein Works, Applied Nutrition, Grenade, Naturelo/Sports Research (via Amazon later). Prioritise by catalogue breadth: a retailer with 2,000 SKUs is worth five with 50.

### 7.4 Ingest rules
- Idempotent: re-running on the same day overwrites that day's raw file; `listings.last_seen` updates; `first_seen` never changes.
- Currency: reject rows not in GBP. Prices as `REAL` with 2 dp.
- Only keep rows whose title or description matches at least one compound alias (Appendix A). Log kept/dropped counts per retailer.
- A listing not seen for 14 days is marked inactive (`in_stock = 0`) and hidden.

---

## 8. Pipeline — commands and behaviour

`pipeline/cli.py` exposes subcommands used by the Makefile:

- `ingest [--retailer id] [--date YYYY-MM-DD]` — pulls feeds or reads seed CSVs → `data/raw/…jsonl`, upserts `listings`.
- `normalise [--force] [--limit N]` — for each listing whose `(content_hash, prompt_version)` has no extraction, call the LLM (§9). Cached forever; `--force` re-extracts.
- `price` — builds/updates `products` (dedupe §11), computes `offers` (§10), applies ranking flags.
- `export` — writes `data/export/*.json`.
- `golden` — runs Appendix B through the normaliser + calculator and prints a pass/fail table (§15).

Every command logs to stdout with counts and to `logs/<date>.log`. Exit code non-zero on any hard failure (feed unreachable, schema invalid, golden < threshold in CI).

---

## 9. Normaliser (LLM extraction)

### 9.1 Contract
Input: retailer title + description (+ optional structured attributes from the feed). Output: one `Extraction` object (§9.3) validated by pydantic. The model **never** computes price per dose, never sees the price, and never invents fields: anything not present in the text is `null` with a reason in `review_reasons`.

### 9.2 Model policy (`config/llm.yml`)
- Default model: `claude-haiku-4-5-20251001`, temperature 0.
- Escalate to `claude-sonnet-5` when: pydantic validation fails after one retry, **or** `confidence < 0.7`, **or** `label_convention = ambiguous` and no cue words found.
- Use the SDK's structured/JSON output mode with the schema from §9.3. Check the current docs at https://docs.claude.com for the exact structured-output mechanism and the current model ids before writing the client; record what was used in DECISIONS.md.
- Cache key: `sha256(prompt_version + content_hash)`. Never re-call for an unchanged listing.
- Budget guard: abort the run if projected calls > `max_calls_per_run` (default 5,000).

### 9.3 `Extraction` schema (pydantic, strict)

```python
class ComponentAmount(BaseModel):
    name: str                      # e.g. "EPA", "DHA", "withanolides", "compound_mass"
    amount: float
    unit: Literal["mg", "mcg", "g", "IU", "percent"]

class ActiveExtraction(BaseModel):
    compound_id: str               # one of the candidate ids supplied in the user message
    form_raw: str | None           # form words exactly as on label
    form_id: str | None            # mapped id from compounds.yml, else null
    amount_per_serving: float | None
    amount_unit: Literal["mg","mcg","g","IU"] | None
    amount_refers_to: Literal["elemental","compound","total_oil","extract","unclear"] | None
    components: list[ComponentAmount]
    extract_ratio: str | None      # e.g. "10:1"
    branded_extract: str | None    # "KSM-66", "Creapure", "Magtein", "Quatrefolic"…
    evidence: dict[str, str]       # field -> exact label substring

class Extraction(BaseModel):
    actives: list[ActiveExtraction]        # every candidate compound present; [] if none
    is_single_ingredient: bool             # true only if exactly one active in total (candidates + other_actives); cofactor acceptance is decided in code (§9.5 step 9)
    other_actives: list[str]               # actives that are NOT candidates (B6, copper, piperine…)
    pack_units: int | None
    pack_unit_type: Literal["capsule","tablet","softgel","gummy","gram","ml","sachet","drop"] | None
    units_per_serving: float | None
    servings_stated: int | None
    multipack_count: int | None            # "3 x 90 tablets" -> 3
    tested_claims: list[str]
    confidence: float                      # 0..1, model's own
    review_reasons: list[str]
    evidence: dict[str, str]               # pack/serving fields -> exact label substring
```

Every populated numeric field **must** have an `evidence` entry quoting the label substring. Missing evidence → treat as null.

### 9.4 Prompt
System prompt in Appendix C. Prompt text is versioned by `prompt_version` (semver string in `config/llm.yml`); bump it on any change so the cache invalidates correctly.

### 9.5 Deterministic post-rules (code, after extraction)
Applied in `pipeline/normalise/rules.py`, **per active**, dispatching on the compound's `normalisation_type` (§6.5). The compound-specific bullets below are that type's parameters, not special-case code. Order:

1. **Unit normalisation:** mcg/µg/ug → mcg; g → mg ×1000; IU only valid for D3 (1 µg = 40 IU) and vitamin A/E (out of scope → review).
2. **Servings:** `servings = pack_units × multipack_count / units_per_serving`. If `servings_stated` exists and differs by > 5 % → `needs_review: servings_conflict`.
3. **Elemental resolution (magnesium, zinc):**
   - `amount_refers_to = elemental` → use as is, `basis = stated_elemental`.
   - `= compound` → multiply by form's `elemental_factor`, `basis = estimated_from_compound`.
   - `= unclear` and `label_convention = elemental_default` → treat as elemental, confidence capped at 0.8.
   - `= unclear` and `label_convention = ambiguous`: apply heuristics — for magnesium, if amount ≥ 400 mg and form is bisglycinate/glycinate/citrate/malate/taurate/threonate → compound (no single-serving product delivers ≥ 400 mg elemental in those forms); if amount ≤ 120 mg → elemental. Otherwise `needs_review: ambiguous_basis`.
4. **Omega-3:** comparison amount = EPA + DHA from `components`. If only "omega-3 total" stated → use it with `basis = stated_total`, confidence −0.2. If only oil mass → null, `needs_review: no_epa_dha`.
5. **Creatine:** monohydrate → use stated mass (`basis = stated_compound`; industry convention). HCl, buffered, blends → own classes. If a monohydrate label states "creatine 4.4 g (from 5 g monohydrate)" prefer the monohydrate mass.
6. **Ashwagandha:** class from `branded_extract` (ksm66 / sensoril / shoden / generic_extract / root_powder). Use extract mass; if `extract_ratio` present and the headline number is the "equivalent" (e.g. "5000 mg from 500 mg 10:1"), use the extract mass (500). Withanolide mg stored as a component for display only.
7. **Vitamin C:** ascorbic acid, sodium ascorbate, calcium ascorbate, Ester-C → class `standard` using the stated vitamin C amount (labels state ascorbate-equivalent). Liposomal → class `liposomal`.
8. **B12 / K2:** class by form (methyl / cyano / adenosyl / hydroxo; MK-7 / MK-4). Never cross-rank.
9. **Multiple actives:** every extracted active gets its own `product_actives` row and its own per-dose price. `multi_ingredient = 1` when the product contains any active (candidate or `other_actives`) that is not in the **primary** active's `accepted_cofactors` (e.g. B6 with magnesium is fine; zinc with magnesium is a combo; D3 and K2 accept each other both ways). Combo products are excluded from the **default** ranked tables and appear only when the "include combinations" toggle is on (Phase 8), with a badge listing the other actives. Their per-dose price counts only the compound being viewed — say so in the row.
10. **Gummies/liquids:** allowed; `pack_unit_type` drives the pack string.
11. **Confidence floor:** final `needs_review = 1` if confidence < 0.6 after adjustments.

### 9.6 Cost
Haiku at ~600 input / 300 output tokens per listing is a fraction of a penny; 5,000 listings ≈ a few pounds one-off, then only new/changed listings. Escalations should be < 10 % of calls; log the rate.

---

## 10. Price maths

All in `pipeline/price/calc.py`, pure functions, fully unit-tested.

```
servings                = pack_units × multipack_count ÷ units_per_serving
total_quantity          = servings × amount_per_serving          # comparison quantity in the pack, in the compound's base unit
price_per_unit          = price_gbp ÷ total_quantity             # £ per mg, per mcg or per IU
price_per_std_dose      = price_per_unit × standard_dose         # standard_dose in the same base unit
cost_per_month          = price_per_std_dose × 30
days_supply_at_std_dose = total_quantity ÷ standard_dose
```

- **Units are per compound, never mixed.** Each compound declares one base unit in `compounds.yml` (`mg`, `mcg` or `IU`); every stored amount for that compound is converted to it at rule time (§9.5 step 1) and `amount_unit` must equal the declared unit or the row fails validation. `standard_dose` (and any form-level `standard_dose_override`) is in the same unit. There are no `_mg` column names anywhere.
- Rounding: store full precision; display `£0.0X` per dose with 3 significant figures, cost per month to 2 dp.
- Shipping is **not** included in v1 ranking. Show the retailer's shipping rule as a tooltip. (Reason: including it depends on basket size; misleading either way.)
- Worked example (must be a unit test): Magnesium bisglycinate, £14.99, 180 capsules, 2 per serving, "providing 200 mg magnesium" per serving → servings 90 → total 18,000 mg → £0.000833/mg → **£0.0833 per 100 mg** → £2.50/month.

---

## 11. Dedupe and product identity

Goal: many retailer listings → one `product`.

1. **EAN match.** Same EAN (digits only, 8/12/13/14) → same product. Highest confidence.
2. **Key match.** `key = normalise(brand) + primary compound_id + form_id + pack_units + pack_unit_type + round(primary amount_per_serving)`. Same key → same product, confidence 0.85.
3. **(v1.1, not prototype)** LLM-assisted match when 1 and 2 fail and a candidate shares brand + compound: "same product? yes/no + reason" on both titles; accept only "yes" ≥ 0.8; log every match. In v1, unmatched listings simply become separate products — a duplicate row is a cosmetic problem, a false merge is a wrong price.
4. Otherwise create a new product. `product_id` = slug of `brand-name-form-pack` and never changes once created (append `-2` on collision).
5. Manual overrides file `config/product_overrides.yml` (merge/split by id) applied last.

---

## 12. Site (Astro)

### 12.1 Routes
- `/` — search box (Pagefind), the 10 compounds as cards with "from £X per dose" and product counts.
- `/c/[compound]/` — explainer (100–200 words: what the forms are, factors, what standard dose means), form-class tabs, table for the default class, FAQ block (3–5 factual Q&As).
- `/c/[compound]/[class]/` — the ranked table; canonical page for that class.
- `/browse/[class]/` — ingredient-class listing (vitamins, minerals, amino acids & derivatives, fatty acids, sports & performance, botanicals & extracts, other) with each compound's "from £X per dose". Class = the `category` field in Appendix F. **Browse is by ingredient class, not by health goal** ("sleep", "immune") — goal-based categories drift into claims; goal tags can live on learn pages later as "commonly studied for".
- `/a-z/` — every compound and every alias, one page, for search engines and humans.
- `/learn/[compound]/` — the overview page (§20). Built only when `content/<compound>/learn.md` has `review_status: approved`. The compound page shows a 100–120-word "at a glance" excerpt from it with a link; the learn page carries **no product tables**, only a "compare prices" link at the end.
- `/p/[product]/` — product detail: label facts, arithmetic, all offers, unverified/multi-ingredient notices where relevant.
- `/methodology/` — full method, factor table (rendered from `compounds.json`), what unverified means, update cadence, how to report an error.
- `/about/` and `/disclosure/` — §16.
- `/sitemap-index.xml`, `/robots.txt`.

### 12.2 Ranked table spec
Columns (desktop): Product (brand + name, tested badge) · Retailer · Pack (e.g. "180 caps · 90 servings") · Per serving (e.g. "200 mg") · **Per 100 mg** · Per month · Link.
Mobile: stack to card rows; **per standard dose** always visible.
- Default sort: price per standard dose ascending; then per month.
- Filters (client-side, no reload): retailer multi-select, tested only, in stock only.
- "Include combinations" toggle (Phase 8; hidden until then): off by default; when on, combo rows appear with a badge ("also contains zinc, B6") and the note "price counts the {compound} only".
- **"Your dose" box** (core, Phase 4): a single number input pre-filled with the comparison dose; changing it recalculates "per dose", "per month" and "days' supply" for every row client-side. State kept in the URL (`?dose=400`) so it's shareable. No storage.
- **Practical pick** (core, Phase 4): the cheapest row is often a 2-year tub. Show a second highlight — "best value under 6 months' supply" — computed from `days_supply`. One line of logic, big trust win.
- **Sort options** (core): per dose (default) · per month · per pack price · days' supply. Filters stay as above.
- **Claimed dietary flags** (core, cheap): vegan / vegetarian / gluten-free / sugar-free parsed from title and feed attributes, shown as "claimed" chips; never inferred, never a filter until the data is clean.
- **Share cards** (core): Open Graph image per class page generated at build ("Cheapest magnesium glycinate per 100 mg · updated {date} · from £X"). Static, SEO and social for free.
- **Quick "is this right?"** (core): every row's expand panel ends with a prefilled report link (product id, retailer, what you saw).
- Row expand: shows `evidence` quotes, basis, factor used, formula with numbers.
- Below the table: "Unverified (X)" section for `needs_review` rows, greyed, with the review reason in plain English, and a note that they are not ranked.
- "Prices last updated: <date>" and the disclosure line at the top of every table.

### 12.3 Operator page (for Patrick, not users)
- `/ops/` — `noindex`, unlinked, rendered from `meta.json` and a small `ops.json` export: last run time and status, counts per retailer, needs_review count by reason, escalation rate, classes that lost products since yesterday, zero-product compounds, feed staleness (days since a retailer's feed last changed).
- `make review` — writes `data/review/<date>.csv` of every needs_review product with its evidence quotes and a blank `decision` column; Patrick fills `decision` (approve-with-values / reject / merge-into:<id>) and `make review-apply` turns it into `config/product_overrides.yml` entries. This is how the unverified queue gets worked down without touching code.

### 12.4 Design language — "Capsule" (adopted 2026-09-17, v1.5)

**Status: this is the direction to aim for. It needs a refinement pass when we get to polish (before the launch gate) — treat what is built today as a faithful first application, not the finished design.** Refine *within* this language; do not change direction without Patrick's say-so.

**The idea.** Clean, calm and professional, with exactly one recurring motif taken from the subject: a **two-tone coral-and-teal capsule**. It appears in three places and nowhere else — the logo mark, the rank marker on each row (coloured for the cheapest, grey otherwise), and the buy button (price in the coral half, retailer in the teal half). Everything around it stays quiet. The promise a first-time visitor should feel: *"I can trust these numbers"* — friendly, not clinical.

**Tokens** live in `site/src/styles/tokens.css` (the single source; bolt-ons copy it, §22):
- Colour (light): ground `#f4f5f8`, surface `#ffffff`, sunken `#eceef3`, ink `#1c1b29`, muted `#5f5e70`, teal `#0e5e6f` (accent, links, the per-dose figure), teal tint `#e3f1f3`, coral `#ff5c4d`. A designed dark palette sits alongside via `prefers-color-scheme`.
- Type: the **Red Hat** family — Display (headings, the per-dose price; weights 700–900), Text (reading), Mono (every other figure, the working panel). **Self-hosted** (`@fontsource-variable/*`); the site makes no third-party requests (§16).
- Shape: cards radius 18px, controls 12px, pills/capsules fully round. Cards are borderless white on the grey ground.

**Rules.**
1. The capsule is the only decoration. No other gradients, illustrations, icons-as-ornament or hero imagery.
2. White text only on teal or ink. Coral carries dark text (white on coral fails contrast) or is purely decorative.
3. The per-dose price is always the largest figure in a row. On phones: a card per product with three figure tiles (per dose — tinted and biggest — per month, lasts) and a full-width buy capsule. On wide screens: a table for side-by-side scanning, same capsule buttons.
4. Status is said in words, quietly: "Cheapest per dose" (teal text), "Best value under 6 months' supply" (coral text), claimed dietary chips (grey). Semantic colour stays separate from the motif. Unverified sections use a quiet hatch, never an alarm colour.
5. Labels in sentence case; no tiny uppercase eyebrow labels; British English.
6. Both themes are designed, contrast AA or better, visible keyboard focus, reduced motion respected.

**Known refinement list (to do at the polish pass):** home page needs a proper opening (headline, search as the hero, "from £X" figures on the cards); product names should be split into name + pack size rather than shown as one feed title; decide whether claimed chips belong in the row or only in the expanded panel; best-row emphasis on phones; share-card typography (currently system fonts at build time); search results ranking and styling; an identity for the methodology/learn pages' long-form text.

Rejected directions, for the record: "Shelf Edge" (supermarket price ticket — too loud), "Receipt" (till-receipt working), "Graduated" (measuring-ruler rows), "Label" (printed dispensing label). Mock-ups are linked from DECISIONS.md.

### 12.5 SEO
- Titles: `Cheapest {Compound} {Class} in the UK — price per {standard dose} ({Month YYYY})`.
- Meta description templated from the live data ("From £0.05 per 100 mg across 6 retailers, 42 products. Updated daily.").
- `schema.org/ItemList` on class pages; `Product` + `Offer` on product pages only where data is complete. No `AggregateRating`.
- Internal links: every class page links to sibling classes and the methodology page.
- Do not generate pages with 0 products (build must skip them).

---

## 13. Search
Pagefind indexes compound, class and product pages. Aliases from Appendix A are injected as hidden indexable text on compound pages so "vit d", "d3", "fish oil" all resolve.

---

## 14. Scheduling and deployment

- **GitHub Actions**: `.github/workflows/daily.yml` — cron `10 5 * * *` UTC (06:10 BST / 05:10 GMT; adjust twice a year or use two schedules), runs `make all`, commits `data/export/*` with message `data: refresh YYYY-MM-DD` if changed. Secrets: `ANTHROPIC_API_KEY`, `AWIN_*`, `IMPACT_*`.
- `.github/workflows/check.yml` — on every push/PR: `make check` (ruff, pytest incl. golden, astro build). Fails the build if golden < 27/30 or any page would have 0 products where one existed yesterday (regression guard using `meta.json` counts).
- **Cloudflare Pages**: connected to the repo, build command `npm run build` in `site/`, output `site/dist`. Environment: none needed at build (data is committed JSON).
- `docs/RUNBOOK.md` must explain: how to add a retailer, how to add a compound, how to re-run a failed day, how to rotate a key, what to do when a feed column name changes.

---

## 15. Testing and quality gates

- `tests/test_calc.py` — every formula in §10 with hand-checked numbers (include the worked example).
- `tests/test_rules.py` — §9.5 rules, one test per rule, including unit conversions and the magnesium heuristics.
- `tests/test_dedupe.py` — EAN, key, and override paths.
- `tests/golden/labels.yml` + `tests/test_golden.py` — Appendix B. Runs the **real** normaliser (network) when `PERDOSE_LIVE_LLM=1`, otherwise replays cached extractions from `tests/golden/cache/`. CI runs live once a day in `daily.yml` and replay on every push.
- `tests/test_export.py` — export JSON validates against a JSON Schema in `pipeline/export/schema.json`; size guard < 5 MB.
- Astro: `astro check` + build must pass; a smoke test asserts the magnesium bisglycinate page contains ≥ 2 retailers in seed mode.

Thresholds: golden ≥ 90 % to merge (27/30 at launch; the denominator grows); escalation rate < 15 %; needs_review rate < 20 % of single-ingredient listings (log, warn above).

**Rule for growth:** every compound ships with ≥ 3 golden labels (one straightforward, one awkward, one combination) before its pages can build. The golden test fails if any compound in `compounds.yml` has fewer than 3.

Golden labels are **test inputs, not site data**, so Claude Code may write realistic *synthetic* label text for them (they live in `tests/golden/` and are never shown to users). Generate them per category batch alongside the YAML entries; Patrick spot-checks ~10 % against real product pages. Real awkward labels found in feeds get added to the golden set as they turn up.

---

## 16. Compliance and content rules

- **No health claims.** Allowed: what a form is, typical label doses, that forms differ in elemental content, that "standard dose" is our comparison unit. Not allowed: any statement that a product or dose treats, prevents, improves or supports anything. When in doubt, cut the sentence.
- **Evidence context**: at most two factual sentences per compound with a link to a reputable source (NHS, NIH ODS, Examine). No paraphrasing beyond 15 words of any source.
- **Affiliate disclosure**: a one-line disclosure at the top of every page with links and a full `/disclosure/` page: we earn commission on purchases through our links; it doesn't affect ranking (ranking is purely price per dose); retailers cannot pay for placement.
- **Accuracy**: "last updated" on every table; a "report an error" mailto on every product page.
- **Not medical advice** line in the footer. Under-18s, pregnancy, medication interactions → generic "speak to a pharmacist or GP" line, nothing more.
- **Privacy**: no cookies beyond Cloudflare's essentials; no analytics in v1 (add privacy-friendly analytics in v1.1 if wanted).
- **Data provenance**: retailer data is used under each affiliate programme's terms; no scraping of retailers in v1.

---

## 17. Phased plan with acceptance criteria

Work strictly in order. Finish each phase with a short written summary and a green `make check`.

**Phase 0 — Scaffold (½ day)**
- Repo layout per CLAUDE.md; `uv` project; Astro project; Makefile; `.env.example`; `DECISIONS.md`, `RUNBOOK.md` stubs; CI workflows.
- ✅ `make check` passes on an empty pipeline; site builds a placeholder home page.

**Phase 1 — Rules and calculator (1 day)**
- `config/compounds.yml` from Appendix A, loaded and validated by pydantic (unique ids, one base unit per compound, `normalisation_type` from §6.5, factors in 0–1, every form has a class, every compound ≥ 3 golden labels).
- Schema from §5.2 including `product_actives` and `offer_prices` — build it multi-active from the start even though the prototype UI shows single-ingredient tables.
- `calc.py` + tests incl. worked example.
- ✅ `pytest tests/test_calc.py tests/test_rules.py` green; `make golden` runs in "calc-only" mode against Appendix B expected fields.

**Phase 2 — Normaliser (2–3 days)**
- LLM client, cache, schema, prompt v1.0.0, post-rules, escalation.
- ✅ Golden ≥ 27/30 live. Escalation rate logged.

**Phase 3 — Seed data end to end (1 day)**
- Seed CSV adapter; Patrick provides ≥ 50 real SKUs across the 10 compounds from ≥ 2 retailers (template Appendix D).
- Dedupe, price, export.
- ✅ `make all` produces `data/export/compounds/*.json` covering ≥ 50 products across the 10 compounds; the magnesium bisglycinate class has ≥ 2 retailers.

**Phase 4 — Site (2–3 days)**
- All routes in §12; tokens; tables with sort options, "your dose" box and practical pick; expand rows with report link; claimed dietary chips; share cards; unverified section; methodology/about/disclosure copy; Pagefind.
- ✅ Prototype-done checklist (§0) items 2, 3, 6 met; Lighthouse performance ≥ 90 on a class page.

**Phase 5 — CI, cron, deploy (½ day)**
- Daily workflow, regression guard, Cloudflare Pages connected; `/ops/` page; `make review` / `make review-apply` round trip proven on at least five real needs_review rows.
- ✅ A scheduled run completes and deploys without human action. **Prototype done.**

**Phase 6 — Live feeds (as approvals arrive)**
- Awin/Impact adapters, column mapping, inactive-listing handling.
- ✅ Two live retailers replace their seed CSVs with no site regressions.

**Phase 7 — v1.1 items (§19 items 1–4), in priority order.**

**Phase 8 — Combination products in the UI (1–2 days)**
- "Include combinations" toggle, badges, per-compound price note; combos never in default view.
- ✅ A D3+K2 product appears in both the d3 and k2_mk7 tables with the badge; ZMA appears under magnesium and zinc only with the toggle on.

**Phase 9 — Overview content layer (§20)**
- Content pipeline (`make content COMPOUND=id`), review gate, learn pages, at-a-glance excerpts, claim linter.
- ✅ Ten approved learn pages live, each passing the review checklist; a legal read-through of one page before the rest publish.

**Phase 6b — Registry expansion to launch scope (runs as feeds arrive; 2–4 weeks of batches)**
Work category by category from Appendix F, Tier 1 first, then Tier 2: for each batch Claude Code drafts the `compounds.yml` entries (factors with sources in `factor_sources.yml`), drafts ≥ 3 golden labels per compound, runs `make golden` and `make all`, and reports: compounds added, products matched per compound, needs_review rate, escalation rate, classes with < 2 products. Patrick approves each batch. Batch order: vitamins → minerals → amino acids & derivatives → sports & performance → fatty acids → botanicals & extracts → other. Expect needs_review to spike on botanicals (standardisation chaos) — that is where the heuristics get tuned.

**Launch gate (public announcement, SEO push, alerts list opened):** all of the following true:
- ≥ 100 compounds with ≥ 2 rank-eligible products each; ≥ 5 live retailer feeds; every Tier 1 compound live.
- Golden ≥ 90 % across the whole registry; needs_review < 20 %; escalation < 15 %.
- Browse, A–Z, methodology, disclosure, about pages live; ≥ 10 approved learn pages (Phase 9 can run in parallel with 6b).
- One full day of the cron completing unattended.

**Phase 10 — Ongoing expansion (§21)**
- Tier 3 compounds, `per_serving` and `cfu_count` types (electrolytes, multivitamins, probiotics), new retailers, and anything the search logs show people looking for and not finding (log zero-result searches from day one).

---

## 18. Ops, secrets, cost

- `.env`: `ANTHROPIC_API_KEY`, `AWIN_API_KEY`, `AWIN_FEED_URL_*`, `IMPACT_ACCOUNT_SID`, `IMPACT_AUTH_TOKEN`. Never printed in logs.
- Expected running cost: hosting £0, CI £0 (public repo or within free minutes), LLM £1–10/month after the initial pass, domain ~£10/yr.
- Backups: `data/perdose.sqlite` uploaded as a CI artifact daily (30-day retention); export JSON is in git anyway.
- Failure modes and what happens: feed 404 → that retailer skipped, others proceed, warning in log; LLM outage → normalise skipped, yesterday's extractions reused, site still rebuilds; golden regression → CI fails, no deploy.

---

## 19. v1.1+ backlog (do not start before Phase 5 is done)

1. **Effective price** — track retailer sitewide codes in `config/promos.yml` (code, %, valid dates); show "with code X: £…" and rank on effective price with a toggle.
2. **Price history** — append daily `(product_id, retailer, price)` to `data/history.sqlite`; sparkline on product pages; "lowest in 90 days" badge.
3. **Alerts** — email capture via a Cloudflare Worker + KV, daily digest when a watched class drops below a threshold. This is the retention asset.
4. **Amazon** via Product Advertising API once Associates sales qualify.
5. **More compounds** — see §21 for the order and the checklist.
5a. **Verified testing flag** — cross-check label claims against the Informed Sport / Informed Choice product registers (manual export or lookup) so "tested" means verified, not claimed.
6. **Browser extension** — "cheapest per dose?" on retailer product pages.
7. **Privacy-friendly analytics** (Plausible/Fathom) once traffic justifies the cost.
8. **Stack calculator** (bolt-on A, client-side only): pick compounds + doses, see total monthly cost at the cheapest rank-eligible option per compound, shareable via URL state. No accounts. The natural on-ramp to alerts and, later, to N=1.
9. **Zero-result search logging** via the same Cloudflare Worker as alerts — the only ongoing source of "what people wanted and didn't find".

---

## 20. Overview content layer ("Learn" pages) — Phase 9

### 20.1 What it is and isn't
A plain-English overview per compound so a normal person understands what they're buying before they compare prices. It is **not** a research engine: no study browser, no live literature search on the page, no per-user answers. One templated page per compound, generated by a pipeline, reviewed by a human, refreshed on a schedule.

### 20.2 Page template (`/learn/<compound>/`, 600–900 words, fixed order)
1. **What it is** — 2–3 sentences. What the substance is, where it comes from, what it is sold as.
2. **Forms, explained** — table: form · what's different about it · elemental % (where relevant) · doses commonly seen on labels. Facts only.
3. **How it works** — "the short version" (3–4 sentences) and "a bit more" (100–150 words). Mechanism in everyday language; 2+ citations.
4. **What the research says** — 3–6 cards, one per commonly studied use. Each card: what kind of studies exist · what they measured · what they broadly found · how confident to be. A grade badge: **Strong / Moderate / Limited / Mixed / Insufficient**. 1–3 citations, meta-analyses and systematic reviews preferred.
5. **What people report** — aggregate patterns from community discussion: commonly reported positives, commonly reported downsides, dosing/timing patterns people mention. Header text on the section: "These are anecdotes people have shared, not evidence." Links to 3–5 discussion threads. **No quotes, no usernames, no product or brand names.**
6. **Things to know** — generic cautions (common interaction categories, timing, "take with food" type notes) ending with the fixed line: "If you take medication, are pregnant, or have a health condition, check with a pharmacist or GP first."
7. **Compare prices** — one link block to the compound's price tables. No product names above this point.

### 20.3 Sources and generation pipeline (`pipeline/content/`)
- **Literature:** OpenAlex, PubMed E-utilities and Semantic Scholar APIs (all free). For each compound and each candidate use: query, filter to systematic reviews / meta-analyses / RCTs, last 15 years, rank by citations and recency, pull abstracts (never full text), store `content/<compound>/evidence.json` (id, title, year, type, n, direction, abstract). The LLM (`claude-sonnet-5`) writes the cards from those abstracts with inline citations by PMID/DOI. **The grade is computed in code** from a rubric over what the LLM extracts per study (type, direction, sample size, consistency); the LLM proposes, the rubric decides. Rubric lives in `pipeline/content/grade.py` and is shown on the methodology page.
- **Mechanism:** drafted by the LLM from the cited reviews; at least two citations; reviewed like everything else.
- **Community anecdotes:** Reddit's Data API terms restrict commercial use and prohibit scraping, so do **not** build an automated Reddit crawler. Launch approach: for each compound, Patrick curates 3–5 threads into `content/<compound>/threads.yml` (URL, title, date); the pipeline fetches nothing automatically — Patrick pastes the thread text into a local, git-ignored file, the LLM synthesises **aggregate patterns only**, and the output stores patterns + thread links, never text from the threads. Refresh quarterly. Check Reddit's current API and content-use terms before any automation and record the check in DECISIONS.md. Other communities can be added the same way where their terms allow.
- **Claim linter:** `make content-check` fails a page if it contains banned phrasing (treats, cures, prevents, boosts immunity, detox, "clinically proven", etc. — list in `config/claims_banned.yml`), any card without citations, any anecdote section with a brand name, or missing frontmatter.

### 20.4 Review gate and cadence
- Frontmatter on `learn.md`: `compound_id`, `content_version`, `generated_at`, `model_id`, `sources[]`, `review_status: draft|approved`, `reviewed_by`, `reviewed_on`. **Only `approved` pages build.**
- `content/REVIEW.md` checklist: no treat/cure/prevent language; every grade has citations and matches the rubric output; anecdotes labelled and product-free; forms table matches `compounds.yml`; UK spelling; the fixed "check with a pharmacist or GP" line present.
- Cadence: literature refresh every 6 months; a monthly OpenAlex query for new meta-analyses flags a page for re-review; anecdotes quarterly.

### 20.5 Compliance
Keep learn pages editorial: no product links or tables above the final "compare prices" block; no retailer names; sources visible. Price pages keep their two-sentence factual explainer only. Get one page read by a solicitor familiar with ASA/CAP and the Nutrition and Health Claims rules before publishing the rest. Phrase findings as what studies measured and found ("trials measured sleep-onset time and found…"), never as what the compound does for the reader.

### 20.6 Cost and the real bottleneck
LLM cost is small (≈ £1–3 per compound to generate, less to refresh). The bottleneck is review: 30–45 minutes per page. So tier it — full learn pages for the top ~50 compounds by search demand, a short "at a glance" block (steps 1, 2 and 6 only) for the rest until they earn a full page.

---

## 21. Scaling to hundreds of compounds — Phase 10

### 21.1 Adding a compound is a checklist, not a project
1. Draft the `compounds.yml` entry from the template (Claude Code can draft it; Patrick approves): id, name, base unit, `normalisation_type`, standard dose, label convention, aliases, accepted cofactors, forms with classes and factors.
2. Cite every elemental factor in `config/factor_sources.yml` (source URL, date checked).
3. Add ≥ 3 golden labels (§15).
4. Run `make golden` for that compound; run `make all`; confirm pages only build for classes with ≥ 2 products.
5. Add the compound to `config/priority.yml` with its search-demand estimate (free keyword tools at first, Search Console once live) so expansion order is data-driven.

### 21.2 Engine changes that make this cheap
- **Candidate selection before extraction:** the ingest alias pass tags each listing with up to 8 candidate compounds; the extraction prompt receives only those candidates (ids, names, forms). The prompt never lists the whole registry.
- **Types, not special cases:** §6.5. Adding a type is a DECISIONS.md event; adding a compound is not.
- **Per-compound export** (§5.3) keeps build memory flat as the catalogue grows.
- **Thin-page rule:** class pages need ≥ 2 products; learn pages need `approved`; everything else is `noindex` or unbuilt.
- **Costs at scale:** ~300 compounds × ~100 listings = 30k listings → one-off extraction in the tens of pounds, daily deltas in pennies; SQLite and Astro are fine at this size; CI time is the thing to watch (target < 15 min).

### 21.3 Expansion order
The full launch registry, with tiers, types, units and comparison doses, is **Appendix F**. Tier 1 = must be live at launch; Tier 2 = launch if feeds have ≥ 2 products; Tier 3 = post-launch. Excluded items are listed in F.11 and must not be added without a DECISIONS.md entry.



---

## 22. Module map — the core stays small

The core is a **static site plus a batch pipeline**. It has no accounts, no sessions, no server-side code, no database at runtime. Anything that needs any of those is a bolt-on with its own deployable and its own repo folder, and the core knows about it only through links and shared design tokens.

| Module | What it is | Needs a backend? | Where it lives | When |
|---|---|---|---|---|
| **Core** | pipeline, class/product/browse/A–Z pages, methodology, ops page, share cards, "your dose", practical pick | No | this repo (`pipeline/`, `site/`) | Prototype → Launch |
| **Learn** | overview pages per compound (§20) | No (static content + review gate) | this repo (`content/`, `pipeline/content/`) | Phase 9 |
| **Alerts** | email capture + price-drop digests; zero-result search log | Yes — one Cloudflare Worker + KV/D1 | `apps/alerts/` | v1.1 |
| **Stack calculator** | multi-compound monthly cost, URL-state | No | `site/` (one page) | v1.1 |
| **N=1** | personal experiment engine: define a trial (compound, dose, weeks, washout), log daily, get a plain-English read-out of whether anything changed | Yes — accounts, storage, mobile-friendly app | separate repo `perdose-n1` (or `apps/n1/`), separate deploy | Later product |

Rules for bolt-ons:
- A bolt-on may **read** core exports (`data/export/*`) and link to core pages; the core never imports from a bolt-on.
- A bolt-on that fails must not break a core build or page. The core build has no step that depends on Alerts or N=1 being up.
- Shared look: bolt-ons copy `site/src/styles/tokens.css`; nothing else is shared.
- N=1 positioning when it comes: self-tracking, not diagnosis or advice. It never recommends a compound; it measures what the user chose to try. Its paid tier is the first non-affiliate revenue line (§23). Keep it out of scope for every phase before Launch.

---

## 23. Revenue model and options

### 23.1 In from launch
1. **Affiliate commission** on every outbound click (Awin/Impact deep links; Amazon later). The ranking is never affected — state this on the disclosure page and mean it.

### 23.2 Add after launch (in this order)
2. **"Best value per dose" badge licensing** — a brand or retailer whose product tops a class can license a dated badge ("PerDose best value · magnesium glycinate · Sept 2026") for their own site. Data-driven, doesn't touch the ranking, and the same mechanism consumer-testing publications use. Needs a short licence template and a monthly re-check that the claim is still true.
3. **Alerts list → digest sponsorship** — once the alerts list exists, one clearly labelled sponsor slot per digest, outside the price content. Only sponsors whose products are in the index; no health-claim copy.
4. **Data licensing / API** — the normalised per-dose dataset (compound, class, per-dose price by retailer, history) to apps, brands doing price monitoring, and journalists. Low volume, high margin, and it is the asset a buyer would value.
5. **Brand price-position reports** — monthly "where you sit per dose vs the category" for brands; small B2B subscription built from the same data.
6. **N=1 premium tier** — the bolt-on's subscription; the first revenue that isn't tied to other people's checkouts.

### 23.3 Deliberately excluded
- **Sponsored rows or "featured" placement inside ranked tables** — the moment a paid product can sit above a cheaper one, the site is worthless.
- **Display ads** — slow, ugly, and they'd show supplement ads next to price data (the exact conflict Examine built its brand on avoiding). Revisit only for Learn pages, only if the numbers make it undeniable.
- **Selling products directly / white-label shop** — different business, different liabilities.
- **Goal-based browse ("sleep", "immune") as a revenue surface** — claims exposure, no.

### 23.4 What actually moves revenue
Traffic × click-through × retailer conversion × commission. The pipeline only affects the first two: coverage (Appendix F, retailer count) and trust (correct numbers, practical pick, "your dose"). Everything in §23.2 is a multiplier on an audience that already exists; none of it substitutes for one.


---

## 24. Competitive landscape and positioning (checked 2026-09-17)

**Verdict:** "price per dose across forms and retailers" is not a new idea. Nobody does it in the UK, at catalogue scale, automated, across ingredient categories. That combination is the product; the idea alone is not a moat.

| Who | What they do | What they don't | Threat |
|---|---|---|---|
| **Verified Supplement Data** (US, launched Mar 2026) | Cost per *clinical* dose, forms compared, evidence grades, A–Z, plus symptom/condition/DNA/labs tools | US only; Amazon-only pricing; prices "reviewed periodically" by hand (dated snapshots); mixes health advice with commerce | Concept twin. Could add UK. Its symptom/DNA/labs features are exactly what §16/§20 keep PerDose away from. |
| **ProteinDeals UK** | Daily-updated prices across UK retailers incl. Bulk, Myprotein, H&B, Amazon; ~650 SKUs per retailer incl. vitamins, minerals, amino acids; "per serving" and per-100g normalisation; subscription vs one-off prices | Per *serving as labelled*, no elemental/IU/EPA+DHA normalisation, no form classes; categories are noisy (B12 filed under pre-workout) | **Most likely fast follower** — they have the price plumbing and only lack the normaliser. Speed matters. |
| **WheyWise** (UK) | Protein price comparison across 90+ retailers, dated prices, cost per 25 g protein | Protein only | Proves the UK model works and gets traffic; also why protein is excluded from PerDose scope. |
| **Creatine Corner, SuppPick, Body Science Review, PricePlow** (US) | Single-category per-gram tools, side-by-side comparators, Amazon cost-per-serving listicles, deal feeds | Single category / US / manual / per serving | Low. |
| **Dose Cost app, ExRx calculator** | Manual per-dose calculators — you type the label in | No catalogue, no prices | None; they validate the user need. |
| **Google Shopping, PriceSpy, idealo** | SKU-level price comparison | No dose normalisation at all | Low, but they own generic "price" queries. |
| **Examine, Labdoor, ConsumerLab** | Evidence and testing | No prices | Adjacent; Examine's "no industry money" stance is the trust bar to match. |

Search check: "cheapest magnesium glycinate UK per 100 mg" currently returns retailer pages, deal aggregators and forum threads doing the maths by hand — no comparator ranks. That is the opening.

**Positioning rules that follow (binding on the build):**
1. **Win on normalisation quality, not on having the idea.** The golden set, the form classes, the elemental/IU/EPA+DHA handling and the "estimated vs stated" honesty are the product. Any shortcut here hands the category to ProteinDeals.
2. **Win on freshness.** Daily feed-driven prices with a visible "updated" date, against hand-reviewed snapshots.
3. **Win on breadth of retailers, then breadth of compounds** (§7.35, Appendix F). Two retailers per compound is a listicle; six is a comparison.
4. **Do not copy the US site's health-advice layer.** No symptoms, no conditions, no DNA, no labs. Learn pages stay editorial and separate (§20). That is both the legal position in the UK and the trust position.
5. **Ship before the follower does.** Launch gate (§17) exists so scope doesn't delay the first public version indefinitely; Tier 1 live beats Tier 3 perfect.
6. **Say it plainly on the methodology page:** what we normalise, what we estimate, what we don't compare (forms in different classes), and that no retailer or brand can pay for position.

---

## Appendix F — Launch registry (~150 compounds)

How to read: **unit** is the compound's base unit; **type** is the normalisation type (§6.5); **comparison dose** is the standard dose used only to normalise price (never a recommendation — say so on every page); **classes** lists forms that are ranked separately; **tier** 1 = must be live at launch, 2 = launch if ≥ 2 products in feeds, 3 = post-launch. Factors given as "~%" are elemental mass fractions to verify and cite in `factor_sources.yml` before use; labels stating elemental content always win. Label convention (`label_convention`) is noted where it is not `elemental_default`.

Every entry becomes one `compounds.yml` record with `category` set to the section name. Claude Code drafts entries from this table; Patrick approves per batch (§17 Phase 6b).

### F.1 Vitamins (`category: vitamins`)

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| vitamin_a | Vitamin A | mcg | vitamin_unit | 800 | retinol (palmitate/acetate; 1 IU = 0.3 mcg) vs beta_carotene (separate class, mg) | 2 |
| vitamin_b1 | Thiamine (B1) | mg | simple_mass | 100 | thiamine hcl/mononitrate one class; benfotiamine separate class | 2 |
| vitamin_b2 | Riboflavin (B2) | mg | simple_mass | 100 | riboflavin vs r5p | 2 |
| vitamin_b3 | Niacin (B3) | mg | simple_mass | 500 | niacin (nicotinic acid) vs niacinamide vs inositol_hexanicotinate — three classes | 2 |
| vitamin_b5 | Pantothenic acid (B5) | mg | simple_mass | 500 | calcium pantothenate: labels state B5 | 3 |
| vitamin_b6 | Vitamin B6 | mg | simple_mass | 50 | pyridoxine_hcl vs p5p — two classes | 1 |
| vitamin_b7 | Biotin | mcg | vitamin_unit | 5000 | one class; mg→mcg conversion common ("10mg") | 1 |
| vitamin_b9 | Folate | mcg | vitamin_unit | 400 | folic_acid vs methylfolate (5-MTHF, Quatrefolic/Metafolin) — two classes; "mcg DFE" → treat as mcg with review flag | 1 |
| vitamin_b12 | Vitamin B12 | mcg | vitamin_unit | 1000 | (v1) methyl / cyano / adenosyl / hydroxo / unspecified | 1 |
| vitamin_c | Vitamin C | mg | simple_mass | 1000 | (v1) standard / liposomal | 1 |
| vitamin_d3 | Vitamin D3 | IU | vitamin_unit | 1000 | (v1) d3 (incl. vegan) / d2 | 1 |
| vitamin_e | Vitamin E | mg | vitamin_unit | 268 | d_alpha (natural) vs dl_alpha (synthetic) vs mixed_tocopherols; IU→mg: natural 1 IU = 0.67 mg, synthetic 1 IU = 0.9 mg (verify) | 2 |
| vitamin_k1 | Vitamin K1 | mcg | vitamin_unit | 100 | phylloquinone | 3 |
| vitamin_k2 | Vitamin K2 | mcg | vitamin_unit | 100 | (v1) mk7 / mk4 (override 5000) | 1 |
| choline | Choline | mg | mineral_elemental | 250 | bitartrate (~41% choline) vs alpha_gpc (~40%) vs citicoline (~18%) — three classes, each with own factor; `label_convention: ambiguous` | 1 |
| inositol | Inositol | mg | simple_mass | 2000 | myo_inositol vs d_chiro (override 600) | 2 |

### F.2 Minerals (`category: minerals`)

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| magnesium | Magnesium | mg | mineral_elemental | 100 | (v1) | 1 |
| zinc | Zinc | mg | mineral_elemental | 15 | (v1) | 1 |
| calcium | Calcium | mg | mineral_elemental | 500 | carbonate (~40%) / citrate (~21%) / citrate_malate (~21–26%) / lactate (~13%) / gluconate (~9%) / marine_algae (state elemental); `label_convention: ambiguous` | 1 |
| iron | Iron | mg | mineral_elemental | 14 | bisglycinate (~20% as Ferrochel; pure ~27%) / fumarate (~33%) / sulfate (heptahydrate ~20%, dried ~32.5%) / gluconate (~12%) / liquid & spatone (state elemental); UK labels almost always state elemental | 1 |
| potassium | Potassium | mg | mineral_elemental | 200 | chloride (~52%) / citrate (~38%) / gluconate (~17%) / bicarbonate (~39%) | 2 |
| selenium | Selenium | mcg | mineral_elemental | 100 | selenomethionine vs selenite/selenate vs yeast — labels state elemental | 1 |
| iodine | Iodine | mcg | mineral_elemental | 150 | potassium_iodide (~76%) / kelp (state elemental) / lugols (liquid, review) | 2 |
| chromium | Chromium | mcg | mineral_elemental | 200 | picolinate (~12.4%) / polynicotinate / chloride — labels state elemental | 2 |
| copper | Copper | mg | mineral_elemental | 1 | gluconate / bisglycinate / citrate — labels state elemental | 3 |
| manganese | Manganese | mg | mineral_elemental | 2 | one class | 3 |
| boron | Boron | mg | mineral_elemental | 3 | citrate / glycinate / calcium fructoborate (separate class) | 2 |
| molybdenum | Molybdenum | mcg | mineral_elemental | 100 | one class | 3 |
| silica | Silica | mg | mineral_elemental | 50 | bamboo_extract / horsetail / orthosilicic_acid (separate) — often unclear; expect review | 3 |
| lithium_orotate | Lithium (orotate) | mcg | mineral_elemental | 1000 | orotate (~3.8% Li); labels usually state elemental Li; `label_convention: ambiguous` | 3 |
| sodium_bicarbonate | Sodium bicarbonate | mg | simple_mass | 5000 | powder/capsules (sport use) | 3 |

### F.3 Amino acids & derivatives (`category: amino-acids`)

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| creatine | Creatine | mg | simple_mass | 5000 | (v1) monohydrate / hcl (1500) / other | 1 |
| beta_alanine | Beta-alanine | mg | simple_mass | 3200 | one class (CarnoSyn badge) | 1 |
| citrulline | L-Citrulline | mg | mineral_elemental | 3000 | base vs malate_2_1 (~66% citrulline by weight when "2:1" stated; else review); `label_convention: ambiguous` | 1 |
| arginine | L-Arginine | mg | simple_mass | 3000 | base vs akg (separate) | 2 |
| glutamine | L-Glutamine | mg | simple_mass | 5000 | one class | 1 |
| leucine | L-Leucine | mg | simple_mass | 3000 | one class | 3 |
| bcaa | BCAA | mg | simple_mass | 5000 | total BCAA per serving; ratio shown as badge (2:1:1, 4:1:1) — "total BCAA" must be stated or review | 2 |
| eaa | EAA | mg | simple_mass | 10000 | total EAA per serving stated or review | 2 |
| taurine | Taurine | mg | simple_mass | 1000 | one class | 1 |
| glycine | Glycine | mg | simple_mass | 3000 | one class | 1 |
| l_theanine | L-Theanine | mg | simple_mass | 200 | (v1) | 1 |
| tyrosine | L-Tyrosine | mg | simple_mass | 500 | tyrosine vs nalt (separate) | 2 |
| carnitine | L-Carnitine | mg | mineral_elemental | 1000 | l_carnitine_tartrate (~68% carnitine) / alcar (acetyl, own class, stated mass) / lclt / liquid — `label_convention: ambiguous` | 1 |
| nac | N-Acetyl Cysteine | mg | simple_mass | 600 | one class | 1 |
| lysine | L-Lysine | mg | simple_mass | 1000 | hcl: labels state lysine or lysine hcl — review if unclear | 2 |
| tryptophan | L-Tryptophan | mg | simple_mass | 500 | one class | 2 |
| five_htp | 5-HTP | mg | simple_mass | 100 | griffonia extract: use 5-HTP content | 1 |
| gaba | GABA | mg | simple_mass | 500 | one class (PharmaGABA badge) | 2 |
| ornithine | L-Ornithine | mg | simple_mass | 1000 | one class | 3 |
| hmb | HMB | mg | mineral_elemental | 3000 | calcium_hmb (~80% HMB) vs free_acid; `label_convention: compound_default` | 2 |
| betaine | Betaine (TMG) | mg | simple_mass | 2500 | anhydrous; betaine HCl is a **different product** (digestive) → own id `betaine_hcl` (650) | 2 |
| betaine_hcl | Betaine HCl | mg | simple_mass | 650 | one class | 3 |
| collagen | Collagen | mg | per_gram_macro | 10000 | bovine / marine / chicken type II (own class, 40) / vegan "builder" (exclude) — hydrolysed peptides; grams per serving | 1 |
| agmatine | Agmatine | mg | simple_mass | 500 | one class | 3 |

### F.4 Sports & performance (`category: sports`) — ingredients not already above

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| caffeine | Caffeine | mg | simple_mass | 200 | tablets/capsules only; anhydrous vs "natural" same class; pre-workout blends are combos | 1 |
| beetroot_nitrate | Beetroot / nitrate | mg | extract_standardised | 400 | nitrate mg per serving when stated; else review; juice shots by ml (unit note) | 2 |
| electrolytes | Electrolytes | — | per_serving | 1 sachet | Phase 10 (`per_serving`): show sodium/potassium/magnesium per serving side by side | 3 |
| cla | CLA | mg | simple_mass | 3000 | one class | 3 |
| dextrose_carbs | Carbohydrate powders | g | per_gram_macro | 50 | dextrose / maltodextrin / cyclic dextrin — Phase 10 | 3 |
| glycerol | Glycerol | mg | simple_mass | 2000 | one class | 3 |
| sodium_bicarbonate | (see F.2) | | | | | |

### F.5 Fatty acids & lipids (`category: fatty-acids`)

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| omega_3 | Omega-3 | mg | oil_components | 1000 | (v1) fish / krill / algae / cod_liver | 1 |
| flaxseed_oil | Flaxseed oil (ALA) | mg | oil_components | 1000 | components_sum [ALA]; review if ALA not stated | 3 |
| evening_primrose | Evening primrose (GLA) | mg | oil_components | 100 | components_sum [GLA] | 3 |
| mct_oil | MCT oil | mg | oil_components | 10000 | components_sum [C8, C10]; else total oil with review; pure C8 own class | 2 |
| phosphatidylserine | Phosphatidylserine | mg | simple_mass | 100 | one class (sunflower vs soy badge) | 2 |
| astaxanthin | Astaxanthin | mg | simple_mass | 4 | one class | 2 |
| black_seed_oil | Black seed oil | mg | simple_mass | 1000 | oil mass; thymoquinone % as component | 3 |

### F.6 Botanicals & extracts (`category: botanicals`) — all `extract_standardised` unless noted; comparison dose is extract mass; standardisation stored as a component and shown; branded extracts get their own class where the standardisation differs

| id | name | comp. dose (mg) | classes / standardisation notes | tier |
|---|---|---|---|---|
| ashwagandha | Ashwagandha | 600 | (v1) ksm66 / sensoril / shoden (120) / generic_extract / root_powder | 1 |
| rhodiola | Rhodiola rosea | 400 | 3% rosavins / 1% salidroside standard; unstandardised own class | 1 |
| curcumin | Turmeric / curcumin | 500 | curcumin_95 (dose = curcuminoids mg) / turmeric_root_powder (own class, 1500) / branded bioavailable (Meriva, Longvida, Theracurmin — own classes) | 1 |
| berberine | Berberine | 500 | `simple_mass`; berberine HCl one class; dihydroberberine own class | 1 |
| lions_mane | Lion's mane | 1000 | fruiting_body_extract / mycelium / powder — three classes (state which; else review) | 1 |
| reishi | Reishi | 1000 | as lion's mane | 2 |
| cordyceps | Cordyceps | 1000 | as lion's mane; CS-4 mycelium own class | 2 |
| chaga | Chaga | 1000 | as lion's mane | 3 |
| bacopa | Bacopa monnieri | 300 | bacosides % stated; Bacognize / Synapsa own classes | 1 |
| ginkgo | Ginkgo biloba | 120 | 24/6 standardised; unstandardised own class | 2 |
| panax_ginseng | Panax ginseng | 200 | ginsenosides % stated; Korean red vs white same class | 2 |
| american_ginseng | American ginseng | 200 | one class | 3 |
| maca | Maca | 1500 | raw_powder / gelatinised / extract (own classes) | 1 |
| tongkat_ali | Tongkat ali | 200 | standardised (eurycomanone %) vs unstandardised | 2 |
| fenugreek | Fenugreek | 500 | seed extract; Testofen own class | 3 |
| tribulus | Tribulus | 500 | saponins % stated | 3 |
| saw_palmetto | Saw palmetto | 320 | 85–95% fatty acids extract vs berry powder | 2 |
| milk_thistle | Milk thistle | 150 | dose = silymarin mg when stated; else extract mass with review | 2 |
| green_tea_extract | Green tea extract | 400 | dose = EGCG mg when stated; else review | 1 |
| quercetin | Quercetin | 500 | `simple_mass`; phytosome own class | 2 |
| resveratrol | Resveratrol | 250 | dose = trans-resveratrol mg | 2 |
| boswellia | Boswellia | 300 | boswellic acids % stated | 3 |
| ginger | Ginger | 500 | extract vs root powder | 3 |
| garlic | Garlic | 600 | aged_garlic (Kyolic) / allicin-standardised / powder | 3 |
| elderberry | Elderberry | 500 | extract mass; gummies common | 2 |
| echinacea | Echinacea | 400 | purpurea vs angustifolia same class; THR products flag | 3 |
| valerian | Valerian | 500 | 0.8% valerenic acid standard | 2 |
| lemon_balm | Lemon balm | 500 | one class | 3 |
| chamomile | Chamomile | 500 | one class | 3 |
| passionflower | Passionflower | 500 | one class | 3 |
| st_johns_wort | St John's wort | 300 | 0.3% hypericin; THR-registered products only (label flag) | 3 |
| cranberry | Cranberry | 36 | dose = PAC mg when stated (36 mg PAC); else extract mass own class | 2 |
| apple_cider_vinegar | Apple cider vinegar | 500 | `simple_mass`; capsules/gummies: ACV powder mg; liquids excluded | 1 |
| psyllium | Psyllium husk | 5000 | `simple_mass`; powder vs capsules | 2 |
| glucomannan | Glucomannan | 1000 | `simple_mass` | 3 |
| inulin | Inulin / FOS | 5000 | `simple_mass`; PHGG own id later | 3 |
| spirulina | Spirulina | 3000 | `simple_mass`; tablets vs powder | 2 |
| chlorella | Chlorella | 3000 | `simple_mass` | 3 |
| moringa | Moringa | 1000 | `simple_mass` | 3 |
| sea_moss | Sea moss | 1000 | `simple_mass`; gel excluded | 3 |
| tart_cherry | Tart cherry | 480 | extract mass; juice by ml excluded from ranking | 2 |
| pine_bark | Pine bark (Pycnogenol) | 100 | Pycnogenol own class | 3 |
| grape_seed | Grape seed extract | 300 | OPC % stated | 3 |
| horny_goat_weed | Horny goat weed | 500 | icariin % stated | 3 |
| shilajit | Shilajit | 500 | resin vs capsule; fulvic acid % stated | 2 |
| nettle | Nettle | 500 | root vs leaf own classes | 3 |
| dandelion | Dandelion | 500 | one class | 3 |
| kelp | (see iodine) | | | |
| hops | Hops | 300 | one class | 3 |
| kanna | Kanna (Sceletium) | 25 | Zembrin own class | 3 |
| gotu_kola | Gotu kola | 500 | one class | 3 |
| holy_basil | Holy basil (tulsi) | 500 | one class | 3 |
| mucuna | Mucuna pruriens | 300 | dose = L-DOPA mg when stated | 3 |
| black_pepper | Black pepper (piperine) | 5 | BioPerine; usually a cofactor, ranked only when sold alone | 3 |

### F.7 Nootropic & cognitive ingredients (`category: nootropics`) — beyond those already listed

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| citicoline | Citicoline (CDP-choline) | mg | simple_mass | 250 | Cognizin badge; also appears under choline via factor | 1 |
| alpha_gpc | Alpha-GPC | mg | simple_mass | 300 | 50% vs 99% powders — dose = alpha-GPC mg stated | 1 |
| huperzine_a | Huperzine A | mcg | vitamin_unit | 200 | one class | 2 |
| acetyl_l_carnitine | (see carnitine, alcar class) | | | | | |
| phosphatidylserine | (see F.5) | | | | | |
| creatine, l_theanine, caffeine, bacopa, lions_mane, rhodiola, ginkgo, tyrosine | (listed above) | | | | | |
| uridine | Uridine monophosphate | mg | simple_mass | 250 | one class | 3 |
| dmae | DMAE | mg | simple_mass | 250 | bitartrate: labels vary — review if unclear | 3 |

### F.8 General health & longevity (`category: general-health`)

| id | name | unit | type | comp. dose | classes / notes | tier |
|---|---|---|---|---|---|---|
| coq10 | CoQ10 | mg | simple_mass | 100 | ubiquinone vs ubiquinol — two classes | 1 |
| pqq | PQQ | mg | simple_mass | 20 | one class | 3 |
| alpha_lipoic_acid | Alpha-lipoic acid | mg | simple_mass | 300 | racemic vs r_ala (own class) | 2 |
| nmn | NMN | mg | simple_mass | 250 | check UK sale status at build time; one class | 2 |
| nr | Nicotinamide riboside | mg | simple_mass | 300 | Niagen badge | 3 |
| glucosamine | Glucosamine | mg | simple_mass | 1500 | sulfate_2kcl vs hcl — two classes (stated salt mass) | 1 |
| chondroitin | Chondroitin | mg | simple_mass | 800 | one class | 2 |
| msm | MSM | mg | simple_mass | 1000 | one class | 2 |
| hyaluronic_acid | Hyaluronic acid | mg | simple_mass | 100 | one class | 2 |
| lutein | Lutein | mg | simple_mass | 10 | zeaxanthin stored as component | 2 |
| lycopene | Lycopene | mg | simple_mass | 10 | one class | 3 |
| beta_glucan | Beta-glucan | mg | simple_mass | 250 | oat vs yeast (1,3/1,6) own classes | 3 |
| colostrum | Colostrum | mg | per_gram_macro | 1000 | IgG % as component | 3 |
| zinc_carnosine | Zinc carnosine | mg | simple_mass | 75 | own id (not zinc): stated PepZin GI mass | 3 |
| digestive_enzymes | Digestive enzymes | — | — | — | activity units differ per enzyme; **excluded until a type exists** | — |
| probiotics | Probiotics | CFU | cfu_count | 10 billion | Phase 10; strain list as components | 3 |
| multivitamin | Multivitamins | — | per_serving | 1 serving | Phase 10 | 3 |
| fibre_phgg | PHGG | mg | simple_mass | 5000 | one class | 3 |
| melatonin | — | | | | **excluded (prescription-only in UK)** | — |
| dhea | — | | | | **excluded (not legally sold as a supplement in UK)** | — |

### F.9 Hair, skin & nails ingredients — no separate ids; tags on existing ones
biotin, collagen, hyaluronic_acid, msm, silica, zinc, vitamin_c, saw_palmetto, astaxanthin. Tagging is a learn-page concern (§20), not a browse category.

### F.10 Counts and priorities
Tier 1 = 39 · Tier 2 = 46 · Tier 3 = 58 (143 ids, plus the Phase 10 types). Launch gate (§17) needs ≥ 100 live with ≥ 2 products — so Tier 1 + most of Tier 2. Feed reality decides the rest: if a compound has < 2 products across all feeds, its pages don't build and it waits for more retailers.

### F.11 Exclusions (do not add without a DECISIONS.md entry)
Melatonin (Rx-only in UK) · DHEA, pregnenolone (not legally sold as supplements in UK) · kava (banned in UK) · yohimbine, ephedra, DMAA, DMHA, higenamine and similar stimulants · racetams, noopept, phenibut and other Psychoactive Substances Act items · SARMs, prohormones, anything marketed as a PED · CBD (separate regulatory regime — Novel Foods; revisit later as its own project) · protein powders and mass gainers (incumbent comparator exists; revisit) · proprietary blends with undisclosed amounts (unrankable by definition — shown as unverified only) · liquid juices and gels sold by ml where the active isn't stated per ml.

---

## Appendix A — `config/compounds.yml` (starter, 10 compounds)

Factors are elemental mass fractions of the anhydrous salt/chelate unless noted. They are estimates; labels that state elemental content always win. Verify against a reference (e.g. NIH ODS fact sheets, supplier specs) during Phase 1 and cite the source in DECISIONS.md.

```yaml
version: 1
compounds:

  - id: magnesium
    name: Magnesium
    comparison_quantity: elemental magnesium
    unit: mg
    standard_dose: 100
    label_convention: ambiguous
    normalisation_type: mineral_elemental
    aliases: [magnesium, mag, mg glycinate, mag glycinate, magnesium bisglycinate, magnesium citrate, magnesium malate, magnesium taurate, magnesium threonate, magtein, magnesium oxide, magnesium chloride]
    accepted_cofactors: [vitamin b6, pyridoxine, p5p]
    forms:
      - id: bisglycinate
        names: [bisglycinate, glycinate, diglycinate, chelate, buffered chelate]
        class: mg_glycinate
        elemental_factor: 0.141
        note: "Anhydrous magnesium bisglycinate ~14% Mg. 'Buffered' chelates include oxide and run higher — treat as unclear if 'buffered' and no elemental stated."
      - id: citrate
        names: [citrate]
        class: mg_citrate
        elemental_factor: 0.16
        note: "Trimagnesium dicitrate anhydrous ~16%; hydrated/dimagnesium forms 11–15%. Prefer stated elemental."
      - id: malate
        names: [malate, di-magnesium malate, dimagnesium malate]
        class: mg_malate
        elemental_factor: 0.15
      - id: taurate
        names: [taurate, taurinate]
        class: mg_taurate
        elemental_factor: 0.089
      - id: l_threonate
        names: [l-threonate, threonate, magtein]
        class: mg_threonate
        elemental_factor: 0.083
      - id: oxide
        names: [oxide]
        class: mg_oxide
        elemental_factor: 0.603
      - id: chloride
        names: [chloride]
        class: mg_chloride
        elemental_factor: 0.12
        note: "Hexahydrate ~12%."
      - id: other
        names: [orotate, lactate, aspartate, carbonate, sulfate, sulphate, blend, complex]
        class: mg_other
        elemental_factor: null
        note: "No factor -> requires stated elemental or needs_review."

  - id: zinc
    name: Zinc
    comparison_quantity: elemental zinc
    unit: mg
    standard_dose: 15
    label_convention: elemental_default
    normalisation_type: mineral_elemental
    aliases: [zinc, zn, zinc picolinate, zinc citrate, zinc gluconate, zinc bisglycinate, zinc oxide, zinc sulphate, zinc sulfate]
    accepted_cofactors: [copper, vitamin c]
    forms:
      - { id: picolinate,   names: [picolinate],                 class: zn_picolinate,   elemental_factor: 0.211 }
      - { id: citrate,      names: [citrate],                    class: zn_citrate,      elemental_factor: 0.31 }
      - { id: gluconate,    names: [gluconate],                  class: zn_gluconate,    elemental_factor: 0.143 }
      - { id: bisglycinate, names: [bisglycinate, glycinate, chelate], class: zn_glycinate, elemental_factor: 0.306 }
      - { id: oxide,        names: [oxide],                      class: zn_oxide,        elemental_factor: 0.803 }
      - { id: sulfate,      names: [sulfate, sulphate],          class: zn_sulfate,      elemental_factor: 0.364, note: "Monohydrate ~36%; heptahydrate ~23%." }
      - { id: other,        names: [acetate, methionine, orotate, blend], class: zn_other, elemental_factor: null }

  - id: vitamin_d3
    name: Vitamin D3
    comparison_quantity: cholecalciferol
    unit: IU
    standard_dose: 1000
    unit_conversions: { mcg_to_IU: 40 }
    label_convention: elemental_default
    normalisation_type: vitamin_unit
    aliases: [vitamin d, vitamin d3, vit d, d3, cholecalciferol, colecalciferol]
    accepted_cofactors: [vitamin k2, mk-7, mk7]
    forms:
      - { id: d3,        names: [d3, cholecalciferol, colecalciferol], class: d3,        elemental_factor: null }
      - { id: d3_vegan,  names: [vegan d3, lichen],                  class: d3,        elemental_factor: null, note: "Same class; source shown as a badge." }
      - { id: d2,        names: [d2, ergocalciferol],                class: d2,        elemental_factor: null, note: "Separate class." }

  - id: vitamin_k2
    name: Vitamin K2
    comparison_quantity: menaquinone
    unit: mcg
    standard_dose: 100
    label_convention: elemental_default
    normalisation_type: vitamin_unit
    aliases: [vitamin k2, k2, mk-7, mk7, menaquinone-7, mk-4, mk4, menaquinone-4]
    accepted_cofactors: [vitamin d3]
    forms:
      - { id: mk7, names: [mk-7, mk7, menaquinone-7, menaq7, k2vital], class: k2_mk7, elemental_factor: null }
      - { id: mk4, names: [mk-4, mk4, menaquinone-4],                  class: k2_mk4, elemental_factor: null, note: "Doses in mg; separate class, standard dose 5 mg." , standard_dose_override: 5000 }

  - id: omega_3
    name: Omega-3
    comparison_quantity: EPA + DHA
    unit: mg
    standard_dose: 1000
    label_convention: compound_default
    normalisation_type: oil_components
    components_sum: [EPA, DHA]
    aliases: [omega 3, omega-3, fish oil, cod liver oil, krill oil, algae oil, algal oil, epa, dha]
    accepted_cofactors: [vitamin e, vitamin d3, astaxanthin]
    forms:
      - { id: fish_tg, names: [triglyceride, rtg, re-esterified], class: o3_fish, elemental_factor: null }
      - { id: fish_ee, names: [ethyl ester, ee],                  class: o3_fish, elemental_factor: null, note: "Same class as TG; form shown as badge." }
      - { id: fish_unspecified, names: [fish oil, omega 3],       class: o3_fish, elemental_factor: null }
      - { id: krill,   names: [krill],                            class: o3_krill, elemental_factor: null }
      - { id: algae,   names: [algae, algal, vegan omega],        class: o3_algae, elemental_factor: null }
      - { id: cod_liver, names: [cod liver],                      class: o3_cod_liver, elemental_factor: null, note: "Contains vitamins A/D; separate class." }

  - id: creatine
    name: Creatine
    comparison_quantity: creatine monohydrate
    unit: mg
    standard_dose: 5000
    label_convention: compound_default
    normalisation_type: simple_mass
    aliases: [creatine, creatine monohydrate, creapure, micronised creatine, micronized creatine, creatine hcl, creatine hydrochloride]
    accepted_cofactors: []
    forms:
      - { id: monohydrate, names: [monohydrate, micronised, micronized, creapure], class: cr_mono, elemental_factor: null }
      - { id: hcl,         names: [hcl, hydrochloride],                       class: cr_hcl,  elemental_factor: null, standard_dose_override: 1500 }
      - { id: other,       names: [buffered, kre-alkalyn, nitrate, ethyl ester, blend], class: cr_other, elemental_factor: null }

  - id: ashwagandha
    name: Ashwagandha
    comparison_quantity: root extract
    unit: mg
    standard_dose: 600
    label_convention: compound_default
    normalisation_type: extract_standardised
    standardisation_component: withanolides
    aliases: [ashwagandha, withania, withania somnifera, ksm-66, ksm66, sensoril, shoden]
    accepted_cofactors: [black pepper, piperine, bioperine]
    forms:
      - { id: ksm66,           names: [ksm-66, ksm66],            class: ash_ksm66,   elemental_factor: null, note: "5% withanolides (HPLC)." }
      - { id: sensoril,        names: [sensoril],                 class: ash_sensoril, elemental_factor: null, note: "10% withanolides; leaf+root." }
      - { id: shoden,          names: [shoden],                   class: ash_shoden,  elemental_factor: null, note: "35% withanolides; standard dose 120 mg.", standard_dose_override: 120 }
      - { id: generic_extract, names: [root extract, extract],    class: ash_generic, elemental_factor: null, note: "Withanolide % varies; store as component." }
      - { id: root_powder,     names: [root powder, powder, whole root], class: ash_powder, elemental_factor: null }

  - id: vitamin_c
    name: Vitamin C
    comparison_quantity: vitamin C (ascorbate equivalent)
    unit: mg
    standard_dose: 1000
    label_convention: elemental_default
    normalisation_type: simple_mass
    aliases: [vitamin c, vit c, ascorbic acid, sodium ascorbate, calcium ascorbate, ester-c, liposomal vitamin c]
    accepted_cofactors: [rosehip, bioflavonoids, citrus bioflavonoids, zinc]
    forms:
      - { id: ascorbic_acid,   names: [ascorbic acid],            class: vc_standard, elemental_factor: null }
      - { id: buffered,        names: [sodium ascorbate, calcium ascorbate, magnesium ascorbate, ester-c, buffered], class: vc_standard, elemental_factor: null, note: "Labels state vitamin C content; use stated." }
      - { id: liposomal,       names: [liposomal],                class: vc_liposomal, elemental_factor: null }
      - { id: timed_release,   names: [timed release, time release, slow release], class: vc_standard, elemental_factor: null }

  - id: vitamin_b12
    name: Vitamin B12
    comparison_quantity: cobalamin
    unit: mcg
    standard_dose: 1000
    label_convention: elemental_default
    normalisation_type: vitamin_unit
    aliases: [vitamin b12, b12, cobalamin, methylcobalamin, cyanocobalamin, adenosylcobalamin, hydroxocobalamin]
    accepted_cofactors: [folate, folic acid, methylfolate]
    forms:
      - { id: methyl,   names: [methylcobalamin, methyl],   class: b12_methyl, elemental_factor: null }
      - { id: cyano,    names: [cyanocobalamin, cyano],     class: b12_cyano,  elemental_factor: null }
      - { id: adenosyl, names: [adenosylcobalamin, dibencozide], class: b12_adenosyl, elemental_factor: null }
      - { id: hydroxo,  names: [hydroxocobalamin, hydroxo], class: b12_hydroxo, elemental_factor: null }
      - { id: unspecified, names: [b12],                    class: b12_unspecified, elemental_factor: null }

  - id: l_theanine
    name: L-Theanine
    comparison_quantity: L-theanine
    unit: mg
    standard_dose: 200
    label_convention: elemental_default
    normalisation_type: simple_mass
    aliases: [l-theanine, theanine, suntheanine]
    accepted_cofactors: []
    forms:
      - { id: l_theanine, names: [l-theanine, theanine, suntheanine], class: thea, elemental_factor: null }
```

Schema notes for the loader: `standard_dose_override` on a form replaces the compound's standard dose for that class; `unit` must be one of mg/mcg/IU (CFU and g arrive with their types in Phase 10); `elemental_factor` null means "use stated amount only"; every compound carries `category` (one of the Appendix F section keys) and `tier` (1–3); the 10 v1 compounds above are the prototype subset of Appendix F and must be reconciled with it (same ids) in Phase 6b.

---

## Appendix B — Golden label set (30)

Format for `tests/golden/labels.yml`: each item has `id`, `title`, `description`, `price_gbp`, and `expect` with the fields that must match (others ignored). Tolerances: amounts ±1 %, price per dose ±1 %, servings exact.

| # | Title (as a retailer might write it) | Expected |
|---|---|---|
| 1 | Magnesium Bisglycinate 2000mg (providing 200mg elemental magnesium) 180 Capsules — 2 capsules per serving | compound magnesium; form bisglycinate; servings 90; amount 200 mg; basis stated_elemental; £14.99 → £0.0833 per 100 mg |
| 2 | Magnesium Glycinate 500mg — 120 Tablets (1 per day) | form bisglycinate; servings 120; amount ≈ 70.5 mg; basis estimated_from_compound; not needs_review |
| 3 | Magnesium Citrate 200mg 120 Vegan Capsules | form citrate; amount 200; basis unclear → `needs_review: ambiguous_basis` |
| 4 | Magnesium Citrate Powder 200g — 1 level teaspoon (4g) provides 400mg magnesium | form citrate; pack 200 g; units_per_serving 4; servings 50; amount 400 stated_elemental |
| 5 | Magnesium Oxide 500mg 90 tabs | form oxide; amount ≈ 301.5 mg estimated |
| 6 | Magnesium Taurate 1000mg (2 caps) 120 caps | form taurate; servings 60; amount ≈ 89 mg estimated |
| 7 | Magtein Magnesium L-Threonate 2000mg (3 caps) — 144mg magnesium — 90 caps | form l_threonate; servings 30; amount 144 stated_elemental |
| 8 | ZMA Zinc Magnesium B6 — 90 caps | actives: zinc (primary, first in title) and magnesium, each with its own amount where stated; B6 in other_actives; multi_ingredient true (magnesium is not an accepted cofactor of zinc); indexed under both, absent from default tables, present with the combinations toggle |
| 9 | Zinc Picolinate 50mg 100 Capsules | compound zinc; form picolinate; amount 50; basis stated (convention); confidence ≤ 0.8 |
| 10 | Zinc Bisglycinate 25mg (as zinc bisglycinate 82mg) 120 tabs | amount 25 stated_elemental; evidence contains "25mg" |
| 11 | Zinc Gluconate 15mg with Copper 1mg 180 tabs | compound zinc; cofactor copper accepted; single-ingredient for ranking |
| 12 | Vitamin D3 4000IU (100µg) 365 Softgels | compound vitamin_d3; amount 4000 IU; servings 365 |
| 13 | Vitamin D3 25mcg High Strength 90 Tablets | amount 1000 IU (converted); servings 90 |
| 14 | Vegan Vitamin D3 2000iu from Lichen 120 caps | form d3_vegan; class d3; amount 2000 |
| 15 | Vitamin D3 1000IU 3 x 90 Tablets Multipack | multipack 3; servings 270 |
| 16 | Vitamin D3 + K2 (2000IU / 75µg MK-7) 90 caps | actives: vitamin_d3 2000 IU (primary, title order) and vitamin_k2 mk7 75 mcg; each accepts the other as a cofactor → multi_ingredient false; ranks in both the d3 and k2_mk7 tables |
| 17 | Vitamin K2 MK-7 100µg 90 caps | compound vitamin_k2; form mk7; amount 100 mcg |
| 18 | Vitamin K2 MK-4 5mg 60 caps | form mk4; class k2_mk4; amount 5000 mcg; standard dose override 5000 |
| 19 | Omega 3 Fish Oil 1000mg 180 Softgels — EPA 180mg DHA 120mg per softgel | components EPA 180, DHA 120; amount 300 (sum); servings 180; basis stated_component_sum |
| 20 | Omega 3 1000mg 120 Capsules | no EPA/DHA → `needs_review: no_epa_dha` |
| 21 | High Strength Omega 3 — 2 softgels provide EPA 660mg DHA 440mg — 120 softgels | units_per_serving 2; servings 60; amount 1100 |
| 22 | Krill Oil 500mg — EPA 60mg DHA 28mg per capsule — 60 caps | form krill; class o3_krill; amount 88 |
| 23 | Creatine Monohydrate Powder 500g — 5g serving | form monohydrate; pack 500 g; units_per_serving 5; servings 100; amount 5000 |
| 24 | Creatine Monohydrate 1kg Unflavoured — 3g scoop (333 servings) | servings 333 (stated) vs 333.3 computed → no conflict; per 5 g = price/1000 g × 5 |
| 25 | Creatine Monohydrate Capsules — 4 capsules provide 3000mg — 240 caps | units_per_serving 4; servings 60; amount 3000 |
| 26 | Creatine HCL 750mg 120 caps | form hcl; class cr_hcl; never in cr_mono table |
| 27 | Ashwagandha KSM-66 500mg 90 caps | form ksm66; amount 500 |
| 28 | Ashwagandha 5000mg (from 500mg 10:1 root extract) 120 tabs | form generic_extract; extract_ratio "10:1"; amount 500 (extract mass, not 5000) |
| 29 | Liposomal Vitamin C 1000mg — 250ml — 5ml serving | form liposomal; class vc_liposomal; pack 250 ml; units_per_serving 5; servings 50; amount 1000 |
| 30 | Vitamin B12 1mg Methylcobalamin 180 Tablets | form methyl; amount 1000 mcg (converted from mg); servings 180 |

Also include three **negative** fixtures outside the 30 (must be dropped at ingest, not extracted): a whey protein, a magnesium bath flakes product, a multivitamin.

---

## Appendix C — Normaliser system prompt (v1.0.0)

```
You extract structured facts from UK supplement product listings. You never estimate,
never compute prices, and never add information that is not in the text.

Input: a product title and description from a retailer. Output: a single JSON object
matching the provided schema. Rules:

1. actives: one entry for EVERY candidate compound (the user message lists the
   candidates, at most 8) that is present as an active in this product. Fill each
   entry's compound_id, form_raw, form_id, amount_per_serving, amount_unit,
   amount_refers_to, components, extract_ratio, branded_extract and evidence.
   If none of the candidates is present, actives is an empty list. A multivitamin
   or a broad blend still gets an entry per candidate it contains.
2. form_raw: copy the form words exactly as written (e.g. "bisglycinate", "MK-7",
   "KSM-66", "ethyl ester"). form_id: map to the closest id from that compound's
   form list supplied in the user message; null if unsure.
   is_single_ingredient: true only when exactly one active is present, counting
   candidates and other_actives together.
3. pack_units / pack_unit_type: the count of capsules, tablets, softgels, gummies,
   sachets, or grams/ml for powders and liquids. For "3 x 90 tablets" set pack_units 90
   and multipack_count 3.
4. units_per_serving: how many units the label says make one serving ("2 capsules
   provide", "5g scoop", "5ml"). If not stated for capsules/tablets, set 1 with
   confidence reduced.
5. amount_per_serving + amount_unit: the headline amount per serving of the main
   active. amount_refers_to:
   - "elemental" if the text says providing/elemental/as <mineral>/NRV or gives
     the mineral amount separately from the compound mass;
   - "compound" if the number is clearly the salt/chelate mass (e.g. "magnesium
     bisglycinate 2000mg" with a separate "providing 200mg magnesium" → put 200 in
     amount_per_serving as elemental and 2000 in components as "compound_mass");
   - "total_oil" for fish/krill/algae oil mass;
   - "extract" for herbal extract mass;
   - "unclear" if you cannot tell. Do not guess.
6. components: every sub-amount stated (EPA, DHA, withanolides %, compound_mass,
   "equivalent to X mg herb"). Copy numbers exactly.
7. extract_ratio: e.g. "10:1" if stated. branded_extract: KSM-66, Sensoril, Shoden,
   Creapure, Magtein, Suntheanine, etc. if stated.
8. other_actives: every other active ingredient named (vitamin B6, black pepper,
   copper, vitamin K2 …). Exclude excipients (cellulose, magnesium stearate, rice
   flour, capsule shell, silica).
9. tested_claims: copy testing/certification claims verbatim ("Informed Sport",
   "third-party tested"). Do not infer.
10. evidence: for every numeric field you fill, quote the exact substring it came from.
    A number without evidence will be discarded.
11. confidence: 0–1 for the whole extraction. Below 0.7 means a human should look.
12. review_reasons: short phrases for anything odd (conflicting numbers, serving size
    missing, "buffered" chelate, marketing claims that contradict the label).

Output JSON only.
```

The user message contains: the compound/form list (ids and names from compounds.yml, filtered to compounds whose aliases matched the listing), then `TITLE:` and `DESCRIPTION:` blocks. Truncate descriptions to 3,000 characters, keeping the nutrition/ingredients section if it can be located by keywords ("per serving", "ingredients", "nutritional information").

---

## Appendix D — Seed CSV template (`data/seed/<retailer_id>.csv`)

Columns, in order. Fill from the real product page; leave unknowns blank, never guess.

```
merchant_pid,ean,brand,title,description,url,image_url,price_gbp,in_stock,captured_on
```

- `merchant_pid`: retailer's own product id or the URL slug.
- `description`: paste the full nutrition/ingredients text; this is what the normaliser reads.
- `url`: the plain product URL for now (affiliate deep links replace it later via `retailers.yml` link template).
- `captured_on`: ISO date the price was read.
- Aim: 50+ rows, 10 compounds, ≥ 2 retailers, deliberately including at least 5 awkward labels (a "providing" case, a compound-only case, a multipack, a powder, a liquid).

---

## Appendix E — `docs/DECISIONS.md` template

```
# Decisions log

| Date | Decision | Why | Alternatives considered | Affects |
|---|---|---|---|---|
| 2026-09-17 | Adopt brief v1.0 | — | — | all |
```

Add a row whenever a rule, factor, model id, schema, or scope changes. Cite sources for factor changes.

---

## Kick-off prompt for Claude Code (paste as the first message)

> Read CLAUDE.md and docs/BRIEF.md in full. Confirm in five bullet points what the prototype is, what it is not, the hard rules you will follow, and any questions where the brief is ambiguous. Then start Phase 0 only: scaffold the repo exactly as CLAUDE.md's repo map describes, get `make check` green with a placeholder site, and stop for review. Do not write the normaliser or any pages yet.
