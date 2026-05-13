from __future__ import annotations

import contextvars

# When set to a list, RunBuilder.run() appends each AgentRun to it and
# suppresses the per-run metrics print.
_active_collector: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "_active_collector", default=None
)

# When set, check() appends (label, passed) tuples here instead of raising.
_active_checks: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "_active_checks", default=None
)
