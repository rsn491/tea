from unittest.mock import patch

import pytest

from tea.main import main


def test_main_help_flag_prints_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "tea" in out


def test_main_without_target_prints_help(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "target" in out


def test_main_returns_zero_when_all_tests_pass():
    with (
        patch("tea.main.run", return_value=True),
        patch("tea.main.print_banner"),
    ):
        assert main(["some_target"]) == 0


def test_main_returns_one_when_a_test_fails():
    with (
        patch("tea.main.run", return_value=False),
        patch("tea.main.print_banner"),
    ):
        assert main(["some_target"]) == 1
