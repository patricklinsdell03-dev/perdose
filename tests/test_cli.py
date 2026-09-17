import pytest

from pipeline.cli import NOT_BUILT_YET, main


def test_golden_runs_on_empty_set():
    assert main(["golden"]) == 0


@pytest.mark.parametrize("command", sorted(NOT_BUILT_YET))
def test_unbuilt_commands_fail_loudly(command, capsys):
    assert main([command]) == 1
    assert "not built yet" in capsys.readouterr().out
