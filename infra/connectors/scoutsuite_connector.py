"""Connector for ScoutSuite cloud security posture (CSPM) scan output.

Normalizes ScoutSuite finding output into
``schema/aggregated_assets.schema.json`` ``assets[].findings`` entries of
``type: "misconfiguration"``. ScoutSuite's ``danger``/``warning`` finding
level must be mapped explicitly to the schema's criticality vocabulary.

ScoutSuite already ran as a one-shot CLI scan in CI and pushed its raw
output to S3 out-of-band (see ``infra/connectors/_object_store.py``); this
connector's :meth:`ScoutSuiteConnector.fetch` only reads that latest
object — it never calls a live ScoutSuite process or API itself.
ScoutSuite's own report file is JS-wrapped
(``scoutsuite_results = {...};``) rather than plain JSON, so ``fetch()``
reads it as text via
:func:`infra.connectors._object_store.read_latest_text` and unwraps it
itself rather than using :func:`infra.connectors._object_store.read_latest`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from infra.connectors import _object_store
from infra.connectors.base import Connector

#: How old the latest ScoutSuite S3 object may be before this connector
#: treats it as unreachable rather than trusting stale scan results.
#: Operational freshness check (ScoutSuite runs on its own CI cadence), not
#: a FAIR modelling constant.
STALENESS_THRESHOLD_SECONDS: int = 24 * 60 * 60

#: Direct rename of ScoutSuite's own ``level`` vocabulary into the schema's
#: criticality vocabulary. This is *not* a FAIR judgement call — it is a
#: 1:1 vocabulary translation local to this connector (same reasoning as
#: ``PROWLER_SEVERITY_TO_CRITICALITY`` in ``prowler_connector.py``).
#: ScoutSuite findings with no level (or a level of "good"/"help") are not
#: actionable findings and are skipped rather than mapped.
SCOUTSUITE_LEVEL_TO_CRITICALITY: dict[str, str] = {
    "danger": "high",
    "warning": "medium",
}

#: Matches ScoutSuite's ``scoutsuite_results = {...};`` JS-variable wrapper
#: around its JSON report body. Operational parsing detail, not a
#: modelling constant.
_JS_WRAPPER_RE = re.compile(r"^\s*scoutsuite_results\s*=\s*(?P<body>.*);\s*$", re.DOTALL)

#: ScoutSuite's own timestamp format for ``last_run.time``, e.g.
#: ``"2026-09-19 00:00:00+0000"``. Operational parsing detail.
_LAST_RUN_TIME_FORMAT = "%Y-%m-%d %H:%M:%S%z"


class ScoutSuiteConnectorError(RuntimeError):
    """Raised when this connector cannot read or make sense of ScoutSuite's
    latest raw output.

    Always names the underlying cause — a missing/stale S3 object (wrapping
    :class:`infra.connectors._object_store.ObjectStoreError`), a malformed
    JS wrapper, or a report body that does not match this connector's
    assumed native-JSON shape.
    """


def _last_run_time_to_iso8601(value: Any) -> str | None:
    """Best-effort normalize ScoutSuite's ``last_run.time`` to ISO-8601.

    Returns the value unchanged if it does not match ScoutSuite's own
    ``"%Y-%m-%d %H:%M:%S%z"`` format, rather than fabricating or discarding
    it — a connector must never invent a timestamp it wasn't given.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        # _LAST_RUN_TIME_FORMAT does include %z; ruff's DTZ007 can't see
        # through the module-level constant to confirm that statically.
        parsed = datetime.strptime(value, _LAST_RUN_TIME_FORMAT)  # noqa: DTZ007
    except ValueError:
        return value
    return parsed.isoformat()


class ScoutSuiteConnector(Connector):
    """Fetches and normalizes ScoutSuite CSPM finding output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "scoutsuite_connector"

    def fetch(self) -> Any:
        """Read ScoutSuite's latest raw report from S3 and unwrap its JS variable.

        Returns:
            The parsed JSON body of ScoutSuite's report (a dict), with the
            ``scoutsuite_results = ...;`` wrapper stripped — parsed but
            untransformed.

        Raises:
            ScoutSuiteConnectorError: If the object store has no bucket
                configured, the ``latest/scoutsuite_connector.json`` object
                is missing/unreadable/stale, the text does not match the
                expected JS-wrapper format, or the wrapped body is not
                valid JSON. Must not return an empty result to mean "could
                not fetch".
        """
        try:
            text = _object_store.read_latest_text(self.name, STALENESS_THRESHOLD_SECONDS)
        except _object_store.ObjectStoreError as exc:
            raise ScoutSuiteConnectorError(
                f"{self.name}: could not read latest ScoutSuite output: {exc}"
            ) from exc

        match = _JS_WRAPPER_RE.match(text)
        if match is None:
            raise ScoutSuiteConnectorError(
                f"{self.name}: latest output is not in the expected "
                "'scoutsuite_results = {...};' JS-wrapped format"
            )

        try:
            body: Any = json.loads(match.group("body"))
        except json.JSONDecodeError as exc:
            raise ScoutSuiteConnectorError(
                f"{self.name}: ScoutSuite report body is not valid JSON: {exc}"
            ) from exc
        return body

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map ScoutSuite findings to schema-shaped finding fragments.

        Assumed ScoutSuite native-JSON shape (adjust if the real CI output
        differs)::

            {
              "last_run": {"time": "2026-09-19 00:00:00+0000", ...},
              "services": {
                "<service_name>": {
                  "findings": {
                    "<finding_key>": {
                      "level": "danger" | "warning" | ...,
                      "items": ["<dotted resource path/UID>", ...]
                    },
                    ...
                  }
                },
                ...
              }
            }

        ScoutSuite reports are point-in-time (there is no per-finding
        "first observed" field), so every finding's ``first_seen_at`` is
        this scan run's own ``last_run.time`` — the actual time this run
        observed the finding, never a fabricated value. One fragment is
        emitted per affected item, since each item is independently
        resolved to an asset.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].findings[]``, restricted to
            findings with a recognized ``level``
            (:data:`SCOUTSUITE_LEVEL_TO_CRITICALITY`), with
            ``provenance.connector`` set to ``"scoutsuite_connector"`` and
            ``provenance.raw_source_id`` set to the finding key. Each
            fragment also carries a private ``_identity_hint`` bridging key
            (see ``wazuh_connector.py``'s ``normalize`` docstring for why
            this placeholder exists pending a real CMDB connector).

        Must never:
            Emit a finding for a non-danger/warning level, or fabricate a
            ``first_seen_at`` when ScoutSuite reported no ``last_run.time``.
        """
        if not isinstance(raw, dict):
            raise ScoutSuiteConnectorError(
                f"{self.name}: expected the ScoutSuite report to be an object, got {type(raw).__name__}"
            )

        last_run = raw.get("last_run")
        scan_time_raw = last_run.get("time") if isinstance(last_run, dict) else None
        first_seen_at = _last_run_time_to_iso8601(scan_time_raw)
        if not first_seen_at:
            raise ScoutSuiteConnectorError(
                f"{self.name}: report has no last_run.time; refusing to fabricate first_seen_at"
            )

        services = raw.get("services")
        if not isinstance(services, dict):
            raise ScoutSuiteConnectorError(f"{self.name}: report has no 'services' object")

        fragments: list[dict[str, Any]] = []
        for service_data in services.values():
            if not isinstance(service_data, dict):
                continue
            findings = service_data.get("findings")
            if not isinstance(findings, dict):
                continue

            for finding_key, finding_data in findings.items():
                if not isinstance(finding_data, dict):
                    continue

                level = finding_data.get("level")
                criticality = SCOUTSUITE_LEVEL_TO_CRITICALITY.get(str(level)) if level else None
                if criticality is None:
                    # Not a danger/warning finding (e.g. an informational
                    # "good"/"help" entry) — not an actionable finding.
                    continue

                items = finding_data.get("items")
                if not isinstance(items, list):
                    raise ScoutSuiteConnectorError(
                        f"{self.name}: finding {finding_key} has a non-list 'items'"
                    )

                for item in items:
                    if not isinstance(item, str) or not item:
                        raise ScoutSuiteConnectorError(
                            f"{self.name}: finding {finding_key} has a non-string item; "
                            "cannot resolve asset identity"
                        )

                    fragments.append(
                        {
                            "findings": [
                                {
                                    "finding_id": f"scoutsuite-{finding_key}-{item}",
                                    "type": "misconfiguration",
                                    "cve_id": None,
                                    "epss_score": None,
                                    "kev_listed": None,
                                    "criticality": criticality,
                                    "provenance": {
                                        "connector": self.name,
                                        "raw_source_id": finding_key,
                                    },
                                    "first_seen_at": first_seen_at,
                                    "remediated_at": None,
                                }
                            ],
                            "_identity_hint": {
                                "kind": "cloud_resource",
                                "value": item.lower(),
                            },
                        }
                    )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a cloud resource path/UID to a stable asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            ``f"cloud:{value}"``, using the ``_identity_hint`` value set by
            :meth:`normalize` — a placeholder identity scheme pending a
            real ``cmdb_connector.py`` implementation.
        """
        value: str = normalized_fragment["_identity_hint"]["value"]
        return f"cloud:{value}"
