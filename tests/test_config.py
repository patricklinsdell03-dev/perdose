"""Every config file in the repo map exists and parses as YAML."""

from pathlib import Path

import pytest
import yaml

from pipeline.settings import load_llm_config, parse_env

CONFIG_FILES = [
    "compounds.yml",
    "retailers.yml",
    "llm.yml",
    "site.yml",
    "factor_sources.yml",
    "priority.yml",
    "claims_banned.yml",
]


@pytest.mark.parametrize("name", CONFIG_FILES)
def test_config_file_parses(name):
    data = yaml.safe_load(Path("config", name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_llm_config_loads():
    config = load_llm_config()
    assert config.models.default.id
    assert config.models.escalation.id
    assert config.prompt_version


def test_env_file_parsing():
    text = "# comment\nFIXTURE_A=plain\nFIXTURE_B='quoted'\nFIXTURE_EMPTY=\n\nnot a pair\n"
    assert parse_env(text) == {"FIXTURE_A": "plain", "FIXTURE_B": "quoted"}
