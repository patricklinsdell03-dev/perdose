from pipeline.cli import main


def test_golden_runs_on_empty_set():
    assert main(["golden"]) == 0


def test_content_needs_a_compound(capsys):
    assert main(["content"]) == 1
    assert "make content COMPOUND=" in capsys.readouterr().out


def test_content_reports_an_ai_outage_in_words(monkeypatch, capsys):
    import anthropic
    import httpx

    def outage(*args, **kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://fixture"))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key-not-real")
    monkeypatch.setattr("pipeline.content.run.draft", outage)
    assert main(["content", "--compound", "magnesium"]) == 1
    assert "the AI service returned an error (APIConnectionError)" in capsys.readouterr().out
