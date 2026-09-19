"""Connector for Prowler cloud security posture (CSPM) scan output.

Normalizes Prowler check results (AWS/Azure/GCP misconfiguration findings)
into ``schema/aggregated_assets.schema.json`` ``assets[].findings`` entries
of ``type: "misconfiguration"``. Prowler's PASS/FAIL/WARNING/INFO status
model and per-check severity must be mapped explicitly to the schema's
criticality vocabulary.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class ProwlerConnector(Connector):
    """Fetches and normalizes Prowler CSPM check output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "prowler_connector"

    def fetch(self) -> Any:
        """Retrieve raw Prowler output (JSON/OCSF report from a scan run).

        Returns:
            Parsed but untransformed per-check results across the scanned
            cloud accounts.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch".
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map Prowler check results to schema-shaped finding fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].findings[]``, restricted to
            failed checks (a PASS is not a finding), with
            ``provenance.connector`` set to ``"prowler_connector"`` and
            ``provenance.raw_source_id`` set to the Prowler check ID.

        Must never:
            Emit a finding for a PASSing check, or leave ``criticality``
            null when Prowler reported a severity for the check.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a cloud resource ARN/resource-id to a stable asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            The stable ``asset_id`` string, resolved via the same identity
            mechanism as ``cmdb_connector.py``.
        """
        raise NotImplementedError
