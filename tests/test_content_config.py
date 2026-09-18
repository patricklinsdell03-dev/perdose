"""config/content.yml loads and keeps its safety settings."""

from pipeline.content.config import load_content_config


def test_content_config_loads():
    config = load_content_config()
    assert config.literature.years == 15
    assert config.budget.max_gbp_per_page > 0
    # The rubric is Claude's proposal until Patrick approves it (content/REVIEW.md).
    assert config.grading.status in ("proposed", "approved")
