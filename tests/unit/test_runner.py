from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from tea.runner import load_module


def test_load_module_raises_import_error_when_spec_is_none(tmp_path):
    # A .txt file is not a recognised Python module; spec_from_file_location returns None
    non_py = tmp_path / "not_python.txt"
    non_py.write_text("hello")
    with pytest.raises(ImportError, match="recognisable Python file"):
        load_module(non_py)


def test_load_module_raises_import_error_when_loader_is_none(tmp_path):
    # Simulate spec_from_file_location returning a spec with loader=None
    dummy = tmp_path / "dummy.py"
    dummy.write_text("x = 1")
    fake_spec = importlib.util.spec_from_file_location("dummy", dummy)
    assert fake_spec is not None  # sanity check
    fake_spec.loader = None  # type: ignore[assignment]
    with patch("importlib.util.spec_from_file_location", return_value=fake_spec):
        with pytest.raises(ImportError, match="recognisable Python file"):
            load_module(dummy)
