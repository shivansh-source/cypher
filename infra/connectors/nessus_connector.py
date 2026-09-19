"""Connector for Tenable Nessus vulnerability scan exports.

Normalizes Nessus scan results (via .nessus XML export or Tenable.io API)
into ``schema/aggregated_assets.schema.json`` ``assets[].findings`` entries.
Nessus's per-plugin severity scale (Info/Low/Medium/High/Critical) must be
mapped explicitly to the schema's criticality vocabulary — see
``core/assumptions.py`` if that mapping requires a judgement call rather
than a direct rename.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class NessusConnector(Connector):
    """Fetches and normalizes Tenable Nessus scan output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "nessus_connector"

    def fetch(self) -> Any:
        """Retrieve a raw Nessus scan export (.nessus XML or Tenable.io API response).

        Returns:
            Parsed but untransformed scan data — plugin results per host,
            exactly as Nessus reports them.

        Raises:
            An error appropriate to the transport (file not found, API auth
            failure, etc). Must not return an empty result to mean "could
            not fetch" — see base class contract.
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map Nessus plugin results to schema-shaped finding fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].findings[]`` in
            ``schema/aggregated_assets.schema.json``, with
            ``provenance.connector`` set to ``"nessus_connector"`` and
            ``provenance.raw_source_id`` set to the Nessus plugin ID.

        Must never:
            Pass through Nessus's Info/Low/Medium/High/Critical scale
            unmapped, or leave ``criticality`` null when Nessus reported a
            severity.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a Nessus host (by IP/hostname/FQDN) to a stable asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            The stable ``asset_id`` string, resolved via the same identity
            mechanism as ``cmdb_connector.py``.
        """
        raise NotImplementedError
