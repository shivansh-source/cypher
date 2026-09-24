"""Connectors that pull raw output from security tools and normalize it into
the shared contract at ``schema/aggregated_assets.schema.json``.

Every connector in this package obeys the fetch -> normalize -> attach
contract defined in ``base.py``. Nothing outside this package may know which
tool produced a given piece of data — see the repo-root ``CLAUDE.md``,
principle 3.
"""

from __future__ import annotations

from infra.connectors.greenbone_connector import GreenboneConnector as GreenboneConnector
from infra.connectors.iam_connector import IAMConnector as IAMConnector
from infra.connectors.prowler_connector import ProwlerConnector as ProwlerConnector
from infra.connectors.scoutsuite_connector import ScoutSuiteConnector as ScoutSuiteConnector
from infra.connectors.wazuh_connector import WazuhConnector as WazuhConnector

__all__ = [
    "GreenboneConnector",
    "IAMConnector",
    "ProwlerConnector",
    "ScoutSuiteConnector",
    "WazuhConnector",
]
