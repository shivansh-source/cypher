"""Connector for AWS IAM posture, via PMapper (nccgroup's principalmapper).

Reads the JSON that ``pmapper analysis --output-type json`` writes and
normalizes each PMapper finding into a
``schema/aggregated_assets.schema.json`` ``assets[].findings`` entry of
``type: "misconfiguration"``, attached to a single account-level asset.

PMapper's ``findings[].description`` names affected principals only as
free-text bullet lines (``* user/tf-bootstrap``), not as a structured field,
and its format across finding categories is unverified. This connector
therefore deliberately does *not* parse principals out of it: every finding
belongs to the account asset, and per-principal resolution is a documented
gap. For the same reason it does not populate ``assets[].identity_access``
(``privileged_accounts_count`` / ``mfa_enforced``) — PMapper's MFA finding
covers admin users only, so deriving an account-wide boolean from it would be
a guess, not an observation.

Like ``prowler_connector.py``, this connector never runs the tool itself: it
reads a file the operator produced. The path comes from
``IAM_PMAPPER_OUTPUT_PATH``. It does not call
``_object_store.write_raw`` — that helper needs ``RAW_FINDINGS_BUCKET``,
which is blank in ``.env.example`` and not confirmed provisioned, and the
input file is itself the audit artifact.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from infra.connectors import _env
from infra.connectors.base import Connector

_PMAPPER_OUTPUT_PATH_ENV = "IAM_PMAPPER_OUTPUT_PATH"

#: Direct rename of PMapper's own severity vocabulary (matched
#: case-insensitively) into the schema's criticality vocabulary. A 1:1
#: vocabulary translation local to this connector, not a FAIR judgement
#: call — same reasoning as ``PROWLER_SEVERITY_TO_CRITICALITY``.
PMAPPER_SEVERITY_TO_CRITICALITY: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "informational": "informational",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class IAMConnectorError(RuntimeError):
    """Raised when this connector cannot read or make sense of PMapper's output.

    Always names the file path or the missing/invalid key involved.
    """


def _slug(text: str) -> str:
    """Lowercase ``text`` and collapse every non-alphanumeric run to one hyphen."""
    return _SLUG_STRIP.sub("-", text.lower()).strip("-")


def _as_iso_utc(value: str) -> str:
    """Validate a PMapper timestamp and return it as a timezone-aware ISO-8601 string.

    A naive timestamp is interpreted as UTC. That is an assumption, not
    something PMapper's output states — revisit it against a real
    ``date_and_time`` value.

    Raises:
        ValueError: If ``value`` is not an ISO-8601 datetime.
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


class IAMConnector(Connector):
    """Fetches and normalizes PMapper IAM analysis output.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "iam_connector"

    def fetch(self) -> Any:
        """Read the PMapper JSON file named by ``IAM_PMAPPER_OUTPUT_PATH``.

        Returns:
            The parsed, untransformed PMapper document
            (``{"account": ..., "date_and_time": ..., "findings": [...], ...}``).

        Raises:
            IAMConnectorError: If the environment variable is unset, or the
                file is missing, unreadable, or not valid JSON. Must not
                return an empty result to mean "could not fetch".
        """
        path = Path(_env.require(_PMAPPER_OUTPUT_PATH_ENV, self.name, IAMConnectorError))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise IAMConnectorError(f"{self.name}: could not read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise IAMConnectorError(f"{self.name}: {path} is not valid JSON: {exc}") from exc

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map PMapper findings to schema-shaped finding fragments.

        Expected top-level keys are ``account`` and ``date_and_time`` (the
        underscore spelling seen in real output; PMapper's source suggests
        other spellings in other versions, which this method rejects
        explicitly rather than guessing).

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            One fragment per PMapper finding, each a ``findings`` list of one
            entry with ``finding_id = "pmapper-<slug of title>"``,
            ``provenance.raw_source_id = <slug of title>`` (PMapper's
            closest analogue to a check id — it has no per-finding id),
            ``criticality`` from ``severity``, and ``first_seen_at`` from the
            top-level ``date_and_time``. Each fragment carries a private
            ``_identity_hint`` for :meth:`resolve_asset_id`.

        Raises:
            IAMConnectorError: On a missing top-level key, a finding without
                a usable ``title``, an unrecognized ``severity``, an
                unparseable timestamp, or two findings with the same title.

        Must never:
            Invent a ``raw_source_id`` (UUID, counter, or hash) when
            ``title`` is missing, parse principals out of ``description``,
            or leave ``criticality`` null.
        """
        if not isinstance(raw, dict):
            raise IAMConnectorError(
                f"{self.name}: expected a PMapper JSON object, got {type(raw).__name__}"
            )
        for key in ("account", "date_and_time", "findings"):
            if key not in raw:
                raise IAMConnectorError(
                    f"{self.name}: PMapper output is missing top-level key {key!r} "
                    f"(found {sorted(raw)}); a different PMapper version may use other key names"
                )

        account = str(raw["account"])
        if not account:
            raise IAMConnectorError(f"{self.name}: PMapper 'account' is empty")
        try:
            first_seen_at = _as_iso_utc(str(raw["date_and_time"]))
        except ValueError as exc:
            raise IAMConnectorError(
                f"{self.name}: unparseable date_and_time {raw['date_and_time']!r}: {exc}"
            ) from exc

        findings = raw["findings"]
        if not isinstance(findings, list):
            raise IAMConnectorError(
                f"{self.name}: expected 'findings' to be a list, got {type(findings).__name__}"
            )

        fragments: list[dict[str, Any]] = []
        seen: set[str] = set()
        for finding in findings:
            if not isinstance(finding, dict):
                raise IAMConnectorError(
                    f"{self.name}: expected each finding to be an object, got {type(finding).__name__}"
                )

            title = finding.get("title")
            raw_source_id = _slug(str(title)) if title else ""
            if not raw_source_id:
                raise IAMConnectorError(
                    f"{self.name}: a PMapper finding has no usable 'title'; "
                    "refusing to invent a raw_source_id"
                )
            if raw_source_id in seen:
                raise IAMConnectorError(
                    f"{self.name}: two PMapper findings share the title {title!r}; "
                    "finding_id would collide"
                )
            seen.add(raw_source_id)

            severity = finding.get("severity")
            if severity:
                criticality = PMAPPER_SEVERITY_TO_CRITICALITY.get(str(severity).lower())
                if criticality is None:
                    raise IAMConnectorError(
                        f"{self.name}: finding {raw_source_id!r} has an unrecognized "
                        f"severity {severity!r}"
                    )
            else:
                # PMapper reported the finding without a severity — an
                # explicit "unknown", never a fabricated one.
                criticality = "unknown"

            fragments.append(
                {
                    "findings": [
                        {
                            "finding_id": f"pmapper-{raw_source_id}",
                            "type": "misconfiguration",
                            "cve_id": None,
                            "epss_score": None,
                            "kev_listed": None,
                            "criticality": criticality,
                            "provenance": {
                                "connector": self.name,
                                "raw_source_id": raw_source_id,
                            },
                            "first_seen_at": first_seen_at,
                            "remediated_at": None,
                        }
                    ],
                    "_identity_hint": {"kind": "cloud_account", "value": account},
                }
            )
        return fragments

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a PMapper fragment to its account-level asset_id.

        Args:
            normalized_fragment: One normalized finding fragment.

        Returns:
            ``f"cloud:aws-account:{account}"``, from the ``_identity_hint``
            set by :meth:`normalize` — a placeholder identity scheme pending
            real CMDB-based resolution, same status as ``prowler_connector.py``'s
            ``cloud:<arn>`` scheme.
        """
        value: str = normalized_fragment["_identity_hint"]["value"]
        return f"cloud:aws-account:{value}"
