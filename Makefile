# Every command listed in CLAUDE.md. Recipes are kept to single plain commands so
# they behave the same under sh (CI, macOS, Linux) and cmd.exe (Windows).

PIPELINE = uv run python -m pipeline.cli
COMPOUND ?=

.PHONY: setup ingest normalise price golden golden-live content content-check review review-apply seed-refresh seed-refresh-apply site check all

setup:
	uv sync
	npm --prefix site install

ingest:
	$(PIPELINE) ingest

normalise:
	$(PIPELINE) normalise

price:
	$(PIPELINE) price
	$(PIPELINE) export

golden:
	$(PIPELINE) golden $(if $(DRAFT),--draft $(DRAFT))

# Calls the real LLM for every golden label (costs pennies) and saves the results for replay.
golden-live:
	$(PIPELINE) golden --live $(if $(DRAFT),--draft $(DRAFT)) $(if $(ONLY),--only $(ONLY))

# Drafts a learn page with the AI (about 10-25p a page; stops above the cap in config/content.yml).
# DRY=1 lists the studies it would use and the estimated cost, and spends nothing.
content:
	$(PIPELINE) content --compound "$(COMPOUND)" $(if $(DRY),--dry-run)

content-check:
	$(PIPELINE) content-check

review:
	$(PIPELINE) review

review-apply:
	$(PIPELINE) review-apply

seed-refresh:
	$(PIPELINE) seed-refresh

seed-refresh-apply:
	$(PIPELINE) seed-refresh-apply

site:
	npm --prefix site run build

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest
	$(PIPELINE) content-check
	npm --prefix site run check
	npm --prefix site run build
	npm --prefix site run smoke

all: ingest normalise price site
