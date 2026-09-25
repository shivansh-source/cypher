"""Build the Wazuh bundle file ``wazuh_connector.py`` reads via ``WAZUH_EXPORT_PATH``.

A manager-only Wazuh deployment has no indexer, so the connector cannot query
alerts or the agent API. Instead an operator collects two files from the
manager and this script joins them::

    # on the manager (sudo needed to read the alerts file)
    sudo cat /var/ossec/logs/alerts/alerts.json > wazuh-alerts.json
    sudo /var/ossec/bin/agent_control -l        > agent-list.txt

    # anywhere
    python -m infra.inventory.build_wazuh_bundle \\
        --alerts wazuh-alerts.json --agents agent-list.txt > wazuh_bundle.json

The bundle has the shape ``WazuhConnector.fetch`` returns: ``agents`` (each
``{"agent": {id, name, ip, status}, "packages": [], "ports": []}``) and
``alerts`` (each raw alert wrapped as ``{"_source": alert}``, the shape an
indexer hit has). Syscollector packages/ports are not collected; the
connector does not read them.

Agent *status* comes only from ``agent_control``; the alerts file does not
carry it, and this script never infers it from alert activity.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

#: One line of ``agent_control -l``, e.g.
#: ``   ID: 001, Name: ip-10-20-1-97, IP: 10.20.1.97, Active`` or
#: ``   ID: 000, Name: ip-10-20-1-56 (server), IP: 127.0.0.1, Active/Local``.
_AGENT_LINE = re.compile(
    r"ID:\s*(?P<id>\d+),\s*Name:\s*(?P<name>.+?)(?:\s*\(server\))?,\s*"
    r"IP:\s*(?P<ip>[^,]+),\s*(?P<status>.+?)\s*$"
)

#: ``agent_control`` reports these as the IP of an agent with no fixed
#: address, or of the manager itself. Neither is a usable host identity.
_NON_IDENTITY_IPS = ("any", "127.0.0.1", "::1")


def parse_agent_control_list(text: str) -> list[dict[str, Any]]:
    """Parse ``agent_control -l`` output into agent records.

    Args:
        text: The command's plain-text output.

    Returns:
        One ``{"id", "name", "ip", "status"}`` dict per agent line. ``status``
        is lowercased and cut at any ``/`` (``Active/Local`` -> ``active``),
        matching the manager API's vocabulary that ``WazuhConnector`` expects.
        ``ip`` is ``None`` for ``any`` / loopback, so the connector falls back
        to the agent name rather than minting ``host:127.0.0.1``.

    Raises:
        ValueError: If no agent line is found at all (wrong file, or the
            command failed) — never an empty list meaning "no agents".
    """
    agents: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = _AGENT_LINE.search(line)
        if not match:
            continue
        ip = match["ip"].strip()
        agents.append(
            {
                "id": match["id"],
                "name": match["name"].strip(),
                "ip": None if ip.lower() in _NON_IDENTITY_IPS else ip,
                "status": match["status"].split("/")[0].strip().lower(),
            }
        )
    if not agents:
        raise ValueError("no 'ID: ..., Name: ..., IP: ..., <status>' lines found in agent list")
    return agents


def build_bundle(alerts_ndjson: str, agent_list_text: str) -> dict[str, Any]:
    """Join an alerts file and an agent list into a connector bundle.

    Args:
        alerts_ndjson: Contents of ``alerts.json`` (one JSON alert per line).
        agent_list_text: Output of ``agent_control -l``.

    Returns:
        ``{"agents": [...], "alerts": [...]}`` as described in the module
        docstring.

    Raises:
        ValueError: On an unparseable alert line or an empty agent list.
    """
    alerts: list[dict[str, Any]] = []
    for number, line in enumerate(alerts_ndjson.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            alerts.append({"_source": json.loads(line)})
        except json.JSONDecodeError as exc:
            raise ValueError(f"alerts line {number} is not valid JSON: {exc}") from exc

    observed_ips = _observed_agent_ips(alerts)
    agents = []
    for agent in parse_agent_control_list(agent_list_text):
        if agent["ip"] is None:
            agent["ip"] = observed_ips.get(agent["id"])
        agents.append({"agent": agent, "packages": [], "ports": []})
    return {"agents": agents, "alerts": alerts}


def _observed_agent_ips(alerts: list[dict[str, Any]]) -> dict[str, str]:
    """Each agent id's IP as Wazuh itself reported it in that agent's alerts.

    ``agent_control -l`` prints ``any`` for agents that enrolled without a fixed address, yet
    their alerts carry the address the manager saw. Used only to fill an otherwise unusable IP,
    and only when every alert for that agent agrees on exactly one address; an agent whose
    alerts name several addresses (or none) gets no IP rather than a guess.
    """
    seen: dict[str, set[str]] = {}
    for alert in alerts:
        agent = alert["_source"].get("agent") or {}
        agent_id, ip = agent.get("id"), agent.get("ip")
        if agent_id and ip:
            seen.setdefault(str(agent_id), set()).add(str(ip))
    return {agent_id: next(iter(ips)) for agent_id, ips in seen.items() if len(ips) == 1}


def main(argv: list[str] | None = None) -> None:
    """Write the bundle JSON for ``--alerts`` and ``--agents`` to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alerts", required=True, type=Path)
    parser.add_argument("--agents", required=True, type=Path)
    args = parser.parse_args(argv)

    bundle = build_bundle(
        args.alerts.read_text(encoding="utf-8"), args.agents.read_text(encoding="utf-8")
    )
    json.dump(bundle, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
