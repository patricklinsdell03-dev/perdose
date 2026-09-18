"""config/llm.yml and the .env file. Secrets are read here and never printed."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

LLM_CONFIG_PATH = Path("config/llm.yml")
ENV_PATH = Path(".env")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelChoice(_Model):
    id: str
    effort: str | None = None  # low | medium | high | xhigh | max; None = API default


class Models(_Model):
    default: ModelChoice
    escalation: ModelChoice


class Price(_Model):
    input: float = Field(ge=0)  # US dollars per million tokens
    output: float = Field(ge=0)


class LlmConfig(_Model):
    models: Models
    max_tokens: int = Field(gt=0)
    escalation_confidence_threshold: float = Field(ge=0, le=1)
    prompt_version: str
    max_calls_per_run: int = Field(gt=0)
    description_max_chars: int = Field(gt=0)
    # Learn-page drafting (`make content`, Phase 9) and the prices used for its cost line.
    content: ModelChoice | None = None
    pricing_usd_per_mtok: dict[str, Price] = {}
    gbp_per_usd: float = Field(default=0.75, gt=0)

    def cost_gbp(self, model_id: str, input_tokens: int, output_tokens: int) -> float | None:
        price = self.pricing_usd_per_mtok.get(model_id)
        if price is None:
            return None
        usd = (input_tokens * price.input + output_tokens * price.output) / 1_000_000
        return usd * self.gbp_per_usd


def load_llm_config(path: Path = LLM_CONFIG_PATH) -> LlmConfig:
    return LlmConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines; comments and empty values are skipped."""
    values = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#") and value.strip():
            values[key.strip()] = value.strip().strip("\"'")
    return values


def load_env(path: Path = ENV_PATH) -> None:
    """Copy .env into the environment (real env vars win)."""
    if path.exists():
        for key, value in parse_env(path.read_text(encoding="utf-8")).items():
            os.environ.setdefault(key, value)
