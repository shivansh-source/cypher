"""Connector for external threat intelligence feeds: EPSS and CISA KEV.

Enriches existing findings (produced by other connectors) with EPSS
exploit-probability scores and CISA KEV listing status, and normalizes any
asset-level threat-intel context into
``schema/aggregated_assets.schema.json`` ``assets[].threat_intel``.

Unlike the other connectors, this one typically runs as an enrichment pass
over findings already normalized by a scanner connector (matching on
``cve_id``), rather than producing brand-new findings from a scan of its
own.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class ThreatIntelConnector(Connector):
    """Fetches and normalizes EPSS/KEV threat intelligence.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey. Note that :meth:`normalize`
    here produces enrichment fragments keyed by ``cve_id`` rather than
    standalone findings.
    """

    name: str = "threat_intel_connector"

    def fetch(self) -> Any:
        """Retrieve the current EPSS score set and CISA KEV catalog.

        Returns:
            Parsed but untransformed EPSS scores (per CVE) and the KEV
            catalog entries.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch" — a failed refresh must not be
            silently treated as "no CVEs are actively exploited".
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map EPSS/KEV data to per-CVE enrichment fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts keyed by ``cve_id`` carrying ``epss_score`` and
            ``kev_listed``, intended to be merged into existing
            ``assets[].findings[]`` entries that share the same
            ``cve_id`` — not to create new findings from scratch.

        Must never:
            Fabricate an EPSS score for a CVE not present in the fetched
            data; leave it null/absent instead so the engine can treat it
            as genuinely unknown.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Not applicable in the usual sense: enrichment is CVE-keyed, not asset-keyed.

        Args:
            normalized_fragment: One normalized enrichment fragment.

        Returns:
            Should not be called directly for this connector's output;
            the aggregation pipeline merges enrichment fragments into
            existing findings by ``cve_id`` rather than by asset identity.
            TODO: confirm with the aggregation pipeline design whether this
            method should simply be unused for this connector or should
            raise a distinct error to make that explicit.
        """
        raise NotImplementedError
