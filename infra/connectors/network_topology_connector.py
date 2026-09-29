"""Connector for real AWS network topology (subnets, security-group-derived exposure).

Normalizes an export from ``infra/inventory/export_network_topology.py`` into
``schema/aggregated_assets.schema.json`` ``assets[].network`` entries
(``segment_id``, ``internet_facing``) and the top-level ``network_topology``
object (``segments``, ``segment_reachability``) that
``core/engine/attack_graph.py`` reads.

Like ``iam_connector.py`` and the other file sources, this connector never
calls AWS itself: an operator or CI job runs the export script, and this
connector only reads the result via ``NETWORK_TOPOLOGY_EXPORT_PATH``.

Unlike every other connector, its job does not fit the "one fragment per
asset" contract cleanly: ``network_topology`` is a *snapshot-level* fact, not
an asset one. This connector still emits normal per-asset fragments for
``assets[].network`` (so :meth:`run` and the standard merge in
``interfaces/cli/cypher.py`` work unchanged), and separately caches the
snapshot-level object on :attr:`topology` for ``cypher`` to read directly
from this same instance after :meth:`run` — the same kind of interfaces-layer
bridging ``cypher.py`` already does for ``cmdb_connector.py``'s
``endpoints[]`` reshaping (see that module's own docstring on why).

Because the same physical machine is known under more than one placeholder
identity scheme in this codebase (Wazuh/Greenbone mint ``host:<ip>``;
Prowler/ScoutSuite mint ``cloud:<ARN>`` — see ``docs/CONNECTORS.md`` on the
duplicate-asset caveat), this connector emits a fragment under *each* scheme
per instance, so whichever representation another connector actually created
in a given run receives the real network facts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infra.connectors import _env
from infra.connectors.base import Connector

_NETWORK_TOPOLOGY_EXPORT_PATH_ENV = "NETWORK_TOPOLOGY_EXPORT_PATH"


class NetworkTopologyConnectorError(RuntimeError):
    """Raised when this connector cannot read or make sense of the topology export.

    Always names the file path or the missing/invalid field involved.
    """


def _require_str(document: dict[str, Any], key: str, connector_name: str, path: Path) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise NetworkTopologyConnectorError(
            f"{connector_name}: {path} is missing required string field {key!r}"
        )
    return value


class NetworkTopologyConnector(Connector):
    """Fetches and normalizes an AWS network-topology export.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey. See this module's docstring for
    why :attr:`topology` exists alongside the normal fragment output.
    """

    name: str = "network_topology_connector"

    def __init__(self) -> None:
        #: Set by :meth:`normalize`; the snapshot-level ``network_topology``
        #: object, valid only after :meth:`run` has completed successfully.
        self.topology: dict[str, Any] | None = None

    def fetch(self) -> Any:
        """Read the JSON file at ``NETWORK_TOPOLOGY_EXPORT_PATH``.

        Returns:
            The parsed, untransformed export document (see
            ``export_network_topology.py``'s module docstring for its shape).

        Raises:
            NetworkTopologyConnectorError: If the environment variable is
                unset, or the file is missing, unreadable, or not valid
                JSON. Must not return an empty result to mean "could not
                fetch".
        """
        path = Path(
            _env.require(
                _NETWORK_TOPOLOGY_EXPORT_PATH_ENV, self.name, NetworkTopologyConnectorError
            )
        )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise NetworkTopologyConnectorError(
                f"{self.name}: could not read {path}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise NetworkTopologyConnectorError(
                f"{self.name}: {path} is not valid JSON: {exc}"
            ) from exc

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map the export document to schema-shaped ``network`` finding fragments.

        As a side effect, sets :attr:`topology` to the schema-shaped
        top-level ``network_topology`` object (``segments`` and
        ``segment_reachability``, taken from the export verbatim — this
        connector never invents a segment or a reachability edge the export
        did not report).

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            Two fragments per instance (one ``host:<private_ip>``, one
            ``cloud:<instance ARN>``) — see the module docstring — each
            ``{"network": {"internet_facing": bool, "segment_id": str}}``
            plus a private ``_identity_hint``. An instance missing a private
            IP, a segment id, or an ARN is skipped for that one identity
            scheme only (not an error: an instance can still be known by
            whichever identifiers it does have).

        Must never:
            Fabricate ``segments``/``segment_reachability`` beyond what the
            export reported, or mark an instance ``internet_facing`` the
            export did not compute.
        """
        if not isinstance(raw, dict):
            raise NetworkTopologyConnectorError(
                f"{self.name}: expected a topology export object, got {type(raw).__name__}"
            )

        path = Path("<in-memory>")  # only used in error text below; fetch() already read the file
        segments = raw.get("segments")
        segment_reachability = raw.get("segment_reachability")
        if not isinstance(segments, list) or not isinstance(segment_reachability, list):
            raise NetworkTopologyConnectorError(
                f"{self.name}: export has no 'segments'/'segment_reachability' list"
            )
        self.topology = {"segments": segments, "segment_reachability": segment_reachability}

        instances = raw.get("instances")
        if not isinstance(instances, list):
            raise NetworkTopologyConnectorError(f"{self.name}: export has no 'instances' list")

        fragments: list[dict[str, Any]] = []
        for instance in instances:
            if not isinstance(instance, dict):
                raise NetworkTopologyConnectorError(
                    f"{self.name}: expected each instance entry to be an object, "
                    f"got {type(instance).__name__}"
                )
            instance_id = _require_str(instance, "instance_id", self.name, path)
            segment_id = instance.get("segment_id")
            internet_facing = instance.get("internet_facing")
            if not isinstance(segment_id, str) or not isinstance(internet_facing, bool):
                raise NetworkTopologyConnectorError(
                    f"{self.name}: instance {instance_id} has no segment_id/internet_facing"
                )
            network = {"internet_facing": internet_facing, "segment_id": segment_id}

            private_ip = instance.get("private_ip")
            if private_ip:
                fragments.append(
                    {"network": network, "_identity_hint": {"kind": "host", "value": private_ip}}
                )
            instance_arn = instance.get("instance_arn")
            if instance_arn:
                fragments.append(
                    {
                        "network": network,
                        "_identity_hint": {"kind": "cloud_resource", "value": instance_arn.lower()},
                    }
                )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a fragment to the same placeholder scheme its identity kind matches.

        Args:
            normalized_fragment: One normalized fragment.

        Returns:
            ``f"host:{value}"`` or ``f"cloud:{value}"`` — the exact same
            schemes ``wazuh_connector.py``/``greenbone_connector.py`` and
            ``prowler_connector.py``/``scoutsuite_connector.py`` already use,
            deliberately, so this connector's facts land on the same
            (duplicate) asset entries those connectors create rather than
            minting a third identity for the same machine.
        """
        hint = normalized_fragment["_identity_hint"]
        prefix = "host" if hint["kind"] == "host" else "cloud"
        value: str = hint["value"]
        return f"{prefix}:{value}"
