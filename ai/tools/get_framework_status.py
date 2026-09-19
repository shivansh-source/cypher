"""Tool: report control status against a named regulatory framework.

This function does not compute anything itself; it delegates to
``governance.mapper.compute_control_status`` for every control in the
requested framework. See repo-root ``CLAUDE.md`` principles 1, 2, and 6.
"""

from __future__ import annotations

from typing import Any


def get_framework_status(framework: str) -> dict[str, Any]:
    """Return current control-by-control status against a named framework.

    Args:
        framework: Framework key matching a filename under
            ``governance/control_library/`` (e.g. "rbi_2026_directions").

    Returns:
        A structured dict of ``governance.mapper.ControlStatus`` entries
        for every control in the framework, plus the framework's
        ``version``/``effective_from`` so the caller can tell which
        version of the framework this status was evaluated against.

    Must never:
        Collapse individual control statuses into a single overall
        "compliant"/"non-compliant" verdict. Must never include or imply
        anything derived from ``core.optimizer`` output — see principle 6.
    """
    raise NotImplementedError
