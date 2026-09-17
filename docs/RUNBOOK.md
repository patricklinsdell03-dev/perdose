# Runbook — how to operate the pipeline and site

Stub. Each section is filled in by the phase that builds the thing it describes (brief §14).

## First-time setup

1. Install `uv`, Node.js (LTS), `git` and GNU `make`.
2. `make setup` — installs Python and site dependencies.
3. Copy `.env.example` to `.env` and fill in keys (not needed until Phase 2).
4. `make check` — lint, tests, site type-check and build. Must be green before every commit.

Preview the site locally: `npm --prefix site run dev`.

## Daily commands

See the command list in `CLAUDE.md`. In Phase 0 only `make setup`, `make golden`, `make site` and `make check` do anything; the rest report which phase builds them.

## How to add a retailer

_To be written in Phase 3 (seed CSV) and Phase 6 (live feeds)._

## How to add a compound

_To be written in Phase 1. Checklist in brief §21.1._

## How to re-run a failed day

_To be written in Phase 5._

## How to rotate a key

_To be written in Phase 5._

## What to do when a feed column name changes

_To be written in Phase 6._

## Working down the unverified queue (`make review` / `make review-apply`)

_To be written in Phase 5._
