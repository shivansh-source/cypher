"""Connector for Wazuh EDR/SIEM agent and alert data.

Normalizes Wazuh agent status and alert output into
``schema/aggregated_assets.schema.json`` ``assets[].edr`` entries, and may
also emit ``assets[].findings`` for Wazuh's own vulnerability-detection
module (CVE findings from installed-package inventory) if that module is
enabled.

This connector talks to two live Wazuh services: the Wazuh manager API
(agent inventory, syscollector package/port data) and the Wazuh indexer
(recent alerts via ``_search``). Both must be reachable and reachable
credentials must authenticate, or :meth:`WazuhConnector.fetch` raises
:class:`WazuhConnectorError` naming the failing endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from infra.connectors import _env, _object_store
from infra.connectors.base import Connector

#: How far back to search the Wazuh indexer for alerts on each run. This is
#: an operational polling window (how much alert history each ingest cycle
#: looks at), not a FAIR modelling constant.
ALERT_LOOKBACK_HOURS: int = 24

#: HTTP timeout applied to every call against the Wazuh manager/indexer
#: APIs. Operational transport setting, not a modelling constant.
_REQUEST_TIMEOUT_SECONDS: int = 30

_WAZUH_API_URL_ENV = "WAZUH_API_URL"
_WAZUH_API_USERNAME_ENV = "WAZUH_API_USERNAME"
_WAZUH_API_PASSWORD_ENV = "WAZUH_API_PASSWORD"
_WAZUH_INDEXER_URL_ENV = "WAZUH_INDEXER_URL"
_WAZUH_INDEXER_USERNAME_ENV = "WAZUH_INDEXER_USERNAME"
_WAZUH_INDEXER_PASSWORD_ENV = "WAZUH_INDEXER_PASSWORD"


class WazuhConnectorError(RuntimeError):
    """Raised when a call to the Wazuh manager or indexer API fails.

    Always names the specific endpoint and, where available, the HTTP
    status code or the shape defect that caused the failure — never raised
    generically, so a caller can tell exactly which of the manager API or
    the indexer was unreachable.
    """


class WazuhConnector(Connector):
    """Fetches and normalizes Wazuh agent/alert data.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "wazuh_connector"

    def fetch(self) -> Any:
        """Retrieve raw agent status and recent alerts from the Wazuh API.

        Authenticates against the Wazuh manager API, lists agents, and for
        each agent retrieves its installed-package and open-port
        syscollector inventory. Separately queries the Wazuh indexer for
        alerts within :data:`ALERT_LOOKBACK_HOURS`.

        Returns:
            A dict ``{"agents": [{"agent": ..., "packages": [...],
            "ports": [...]}, ...], "alerts": [...]}`` — parsed but
            untransformed Wazuh-native records.

        Raises:
            WazuhConnectorError: If authentication fails, any manager/
                indexer endpoint is unreachable or returns a non-2xx
                status, or a response is missing the fields this method
                depends on. Must not return an empty result to mean
                "could not fetch".
        """
        api_url = _env.require(_WAZUH_API_URL_ENV, self.name, WazuhConnectorError)
        api_username = _env.require(_WAZUH_API_USERNAME_ENV, self.name, WazuhConnectorError)
        api_password = _env.require(_WAZUH_API_PASSWORD_ENV, self.name, WazuhConnectorError)
        indexer_url = _env.require(_WAZUH_INDEXER_URL_ENV, self.name, WazuhConnectorError)
        indexer_username = _env.require(_WAZUH_INDEXER_USERNAME_ENV, self.name, WazuhConnectorError)
        indexer_password = _env.require(_WAZUH_INDEXER_PASSWORD_ENV, self.name, WazuhConnectorError)

        token = self._authenticate(api_url, api_username, api_password)
        agents = self._get_agents(api_url, token)

        agents_raw: list[dict[str, Any]] = []
        for agent in agents:
            agent_id = agent.get("id")
            if not agent_id:
                raise WazuhConnectorError(
                    f"{self.name}: an agent record from {api_url}/agents has no 'id'"
                )
            packages = self._get_syscollector(api_url, token, str(agent_id), "packages")
            ports = self._get_syscollector(api_url, token, str(agent_id), "ports")
            agents_raw.append({"agent": agent, "packages": packages, "ports": ports})

        alerts = self._search_alerts(indexer_url, indexer_username, indexer_password)

        raw: dict[str, Any] = {"agents": agents_raw, "alerts": alerts}
        _object_store.write_raw(self.name, raw)
        return raw

    def _authenticate(self, api_url: str, username: str, password: str) -> str:
        """Authenticate against the Wazuh manager API and return a JWT.

        Raises:
            WazuhConnectorError: If the endpoint is unreachable, returns a
                non-2xx status, or the response does not contain the
                expected ``data.token`` field (the typical Wazuh API
                authentication response shape).
        """
        endpoint = f"{api_url}/security/user/authenticate"
        try:
            response = requests.post(
                endpoint, auth=(username, password), timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            raise WazuhConnectorError(f"{self.name}: could not reach {endpoint}: {exc}") from exc

        if not response.ok:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned HTTP {response.status_code}"
            )

        try:
            body: Any = response.json()
            token = body["data"]["token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned a malformed response (expected data.token): {exc}"
            ) from exc

        if not isinstance(token, str) or not token:
            raise WazuhConnectorError(f"{self.name}: {endpoint} returned a non-string/empty token")
        return token

    def _authenticated_get(self, endpoint: str, token: str) -> Any:
        """GET ``endpoint`` with a bearer token and return the parsed JSON body.

        Raises:
            WazuhConnectorError: If the endpoint is unreachable, returns a
                non-2xx status, or the response body is not valid JSON.
        """
        try:
            response = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise WazuhConnectorError(f"{self.name}: could not reach {endpoint}: {exc}") from exc

        if not response.ok:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned HTTP {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned a non-JSON response"
            ) from exc

    def _get_affected_items(self, endpoint: str, token: str) -> list[dict[str, Any]]:
        """GET ``endpoint`` and return its ``data.affected_items`` list.

        Shared by :meth:`_get_agents` and :meth:`_get_syscollector`, which
        both hit Wazuh manager API endpoints sharing this response envelope.

        Raises:
            WazuhConnectorError: If the response lacks ``data.affected_items``
                or that field is not a list.
        """
        data = self._authenticated_get(endpoint, token)
        try:
            items: Any = data["data"]["affected_items"]
        except (KeyError, TypeError) as exc:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned a malformed response (expected data.affected_items): {exc}"
            ) from exc

        if not isinstance(items, list):
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned a non-list data.affected_items"
            )
        return items

    def _get_agents(self, api_url: str, token: str) -> list[dict[str, Any]]:
        """GET the full agent inventory from the Wazuh manager API."""
        return self._get_affected_items(f"{api_url}/agents", token)

    def _get_syscollector(
        self, api_url: str, token: str, agent_id: str, resource: str
    ) -> list[dict[str, Any]]:
        """GET one syscollector resource (``packages`` or ``ports``) for an agent."""
        return self._get_affected_items(f"{api_url}/syscollector/{agent_id}/{resource}", token)

    def _search_alerts(
        self, indexer_url: str, username: str, password: str
    ) -> list[dict[str, Any]]:
        """POST a lookback-window ``_search`` query to the Wazuh indexer.

        Raises:
            WazuhConnectorError: If the indexer is unreachable, returns a
                non-2xx status, or the response lacks ``hits.hits``.
        """
        endpoint = f"{indexer_url}/wazuh-alerts-*/_search"
        lookback_start = (datetime.now(UTC) - timedelta(hours=ALERT_LOOKBACK_HOURS)).isoformat()
        query = {"query": {"range": {"timestamp": {"gte": lookback_start}}}}

        try:
            response = requests.post(
                endpoint,
                auth=(username, password),
                json=query,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise WazuhConnectorError(f"{self.name}: could not reach {endpoint}: {exc}") from exc

        if not response.ok:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned HTTP {response.status_code}"
            )

        try:
            body: Any = response.json()
            hits: Any = body["hits"]["hits"]
        except (ValueError, KeyError, TypeError) as exc:
            raise WazuhConnectorError(
                f"{self.name}: {endpoint} returned a malformed response (expected hits.hits): {exc}"
            ) from exc

        if not isinstance(hits, list):
            raise WazuhConnectorError(f"{self.name}: {endpoint} returned a non-list hits.hits")
        return hits

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map Wazuh agent/alert data to schema-shaped ``edr`` fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            One fragment per agent:
            ``{"edr": {"agent_installed": True, "agent_healthy": <bool>,
            "detection_rules_active": None, "recent_alerts": [...]},
            "_identity_hint": {"kind": "host", "value": "<agent ip or name,
            lowercased>"}}``.

            ``_identity_hint`` is a private, non-schema bridging key
            consumed only by :meth:`resolve_asset_id` — see
            :meth:`infra.connectors.base.Connector.run`, which strips every
            ``_``-prefixed key before anything is merged into a
            schema-shaped snapshot. It exists only because there is no
            CMDB connector implemented yet (``cmdb_connector.py`` is still
            a stub with its own unresolved TODO on identity keys); it is an
            explicitly-flagged placeholder pending real CMDB-based identity
            resolution, not a new identity scheme.

            This method does not attempt to derive CVE findings from the
            installed-package inventory fetched alongside agent data — that
            would require a real vulnerability-database lookup, which is
            out of scope here (``greenbone_connector.py`` already covers
            CVE findings for this deployment).

        Must never:
            Report ``agent_installed: true`` for a host with no
            corresponding Wazuh agent record, or infer ``agent_healthy``
            from anything other than the agent's actual reported status.
        """
        agents = raw.get("agents", []) if isinstance(raw, dict) else []
        alerts = raw.get("alerts", []) if isinstance(raw, dict) else []

        fragments: list[dict[str, Any]] = []
        for entry in agents:
            agent = entry.get("agent", {}) if isinstance(entry, dict) else {}
            agent_id = agent.get("id")
            status = agent.get("status")
            identity_source = agent.get("ip") or agent.get("name")
            if not identity_source:
                raise WazuhConnectorError(
                    f"{self.name}: agent {agent_id!r} has neither an ip nor a name; "
                    "cannot resolve identity"
                )
            identity_value = str(identity_source).lower()

            recent_alerts = [
                self._alert_summary(hit)
                for hit in alerts
                if isinstance(hit, dict)
                and hit.get("_source", {}).get("agent", {}).get("id") == agent_id
            ]

            fragments.append(
                {
                    "edr": {
                        "agent_installed": True,
                        "agent_healthy": status == "active",
                        "detection_rules_active": None,
                        "recent_alerts": recent_alerts,
                    },
                    "_identity_hint": {"kind": "host", "value": identity_value},
                }
            )
        return fragments

    @staticmethod
    def _alert_summary(hit: dict[str, Any]) -> dict[str, Any]:
        """Extract a small, schema-vocabulary-only summary of one alert hit."""
        source = hit.get("_source", {}) if isinstance(hit.get("_source"), dict) else {}
        rule = source.get("rule", {}) if isinstance(source.get("rule"), dict) else {}
        return {
            "rule_id": rule.get("id"),
            "description": rule.get("description"),
            "timestamp": source.get("timestamp"),
        }

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a Wazuh agent (by agent IP/name) to a stable asset_id.

        Args:
            normalized_fragment: One normalized fragment, carrying
                ``_identity_hint.value`` as produced by :meth:`normalize`.

        Returns:
            ``f"host:{value}"``, using the identity hint's value.

            This is a placeholder identity scheme pending a real
            ``cmdb_connector.py`` implementation (see :meth:`normalize`'s
            docstring) — not a permanent cross-connector identity contract.
        """
        value: str = normalized_fragment["_identity_hint"]["value"]
        return f"host:{value}"
