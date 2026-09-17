# Every command listed in CLAUDE.md. Recipes are kept to single plain commands so
# they behave the same under sh (CI, macOS, Linux) and cmd.exe (Windows).

PIPELINE = uv run python -m pipeline.cli
COMPOUND ?=

.PHONY: setup ingest normalise price golden golden-live content content-check review review-apply site check all

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
	$(PIPELINE) golden

# Calls the real LLM for every golden label (costs pennies) and saves the results for replay.
golden-live:
	$(PIPELINE) golden --live

content:
	$(PIPELINE) content --compound "$(COMPOUND)"

content-check:
	$(PIPELINE) content-check

review:
	$(PIPELINE) review

review-apply:
	$(PIPELINE) review-apply

site:
	npm --prefix site run build

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest
	npm --prefix site run check
	npm --prefix site run build
	npm --prefix site run smoke

all: ingest normalise price site
