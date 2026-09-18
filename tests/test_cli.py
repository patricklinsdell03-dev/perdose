from pipeline.cli import main


def test_golden_runs_on_empty_set():
    assert main(["golden"]) == 0


def test_content_needs_a_compound(capsys):
    assert main(["content"]) == 1
    assert "make content COMPOUND=" in capsys.readouterr().out
