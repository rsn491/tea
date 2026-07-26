from unittest.mock import patch

import pytest

from tea.main import build_parser, main


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


def test_parser_defaults_summary_export_and_baseline_to_none():
    args = build_parser().parse_args(["some_target"])
    assert args.summary_export is None
    assert args.baseline is None


def test_parser_parses_summary_export_and_baseline():
    args = build_parser().parse_args(
        ["some_target", "--summary-export", "out.json", "--baseline", "base.json"]
    )
    assert args.summary_export == "out.json"
    assert args.baseline == "base.json"


def test_main_threads_summary_export_and_baseline_into_run():
    with (
        patch("tea.main.run", return_value=True) as run_mock,
        patch("tea.main.print_banner"),
    ):
        main(["some_target", "--summary-export", "out.json", "--baseline", "base.json"])
    _, kwargs = run_mock.call_args
    assert kwargs["summary_export"] == "out.json"
    assert kwargs["baseline"] == "base.json"
