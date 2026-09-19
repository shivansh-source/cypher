"""Connector for Wazuh EDR/SIEM agent and alert data.

Normalizes Wazuh agent status and alert output into
``schema/aggregated_assets.schema.json`` ``assets[].edr`` entries, and may
also emit ``assets[].findings`` for Wazuh's own vulnerability-detection
module (CVE findings from installed-package inventory) if that module is
enabled.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class WazuhConnector(Connector):
    """Fetches and normalizes Wazuh agent/alert data.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "wazuh_connector"

    def fetch(self) -> Any:
        """Retrieve raw agent status and recent alerts from the Wazuh API.

        Returns:
            Parsed but untransformed agent list and alert data.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch".
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map Wazuh agent/alert data to schema-shaped ``edr`` fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching the ``assets[].edr`` shape (and,
            where applicable, ``assets[].findings[]`` entries for
            vulnerability-detection-module results), with
            ``provenance.connector`` set to ``"wazuh_connector"``.

        Must never:
            Report ``agent_installed: true`` for a host with no
            corresponding Wazuh agent record, or infer ``agent_healthy``
            from anything other than the agent's actual reported status.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a Wazuh agent (by agent ID/hostname) to a stable asset_id.

        Args:
            normalized_fragment: One normalized fragment.

        Returns:
            The stable ``asset_id`` string, resolved via the same identity
            mechanism as ``cmdb_connector.py``.
        """
        raise NotImplementedError
