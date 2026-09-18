"""config/content.yml: literature search settings, the grading rubric and the cost cap."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONTENT_CONFIG_PATH = Path("config/content.yml")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LiteratureConfig(_Model):
    years: int = Field(gt=0)
    max_reviews: int = Field(ge=0)
    max_trials: int = Field(ge=0)
    max_background: int = Field(ge=0)
    title_exclusions: list[str] = []
    terms: dict[str, list[str]] = {}
    no_supplement_filter: list[str] = []


class StrongRule(_Model):
    reviews: int = Field(ge=0)
    participants: int = Field(ge=0)
    agree_share: float = Field(gt=0, le=1)


class ModerateRule(_Model):
    reviews: int = Field(ge=0)
    trials_instead: int = Field(ge=0)
    participants: int = Field(ge=0)


class InsufficientRule(_Model):
    reviews: int = Field(ge=0)
    trials: int = Field(ge=0)


class GradingConfig(_Model):
    status: Literal["proposed", "approved"]
    review_weight: float = Field(gt=0)
    trial_weight: float = Field(gt=0)
    agree_share: float = Field(gt=0, le=1)
    strong: StrongRule
    moderate: ModerateRule
    insufficient_below: InsufficientRule


class BudgetConfig(_Model):
    max_gbp_per_page: float = Field(gt=0)


class ContentConfig(_Model):
    version: int
    prompt_version: str
    literature: LiteratureConfig
    grading: GradingConfig
    budget: BudgetConfig


def load_content_config(path: Path = CONTENT_CONFIG_PATH) -> ContentConfig:
    return ContentConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
