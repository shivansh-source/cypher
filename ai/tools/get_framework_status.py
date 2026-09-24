"""Tool: report control status against a named regulatory framework.

This function does not compute anything itself; it delegates to
``governance.mapper.compute_control_status`` for every control in the
requested framework. See repo-root ``CLAUDE.md`` principles 1, 2, and 6.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai.tools._snapshot import current_snapshot_or_unavailable
from governance.attestations import load_attestations
from governance.library_loader import load_control_library
from governance.mapper import compute_all_control_statuses, compute_weighted_score

#: Where the versioned control library YAML files live.
_CONTROL_LIBRARY_DIR = (
    Path(__file__).resolve().parent.parent.parent / "governance" / "control_library"
)

#: Matches ATTESTATION_STORE_PATH's default in .env.example.
_DEFAULT_ATTESTATION_STORE_PATH = "./data/attestations.json"


def get_framework_status(framework: str) -> dict[str, Any]:
    """Return current control-by-control status against a named framework.

    Args:
        framework: Framework key matching a filename under
            ``governance/control_library/`` (e.g. "rbi_2026_directions").

    Returns:
        A structured dict of ``governance.mapper.ControlStatus`` entries
        for every control in the framework — each carrying its library
        entry's ``parameter_name`` and ``framework_ref`` so it can be named
        without a second lookup — plus the framework's
        ``version``/``effective_from`` so the caller can tell which
        version of the framework this status was evaluated against, and
        ``governance.mapper.compute_weighted_score``'s result (always with
        its coverage and low-confidence share, never a bare percentage).

    Must never:
        Collapse individual control statuses into a single overall
        "compliant"/"non-compliant" verdict. Must never include or imply
        anything derived from ``core.optimizer`` output — see principle 6.
    """
    library_path = _CONTROL_LIBRARY_DIR / f"{framework}.yaml"
    if not library_path.is_file():
        raise NotImplementedError(f"no control library file for framework {framework!r}")

    snapshot = current_snapshot_or_unavailable()
    as_of = datetime.now(UTC)
    library = load_control_library(library_path, as_of.date())

    attestation_store = Path(
        os.environ.get("ATTESTATION_STORE_PATH", _DEFAULT_ATTESTATION_STORE_PATH)
    )
    attestations = load_attestations(attestation_store)

    statuses = compute_all_control_statuses(snapshot, library, attestations, as_of)
    entries = {control.id: control for control in library.controls}
    return {
        "framework": library.framework,
        "version": library.version,
        "effective_from": library.effective_from,
        "effective_to": library.effective_to,
        "snapshot_id": snapshot["snapshot_id"],
        "controls": [
            {
                **asdict(status),
                "parameter_name": entries[status.control_id].parameter_name,
                "framework_ref": entries[status.control_id].framework_ref,
            }
            for status in statuses
        ],
        "weighted_score": asdict(compute_weighted_score(library, statuses)),
    }
