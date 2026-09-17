"""Every config file in the repo map exists and parses as YAML."""

from pathlib import Path

import pytest
import yaml

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


def test_llm_model_ids_present():
    llm = yaml.safe_load(Path("config/llm.yml").read_text(encoding="utf-8"))
    assert llm["models"]["default"]
    assert llm["models"]["escalation"]
    assert llm["temperature"] == 0
