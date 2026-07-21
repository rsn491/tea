from __future__ import annotations

import pytest

from tea.tui.theme import DefaultTheme, LightTheme, resolve_mode, set_mode
from tea.tui.theme import active as active_mod
from tea.tui.utils import _nearest_256, _rgb


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Each test starts with no TEA_THEME and the default palette restored."""
    monkeypatch.delenv("TEA_THEME", raising=False)
    original = active_mod._active
    yield
    active_mod._active = original


# ── resolve_mode: precedence ────────────────────────────────────────────────────


def test_resolve_mode_defaults_to_dark():
    assert resolve_mode() == "dark"


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_resolve_mode_accepts_explicit_flag(mode):
    assert resolve_mode(mode) == mode


def test_resolve_mode_reads_env_when_no_flag(monkeypatch):
    monkeypatch.setenv("TEA_THEME", "light")
    assert resolve_mode() == "light"


def test_resolve_mode_flag_beats_env(monkeypatch):
    monkeypatch.setenv("TEA_THEME", "light")
    assert resolve_mode("dark") == "dark"


def test_resolve_mode_normalizes_case_and_whitespace(monkeypatch):
    monkeypatch.setenv("TEA_THEME", "  LIGHT  ")
    assert resolve_mode() == "light"


# ── resolve_mode: fallback semantics ────────────────────────────────────────────


def test_invalid_flag_falls_through_to_valid_env(monkeypatch, capsys):
    monkeypatch.setenv("TEA_THEME", "light")
    assert resolve_mode("bogus") == "light"
    assert "unknown theme 'bogus'" in capsys.readouterr().err


def test_invalid_flag_and_no_env_falls_back_to_default(capsys):
    assert resolve_mode("bogus") == "dark"
    assert "unknown theme 'bogus'" in capsys.readouterr().err


def test_invalid_env_falls_back_to_default(monkeypatch, capsys):
    monkeypatch.setenv("TEA_THEME", "neon")
    assert resolve_mode() == "dark"
    assert "unknown theme 'neon'" in capsys.readouterr().err


# ── set_mode: installs the active palette ───────────────────────────────────────


def test_set_mode_installs_light_theme():
    assert set_mode("light") == "light"
    assert active_mod.active_theme() is LightTheme


def test_set_mode_installs_dark_theme():
    set_mode("light")
    assert set_mode("dark") == "dark"
    assert active_mod.active_theme() is DefaultTheme


def test_set_mode_default_is_dark_theme():
    assert set_mode() == "dark"
    assert active_mod.active_theme() is DefaultTheme


# ── _rgb / 256-color fallback ───────────────────────────────────────────────────


def test_rgb_emits_truecolor_when_supported(monkeypatch):
    monkeypatch.setattr("tea.tui.utils._TRUECOLOR", True)
    assert _rgb(74, 168, 120) == "38;2;74;168;120"


def test_rgb_falls_back_to_256_without_truecolor(monkeypatch):
    monkeypatch.setattr("tea.tui.utils._TRUECOLOR", False)
    assert _rgb(74, 168, 120) == f"38;5;{_nearest_256(74, 168, 120)}"


@pytest.mark.parametrize(
    "rgb,index",
    [
        ((0, 0, 0), 16),  # black → cube origin
        ((255, 255, 255), 231),  # white → cube corner
        ((4, 4, 4), 16),  # near-black gray → cube origin
        ((250, 250, 250), 231),  # near-white gray → cube corner
        ((128, 128, 128), 244),  # mid gray → grayscale ramp
        ((74, 168, 120), 72),  # SENCHA → 16 + 36*1 + 6*3 + 2
    ],
)
def test_nearest_256_maps_known_colors(rgb, index):
    assert _nearest_256(*rgb) == index
