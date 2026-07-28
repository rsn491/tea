from __future__ import annotations

import contextlib
import itertools
import sys
import threading

from .theme import primary
from .utils import _NO_SPINNER, _TTY


class _Spinner:
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str) -> None:
        self._label = label
        self._stopped = threading.Event()
        self._paused = threading.Event()  # set → spin thread should pause
        self._cleared = threading.Event()  # set → spin thread has cleared the line
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def set_label(self, label: str) -> None:
        """Update the spinner label (safe to call from any thread)."""
        self._label = label

    def _clear_line(self) -> None:
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _spin(self) -> None:
        if not _TTY or _NO_SPINNER:
            return
        for ch in itertools.cycle(self._FRAMES):
            if self._stopped.is_set():
                break
            if self._paused.is_set():
                self._clear_line()
                self._cleared.set()
                # Wait until resumed or stopped (poll every 50 ms)
                while self._paused.is_set() and not self._stopped.is_set():
                    self._stopped.wait(0.05)
                self._cleared.clear()
                continue
            sys.stdout.write(f"\r  {primary(ch)} {self._label} …")
            sys.stdout.flush()
            self._stopped.wait(0.08)
        self._clear_line()

    def __enter__(self) -> _Spinner:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopped.set()
        self._thread.join()

    @contextlib.contextmanager
    def paused(self):  # type: ignore[return]
        """Temporarily pause the spinner so the caller can write to stdout cleanly."""
        self._cleared.clear()
        self._paused.set()
        if _TTY and not _NO_SPINNER:
            self._cleared.wait()  # block until the spin thread has cleared the line
        try:
            yield
        finally:
            self._paused.clear()
