import pytest

from harntest.main import main


def test_main_help_flag_prints_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "harntest" in out


def test_main_without_target_prints_help(capsys):
    main([])
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "target" in out
