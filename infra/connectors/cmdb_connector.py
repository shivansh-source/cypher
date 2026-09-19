"""Connector for the organization's CMDB (configuration management database).

This connector is the canonical source of asset identity for the whole
system: it is expected to define the ``asset_id`` resolution scheme that
every other connector's :meth:`resolve_asset_id` looks up against. It also
normalizes CMDB service/ownership records into
``schema/aggregated_assets.schema.json`` ``services[]`` entries.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class CMDBConnector(Connector):
    """Fetches and normalizes CMDB asset and service records.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "cmdb_connector"

    def fetch(self) -> Any:
        """Retrieve raw asset/service/ownership records from the CMDB.

        Returns:
            Parsed but untransformed CMDB records.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch".
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map CMDB records to schema-shaped ``services[]``/asset-identity fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``services[]`` in
            ``schema/aggregated_assets.schema.json``, plus the canonical
            asset-identity records that other connectors'
            :meth:`resolve_asset_id` methods look up against.

        Must never:
            Silently invent a ``criticality`` value for a service the CMDB
            has not explicitly tiered.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Return the CMDB's own stable asset identifier, unchanged.

        Args:
            normalized_fragment: One normalized fragment.

        Returns:
            The stable ``asset_id`` string as recorded by the CMDB itself —
            this connector defines identity rather than resolving against
            an external source.

        Must document:
            The exact identity key(s) (e.g. serial number, cloud resource
            ID, hostname+domain) other connectors must match against.
            TODO: finalize this key once the target organization's CMDB
            schema is known.
        """
        raise NotImplementedError
