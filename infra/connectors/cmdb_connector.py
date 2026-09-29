"""Connector for the organization's CMDB (configuration management database).

This connector is the canonical source of asset identity for the whole
system (see ``infra/README.md``): every identifier CMDB has on file for an
asset — hostnames, IP addresses, cloud instance ids — is normalized here
into ``schema/aggregated_assets.schema.json`` ``endpoints[]`` entries, each
carrying ``resolved_asset_id`` set to that asset's canonical
``cmdb:<id>`` id. ``infra/connectors/_identity_resolution.py`` (never
imported from here — see its own docstring on why) later matches these
``endpoints[]`` entries against the placeholder ``host:``/``cloud:`` asset
ids the other implemented connectors mint, as the evidence side of a
Jev-assisted merge decision made in ``interfaces/cli/cypher.py``.

Unlike every other connector in this package, this one needs no
``_identity_hint`` bridging convention and no placeholder id scheme: CMDB
*is* this system's identity authority, so :meth:`CMDBConnector.resolve_asset_id`
can compute the final ``asset_id`` directly at normalize time, with nothing
left to resolve against another source.

Scope note: CMDB records also carry service/ownership data
(``schema/aggregated_assets.schema.json``'s ``services[]``), which this
connector does not yet normalize. ``services[]`` entries are keyed by
``service_id``, not ``asset_id`` — they do not fit ``base.py``'s
fetch -> normalize -> attach-one-asset-id-per-fragment contract at all, and
resolving that mismatch is a distinct, already-flagged open question (see
``schema/README.md``'s TODO on where service financial attributes belong),
not part of identity resolution. Left as a documented gap rather than
folded into this pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from infra.connectors import _env
from infra.connectors.base import Connector

#: Request timeout (seconds) for the CMDB REST API. Operational transport
#: setting, not a modelling constant — mirrors wazuh_connector.py's own
#: request timeout handling.
_REQUEST_TIMEOUT_SECONDS: int = 30

_CMDB_BASE_URL_ENV = "CMDB_BASE_URL"
_CMDB_API_TOKEN_ENV = "CMDB_API_TOKEN"
_CMDB_EXPORT_PATH_ENV = "CMDB_EXPORT_PATH"

#: CMDB's own identifier-list field names -> the identifier kind used
#: throughout infra/connectors/_identity_resolution.py and this connector's
#: endpoints[] output. A direct rename, not a judgement call (same
#: reasoning as GVM_THREAT_TO_CRITICALITY in greenbone_connector.py), so it
#: stays here rather than in core/assumptions.py.
_CMDB_FIELD_TO_IDENTIFIER_KIND: dict[str, str] = {
    "hostnames": "host",
    "ip_addresses": "ip",
    "cloud_instance_ids": "cloud",
}

#: Identifier kind -> the schema's endpoints[].address_type vocabulary.
#: schema/aggregated_assets.schema.json's own description gives
#: "ipv4"/"ipv6"/"hostname"/"url" as examples, not an exhaustive enum;
#: "cloud_instance_id" is an explicit, documented extension for identifiers
#: nmap/DNS-style tooling wouldn't otherwise represent. IPv4 vs IPv6 is not
#: distinguished — a documented simplification, not a claim that CMDB never
#: records IPv6.
_IDENTIFIER_KIND_TO_ADDRESS_TYPE: dict[str, str] = {
    "host": "hostname",
    "ip": "ipv4",
    "cloud": "cloud_instance_id",
}


class CMDBConnectorError(RuntimeError):
    """Raised when this connector cannot reach, authenticate against, or
    make sense of the CMDB's REST API.

    Always names the CMDB base URL involved.
    """


class CMDBConnector(Connector):
    """Fetches and normalizes CMDB asset-identity records.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey. See this module's docstring
    for why this connector's output is ``endpoints[]`` fragments, not
    ``assets[]`` fragments like every other implemented connector.
    """

    name: str = "cmdb_connector"

    def fetch(self) -> Any:
        """Retrieve raw asset-identity records, from an export file or the CMDB's REST API.

        If ``CMDB_EXPORT_PATH`` is set, reads that JSON file (an operator-
        produced inventory export, e.g. ``infra/inventory/export_ec2_inventory.py``;
        the same "operator provides the file" pattern as ``iam_connector.py``).
        Otherwise calls ``GET {CMDB_BASE_URL}/assets`` with a bearer token.
        Either way the expected shape (this connector's own contract with its
        source, not a schema-governed one) is a JSON list of objects, each
        with an ``id`` (the source's own stable identifier), and optionally
        ``hostnames``, ``ip_addresses``, ``cloud_instance_ids`` — each a
        list of strings.

        Returns:
            The parsed JSON list of raw asset records, untransformed.

        Raises:
            CMDBConnectorError: If a required environment variable is
                missing, the file or request cannot be read, or the payload
                is not a JSON list. Must not return an empty result to mean
                "could not fetch".
        """
        export_path = _env.get_optional(_CMDB_EXPORT_PATH_ENV)
        if export_path:
            return self._read_export(Path(export_path))

        base_url = _env.require(_CMDB_BASE_URL_ENV, self.name, CMDBConnectorError)
        token = _env.require(_CMDB_API_TOKEN_ENV, self.name, CMDBConnectorError)

        try:
            response = requests.get(
                f"{base_url.rstrip('/')}/assets",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CMDBConnectorError(f"{self.name}: request to {base_url} failed: {exc}") from exc

        if not response.ok:
            raise CMDBConnectorError(
                f"{self.name}: {base_url} returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            records = response.json()
        except ValueError as exc:
            raise CMDBConnectorError(
                f"{self.name}: {base_url} did not return valid JSON: {exc}"
            ) from exc
        if not isinstance(records, list):
            raise CMDBConnectorError(
                f"{self.name}: expected a JSON list of CMDB asset records, got {type(records).__name__}"
            )
        return records

    def _read_export(self, path: Path) -> Any:
        """Read and validate an inventory export file (see :meth:`fetch`)."""
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CMDBConnectorError(f"{self.name}: could not read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CMDBConnectorError(f"{self.name}: {path} is not valid JSON: {exc}") from exc
        if not isinstance(records, list):
            raise CMDBConnectorError(
                f"{self.name}: expected {path} to hold a JSON list of asset records, "
                f"got {type(records).__name__}"
            )
        return records

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map CMDB asset records to schema-shaped ``endpoints[]`` fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            One fragment per known identifier per CMDB asset record,
            matching ``endpoints[]`` (``endpoint_id``, ``address_type``,
            ``address``, ``resolved_asset_id``) — already fully resolved,
            since CMDB is this system's identity authority (see this
            module's docstring). An asset record with no known identifiers
            at all produces no fragments (nothing to merge against, and
            nothing schema-illegal to emit either).

        Must never:
            Emit an ``endpoints[]`` fragment with ``resolved_asset_id``
            null — every fragment here comes from CMDB's own record of a
            known asset, so it is resolved by construction.
        """
        if not isinstance(raw, list):
            raise CMDBConnectorError(
                f"{self.name}: expected a list of CMDB asset records, got {type(raw).__name__}"
            )

        fragments: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise CMDBConnectorError(
                    f"{self.name}: expected each CMDB asset record to be an object, "
                    f"got {type(record).__name__}"
                )
            cmdb_id = record.get("id")
            if not cmdb_id:
                raise CMDBConnectorError(f"{self.name}: a CMDB asset record is missing its id")
            canonical_asset_id = f"cmdb:{cmdb_id}"

            for cmdb_field, identifier_kind in _CMDB_FIELD_TO_IDENTIFIER_KIND.items():
                values = record.get(cmdb_field) or []
                for index, value in enumerate(values):
                    fragments.append(
                        {
                            "endpoint_id": f"cmdb-{cmdb_id}-{identifier_kind}-{index}",
                            "address_type": _IDENTIFIER_KIND_TO_ADDRESS_TYPE[identifier_kind],
                            "address": str(value).lower(),
                            "resolved_asset_id": canonical_asset_id,
                        }
                    )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Return the CMDB-canonical asset id already computed by :meth:`normalize`.

        Args:
            normalized_fragment: One ``endpoints[]``-shaped fragment from
                :meth:`normalize`.

        Returns:
            ``normalized_fragment["resolved_asset_id"]`` — unlike every
            other implemented connector, this is not a placeholder scheme
            awaiting later resolution; it is the final identity, because
            CMDB is the identity authority (see this module's docstring).
            The caller (``interfaces/cli/cypher.py``) reads
            ``resolved_asset_id``/``address_type``/``address``/
            ``endpoint_id`` directly to build ``endpoints[]`` entries and
            does not use the ``asset_id`` key :meth:`Connector.run` also
            attaches — it is harmless, redundant output for this
            connector, not a signal that these fragments belong in
            ``assets[]``.
        """
        value: str = normalized_fragment["resolved_asset_id"]
        return value
