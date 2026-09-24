"""Connector for Prowler cloud security posture (CSPM) scan output.

Normalizes Prowler check results (AWS/Azure/GCP misconfiguration findings)
into ``schema/aggregated_assets.schema.json`` ``assets[].findings`` entries
of ``type: "misconfiguration"``. Prowler's PASS/FAIL/WARNING/INFO status
model and per-check severity must be mapped explicitly to the schema's
criticality vocabulary.

Prowler already ran as a one-shot CLI scan in CI and pushed its raw output
to S3 out-of-band (see ``infra/connectors/_object_store.py``); this
connector's :meth:`ProwlerConnector.fetch` only reads that latest object —
it never calls a live Prowler process or API itself.
"""

from __future__ import annotations

from typing import Any

from infra.connectors import _object_store
from infra.connectors.base import Connector

#: How old the latest Prowler S3 object may be before this connector treats
#: it as unreachable rather than trusting stale scan results. Operational
#: freshness check (Prowler runs on its own CI cadence), not a FAIR
#: modelling constant.
STALENESS_THRESHOLD_SECONDS: int = 24 * 60 * 60

#: Direct rename of Prowler's own severity vocabulary into the schema's
#: criticality vocabulary. This is *not* a FAIR judgement call (no
#: resistance/likelihood modelling happens here) — it is a 1:1 vocabulary
#: translation local to this connector, so it stays here rather than in
#: ``core/assumptions.py``.
PROWLER_SEVERITY_TO_CRITICALITY: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "informational": "informational",
}

#: ``Compliance.Status`` value Prowler's ASFF output uses for an actual
#: finding. Everything else (``PASSED`` and any other status) is not a
#: finding and must be skipped.
_FAILING_STATUS: str = "FAILED"

#: Prefix Prowler puts on every ASFF ``GeneratorId`` (``prowler-<check id>``).
_GENERATOR_ID_PREFIX: str = "prowler-"


class ProwlerConnectorError(RuntimeError):
    """Raised when this connector cannot read or make sense of Prowler's
    latest raw output.

    Always names the underlying cause — a missing/stale S3 object (wrapping
    :class:`infra.connectors._object_store.ObjectStoreError`) or a Prowler
    finding that does not match this connector's expected ASFF shape.
    """


class ProwlerConnector(Connector):
    """Fetches and normalizes Prowler CSPM check output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "prowler_connector"

    def fetch(self) -> Any:
        """Read Prowler's latest raw scan output from S3.

        Returns:
            Parsed but untransformed per-check results across the scanned
            cloud accounts (a JSON list of ASFF finding dicts), exactly as
            pushed to S3 — i.e. the unmodified ``*.asff.json`` file
            ``prowler aws --output-formats json-asff`` writes.

        Raises:
            ProwlerConnectorError: If the object store has no bucket
                configured, the ``latest/prowler_connector.json`` object is
                missing/unreadable, or it is older than
                :data:`STALENESS_THRESHOLD_SECONDS`. Must not return an
                empty result to mean "could not fetch".
        """
        try:
            return _object_store.read_latest(self.name, STALENESS_THRESHOLD_SECONDS)
        except _object_store.ObjectStoreError as exc:
            raise ProwlerConnectorError(
                f"{self.name}: could not read latest Prowler output: {exc}"
            ) from exc

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map Prowler ASFF findings to schema-shaped finding fragments.

        Expected shape: Prowler 5.x ``json-asff`` output (verified against a
        real 5.43.0 file) — a top-level JSON list, each item an ASFF finding
        with:

        * ``GeneratorId`` (str) — ``"prowler-<check id>"``.
        * ``Compliance.Status`` (str) — ``"FAILED"`` marks a finding;
          ``"PASSED"`` (and anything else) is skipped.
        * ``Severity.Label`` (str) — ``CRITICAL``/``HIGH``/``MEDIUM``/
          ``LOW``/``INFORMATIONAL``, matched case-insensitively against
          :data:`PROWLER_SEVERITY_TO_CRITICALITY`.
        * ``Resources`` (list[dict]) — each with an ``"Id"`` holding the
          affected resource's ARN/id.
        * ``FirstObservedAt`` (str, ISO-8601 with ``Z``) — used as
          ``first_seen_at``.

        The ``json-ocsf`` output is deliberately not used: its
        ``finding_info.created_time_dt`` is a *naive local-time* string
        (observed 5.5h ahead of the UTC ``FirstObservedAt`` for the same
        finding), which would silently mis-date every finding.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].findings[]``, restricted to
            failed checks (a PASS is not a finding), with
            ``provenance.connector`` set to ``"prowler_connector"`` and
            ``provenance.raw_source_id`` set to the Prowler check ID. Each
            fragment also carries a private ``_identity_hint`` bridging key
            (see ``wazuh_connector.py``'s ``normalize`` docstring for why
            this placeholder exists pending a real CMDB connector) —
            stripped by :meth:`infra.connectors.base.Connector.run` before
            anything reaches a schema-shaped snapshot.

        Must never:
            Emit a finding for a PASSing check, leave ``criticality`` null
            when Prowler reported a severity for the check, or fabricate a
            ``first_seen_at`` timestamp when Prowler did not report one.
        """
        if not isinstance(raw, list):
            raise ProwlerConnectorError(
                f"{self.name}: expected a list of Prowler ASFF findings, got {type(raw).__name__}"
            )

        fragments: list[dict[str, Any]] = []
        for check in raw:
            if not isinstance(check, dict):
                raise ProwlerConnectorError(
                    f"{self.name}: expected each Prowler finding to be an object, got {type(check).__name__}"
                )

            status = (check.get("Compliance") or {}).get("Status")
            if status is None:
                raise ProwlerConnectorError(
                    f"{self.name}: finding {check.get('Id')!r} has no Compliance.Status"
                )
            if status != _FAILING_STATUS:
                continue

            generator_id = str(check.get("GeneratorId") or "")
            if not generator_id.startswith(_GENERATOR_ID_PREFIX) or generator_id == _GENERATOR_ID_PREFIX:
                raise ProwlerConnectorError(
                    f"{self.name}: a FAILED finding has an unusable GeneratorId {generator_id!r}"
                )
            check_id = generator_id[len(_GENERATOR_ID_PREFIX) :]

            severity = (check.get("Severity") or {}).get("Label")
            criticality = (
                PROWLER_SEVERITY_TO_CRITICALITY.get(str(severity).lower()) if severity else None
            )
            if criticality is None:
                raise ProwlerConnectorError(
                    f"{self.name}: check {check_id} has an unrecognized Severity.Label {severity!r}"
                )

            timestamp = check.get("FirstObservedAt")
            if not timestamp:
                raise ProwlerConnectorError(
                    f"{self.name}: check {check_id} has no FirstObservedAt; refusing to fabricate first_seen_at"
                )

            resources = check.get("Resources")
            if not isinstance(resources, list) or not resources:
                raise ProwlerConnectorError(
                    f"{self.name}: check {check_id} has no Resources; cannot resolve asset identity"
                )

            for resource in resources:
                resource_uid = resource.get("Id") if isinstance(resource, dict) else None
                if not resource_uid:
                    raise ProwlerConnectorError(
                        f"{self.name}: check {check_id} has a resource with no Id"
                    )

                fragments.append(
                    {
                        "findings": [
                            {
                                "finding_id": f"prowler-{check_id}-{resource_uid}",
                                "type": "misconfiguration",
                                "cve_id": None,
                                "epss_score": None,
                                "kev_listed": None,
                                "criticality": criticality,
                                "provenance": {
                                    "connector": self.name,
                                    "raw_source_id": check_id,
                                },
                                "first_seen_at": timestamp,
                                "remediated_at": None,
                            }
                        ],
                        "_identity_hint": {
                            "kind": "cloud_resource",
                            "value": str(resource_uid).lower(),
                        },
                    }
                )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a cloud resource ARN/resource-id to a stable asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            ``f"cloud:{value}"``, using the ``_identity_hint`` value set by
            :meth:`normalize` — a placeholder identity scheme pending a
            real ``cmdb_connector.py`` implementation.
        """
        value: str = normalized_fragment["_identity_hint"]["value"]
        return f"cloud:{value}"
