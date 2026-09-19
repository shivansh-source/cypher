"""Connector for nmap network exposure scans.

Normalizes nmap scan output into ``schema/aggregated_assets.schema.json``
``assets[].network`` entries (internet-facing status, open ports) and
``endpoints[]`` entries for discovered addresses.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class NmapConnector(Connector):
    """Fetches and normalizes nmap scan output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "nmap_connector"

    def fetch(self) -> Any:
        """Retrieve raw nmap scan output (XML export or direct invocation result).

        Returns:
            Parsed but untransformed per-host port/service scan results.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch" — a scan that could not run
            must be recorded in ``scan_scope.unreachable_scanners``, not
            silently reported as zero open ports.
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map nmap results to schema-shaped ``network``/``endpoints`` fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].network`` and
            ``endpoints[]``, with ``provenance.connector`` set to
            ``"nmap_connector"`` for any derived findings (e.g. an
            unexpectedly open port treated as a finding).

        Must never:
            Infer ``internet_facing`` from network range heuristics alone
            when the scan was explicitly scoped to internal ranges only.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a scanned IP/hostname to a stable asset_id.

        Args:
            normalized_fragment: One normalized fragment.

        Returns:
            The stable ``asset_id`` string, resolved via the same identity
            mechanism as ``cmdb_connector.py``. May return an
            unresolved/null-equivalent state via the ``endpoints[]``
            ``resolved_asset_id: null`` path rather than fabricating an
            asset_id when no match exists.
        """
        raise NotImplementedError
