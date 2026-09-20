"""Connector for Greenbone (OpenVAS/GVM) vulnerability scan output.

Normalizes Greenbone GMP scan results into
``schema/aggregated_assets.schema.json`` ``assets[].findings`` entries of
``type: "cve"``. Greenbone's ``threat`` scale (High/Medium/Low/Log) must be
mapped explicitly to the schema's criticality vocabulary — see
``core/assumptions.py`` if that mapping ever requires a judgement call
rather than a direct rename.

In this deployment, Greenbone plays the role Nessus plays in
``nessus_connector.py`` elsewhere in the codebase (both populate
``assets[].findings`` with ``type: "cve"``) — only one of the two is
actually wired into ``interfaces/cli/riskctl.py``'s ``ingest_command`` for
now (see ``infra/README.md``).
"""

from __future__ import annotations

from typing import Any

from gvm.connections import TLSConnection
from gvm.protocols.gmp import Gmp
from gvm.transforms import EtreeCheckCommandTransform

from infra.connectors import _env, _object_store
from infra.connectors.base import Connector

#: Default GVM manager daemon port, used when ``GREENBONE_PORT`` is not set.
#: Operational transport default, not a modelling constant.
DEFAULT_GVM_PORT: int = 9390

#: TLS connection timeout (seconds) for the GVM manager. Operational
#: transport setting, not a modelling constant.
_CONNECTION_TIMEOUT_SECONDS: int = 60

_GREENBONE_HOST_ENV = "GREENBONE_HOST"
_GREENBONE_PORT_ENV = "GREENBONE_PORT"
_GREENBONE_USERNAME_ENV = "GREENBONE_USERNAME"
_GREENBONE_PASSWORD_ENV = "GREENBONE_PASSWORD"

#: Direct rename of GVM's own ``threat`` vocabulary into the schema's
#: criticality vocabulary. This is *not* a FAIR judgement call — it is a
#: 1:1 vocabulary translation local to this connector (same reasoning as
#: ``PROWLER_SEVERITY_TO_CRITICALITY`` in ``prowler_connector.py``), so it
#: stays here rather than in ``core/assumptions.py``.
GVM_THREAT_TO_CRITICALITY: dict[str, str] = {
    "High": "high",
    "Medium": "medium",
    "Low": "low",
    "Log": "informational",
}

#: GVM's own literal sentinel for "this NVT has no assigned CVE" — not a
#: real CVE identifier, so it must be normalized to ``None`` rather than
#: passed through as ``cve_id``.
_GVM_NO_CVE_SENTINEL: str = "NOCVE"


class GreenboneConnectorError(RuntimeError):
    """Raised when this connector cannot connect to, authenticate against,
    or query the Greenbone GVM manager, or cannot make sense of its
    response.

    Always names the host/port involved.
    """


def _element_text(element: Any) -> str | None:
    """Return an lxml element's text content, or ``None`` if the element is absent."""
    if element is None:
        return None
    text: str | None = element.text
    return text


def _results_to_dicts(results_root: Any) -> list[dict[str, Any]]:
    """Convert a ``get_results`` XML response into plain dicts.

    Preserves GVM's own field names (``host``, NVT ``oid``, ``name``,
    ``cvss`` via ``severity``, ``threat``, ``cve``, result ``id``) without
    renaming any vocabulary — that mapping belongs in
    :meth:`GreenboneConnector.normalize`, not here.
    """
    records: list[dict[str, Any]] = []
    for result in results_root.findall("result"):
        nvt = result.find("nvt")
        records.append(
            {
                "result_id": result.get("id"),
                "host": _element_text(result.find("host")),
                "name": _element_text(result.find("name")),
                "threat": _element_text(result.find("threat")),
                "severity": _element_text(result.find("severity")),
                "creation_time": _element_text(result.find("creation_time")),
                "nvt_oid": nvt.get("oid") if nvt is not None else None,
                "cve": _element_text(nvt.find("cve")) if nvt is not None else None,
            }
        )
    return records


class GreenboneConnector(Connector):
    """Fetches and normalizes Greenbone (OpenVAS/GVM) scan output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "greenbone_connector"

    def fetch(self) -> Any:
        """Connect to the Greenbone GVM manager and retrieve scan results.

        Connects via GMP-over-TLS to ``GREENBONE_HOST``/``GREENBONE_PORT``
        (defaulting to :data:`DEFAULT_GVM_PORT`), authenticates with
        ``GREENBONE_USERNAME``/``GREENBONE_PASSWORD``, and calls
        ``gmp.get_results()``.

        Returns:
            A list of plain dicts, one per GVM result, with GVM's own field
            names preserved (see :func:`_results_to_dicts`) — parsed but
            untransformed.

        Raises:
            GreenboneConnectorError: If a required environment variable is
                missing, the TLS connection cannot be opened, authentication
                fails, or the ``get_results`` request fails. Must not
                return an empty result to mean "could not fetch".
        """
        host = _env.require(_GREENBONE_HOST_ENV, self.name, GreenboneConnectorError)
        username = _env.require(_GREENBONE_USERNAME_ENV, self.name, GreenboneConnectorError)
        password = _env.require(_GREENBONE_PASSWORD_ENV, self.name, GreenboneConnectorError)
        port = int(_env.get_optional(_GREENBONE_PORT_ENV) or DEFAULT_GVM_PORT)

        try:
            connection = TLSConnection(
                hostname=host, port=port, timeout=_CONNECTION_TIMEOUT_SECONDS
            )
        except Exception as exc:
            raise GreenboneConnectorError(
                f"{self.name}: could not open a TLS connection to Greenbone GVM manager at {host}:{port}: {exc}"
            ) from exc

        try:
            # python-gvm's own EtreeCheckCommandTransform.__init__ carries no
            # type annotations (unlike the rest of the py.typed gvm package),
            # so mypy --strict flags this as an untyped call. Unavoidable
            # without vendoring a typed wrapper for one constructor call.
            transform = EtreeCheckCommandTransform()  # type: ignore[no-untyped-call]
            with Gmp(connection, transform=transform) as gmp:
                gmp.authenticate(username, password)
                results_root = gmp.get_results()
        except Exception as exc:
            raise GreenboneConnectorError(
                f"{self.name}: Greenbone GVM manager at {host}:{port} rejected authentication "
                f"or the get_results request: {exc}"
            ) from exc

        results = _results_to_dicts(results_root)
        _object_store.write_raw(self.name, results)
        return results

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map GVM result records to schema-shaped finding fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].findings[]`` (``type:
            "cve"``), with ``provenance.connector`` set to
            ``"greenbone_connector"`` and ``provenance.raw_source_id`` set
            to the NVT OID (or the result ID if no OID is present). Each
            fragment also carries a private ``_identity_hint`` bridging key
            (see ``wazuh_connector.py``'s ``normalize`` docstring for why
            this placeholder exists pending a real CMDB connector).

        Must never:
            Pass through GVM's High/Medium/Low/Log ``threat`` scale
            unmapped, or fabricate a ``first_seen_at``/``creation_time``
            when GVM did not report one.
        """
        if not isinstance(raw, list):
            raise GreenboneConnectorError(
                f"{self.name}: expected a list of Greenbone results, got {type(raw).__name__}"
            )

        fragments: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise GreenboneConnectorError(
                    f"{self.name}: expected each Greenbone result to be an object, got {type(record).__name__}"
                )

            result_id = record.get("result_id")
            if not result_id:
                raise GreenboneConnectorError(f"{self.name}: a result is missing its result id")

            threat = record.get("threat")
            if threat:
                criticality = GVM_THREAT_TO_CRITICALITY.get(str(threat))
                if criticality is None:
                    raise GreenboneConnectorError(
                        f"{self.name}: result {result_id} has an unrecognized threat {threat!r}"
                    )
            else:
                # GVM evaluated this result but assigned no threat level —
                # an explicit, legitimate "unknown", never a fabricated one.
                criticality = "unknown"

            host = record.get("host")
            if not host:
                raise GreenboneConnectorError(
                    f"{self.name}: result {result_id} has no host; cannot resolve asset identity"
                )

            creation_time = record.get("creation_time")
            if not creation_time:
                raise GreenboneConnectorError(
                    f"{self.name}: result {result_id} has no creation_time; "
                    "refusing to fabricate first_seen_at"
                )

            cve = record.get("cve") or None
            if cve == _GVM_NO_CVE_SENTINEL:
                cve = None
            raw_source_id = str(record.get("nvt_oid") or result_id)

            fragments.append(
                {
                    "findings": [
                        {
                            "finding_id": f"greenbone-{result_id}",
                            "type": "cve",
                            "cve_id": cve,
                            "epss_score": None,
                            "kev_listed": None,
                            "criticality": criticality,
                            "provenance": {
                                "connector": self.name,
                                "raw_source_id": raw_source_id,
                            },
                            "first_seen_at": creation_time,
                            "remediated_at": None,
                        }
                    ],
                    "_identity_hint": {"kind": "host", "value": str(host).lower()},
                }
            )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a Greenbone-scanned host (by IP/hostname) to a stable asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            ``f"host:{value}"``, using the ``_identity_hint`` value set by
            :meth:`normalize` — a placeholder identity scheme pending a
            real ``cmdb_connector.py`` implementation.
        """
        value: str = normalized_fragment["_identity_hint"]["value"]
        return f"host:{value}"
