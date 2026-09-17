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

_To be written in Phase 3 (seed CSV) and Phase 6 (live feeds)._

## How to add a compound

1. Add an entry to `config/compounds.yml` (copy a similar compound). It needs: `id`, `name`, `category`, `tier`, `unit` (mg, mcg or IU), `standard_dose`, `label_convention`, `normalisation_type`, `aliases`, `accepted_cofactors`, and `forms` — each form with an `id`, `names`, a `class`, and an `elemental_factor` (or `null`). Never change an existing `id`.
2. For every non-null `elemental_factor`, add the chemical formula to `config/factor_sources.yml`. The tests recompute the factor from the formula and fail if they disagree by more than 1.5 %.
3. Add at least 3 golden labels for it in `tests/golden/labels.yml` (one straightforward, one awkward, one combination), each with a reference `extraction` and an `expect` block. List the compound under `compounds:` on each.
4. Run `make golden` — every label must pass — then `make check`.
5. (From Phase 6b) add it to `config/priority.yml`.

If the file has a mistake (duplicate id, factor outside 0–1, a form without a class, two forms in one class with different doses), loading fails with a message naming the compound.

## How to re-run a failed day

_To be written in Phase 5._

## How to rotate a key

_To be written in Phase 5._

## What to do when a feed column name changes

_To be written in Phase 6._

## Working down the unverified queue (`make review` / `make review-apply`)

_To be written in Phase 5._
