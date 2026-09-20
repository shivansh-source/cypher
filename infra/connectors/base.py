"""Abstract base contract every connector must implement.

A connector's entire job is three steps, always in this order:

1. **Fetch** raw output from a specific security tool (API call, file
   export, CLI invocation — whatever that tool requires).
2. **Normalize** that raw output into the shape defined by
   ``schema/aggregated_assets.schema.json``. This is where all
   tool-specific knowledge must live and die. No field name, severity
   scale, or identifier format specific to the source tool may leak past
   this step.
3. **Attach** each normalized record to a resolved ``asset_id``, so that
   records from different tools describing the same real-world asset merge
   under one identity in the aggregated snapshot.

Emitting a shape other than ``schema/aggregated_assets.schema.json`` is the
one unforgivable error a connector can make. Every consumer downstream —
the quality gates in ``core/snapshot.py``, the engine in ``core/engine.py``,
the mapper in ``governance/mapper.py`` — trusts that the schema is the only
shape it will ever see and has no fallback for anything else.
"""

from __future__ import annotations

import abc
from typing import Any


class Connector(abc.ABC):
    """Base class for all connectors in ``infra/connectors/``.

    Subclasses must implement :meth:`fetch`, :meth:`normalize`, and
    :meth:`resolve_asset_id`. :meth:`run` orchestrates the three in order
    and should not need overriding.
    """

    #: Stable identifier for this connector, used in
    #: ``scan_scope.reachable_scanners`` / ``unreachable_scanners`` and in
    #: every ``provenance.connector`` field this connector produces. Must
    #: match the connector's module name.
    name: str

    @abc.abstractmethod
    def fetch(self) -> Any:
        """Retrieve raw, tool-native output from the source system.

        Must not perform any normalization or schema-shaping — this method
        returns exactly what the source tool gives back (parsed enough to
        be a Python object, e.g. from JSON/XML/CSV, but otherwise
        untransformed).

        Returns:
            Raw tool-native data in whatever structure is most faithful to
            the source (a list of dicts, a parsed report object, etc).

        Raises:
            Whatever connection/auth/parsing error is appropriate; a
            connector that cannot fetch must surface that as an error, not
            as an empty successful result, so that it can be recorded in
            ``scan_scope.unreachable_scanners`` rather than silently
            appearing as "ran and found nothing".
        """
        raise NotImplementedError

    @abc.abstractmethod
    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Transform raw tool output into schema-shaped fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts, each a fragment matching the relevant part of
            ``schema/aggregated_assets.schema.json`` (e.g. entries under
            ``assets[].findings``, or a full ``assets[]`` entry) *before*
            asset identity resolution has been attached. Every field name,
            severity scale, and enum value in the output must already
            match the schema's vocabulary — no tool-specific vocabulary may
            survive past this method.

        Must never:
            Include a field, key, or nested shape not present in
            ``schema/aggregated_assets.schema.json``. Must never invent a
            criticality/severity scale different from the schema's — map
            the source tool's scale explicitly and name that mapping as an
            assumption in ``core/assumptions.py`` if it requires a
            judgement call.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve a normalized fragment to a stable, cross-connector asset_id.

        Args:
            normalized_fragment: One item from :meth:`normalize`'s output.

        Returns:
            The stable ``asset_id`` string this fragment belongs to, using
            whatever identity-resolution mechanism the codebase has
            established (see ``cmdb_connector.py`` for the canonical
            source of asset identity). Must be stable across connector runs
            and across connectors — two different tools' data about the
            same physical/logical asset must resolve to the same
            ``asset_id``.

        Must never:
            Fabricate a new identity scheme local to this connector. If no
            existing asset_id can be resolved, that is a data quality
            problem to surface, not a reason to mint a connector-local ID.
        """
        raise NotImplementedError

    def run(self) -> list[dict[str, Any]]:
        """Execute fetch -> normalize -> attach asset_id, in order.

        After :meth:`resolve_asset_id` is called on a normalized fragment,
        any key in that fragment starting with ``_`` is stripped before it
        is returned. Such keys (e.g. ``_identity_hint``) are a private,
        non-schema bridging convention some connectors use internally to
        carry whatever raw identity information they have (a hostname, an
        agent IP, a cloud resource ARN) from :meth:`normalize` into
        :meth:`resolve_asset_id`, pending a real CMDB-based identity
        resolution (``cmdb_connector.py`` is itself still a stub with an
        unresolved TODO on identity keys). They must never survive into the
        aggregated snapshot, since nothing in ``schema/aggregated_assets.schema.json``
        defines them and ``additionalProperties: false`` would reject them.

        Returns:
            A list of normalized, asset_id-attached fragments ready to be
            merged into an aggregated snapshot by the aggregation pipeline
            that calls this connector — each a dict of
            ``{"asset_id": <resolved>, **fragment}`` with all ``_``-prefixed
            keys removed from ``fragment``.

        Must never:
            Catch a fetch failure and return an empty list silently — a
            failed fetch must propagate so the caller can record this
            connector under ``scan_scope.unreachable_scanners`` instead of
            an absence of findings being misread as a clean scan.
        """
        raw = self.fetch()
        fragments = self.normalize(raw)
        attached: list[dict[str, Any]] = []
        for fragment in fragments:
            asset_id = self.resolve_asset_id(fragment)
            cleaned = {key: value for key, value in fragment.items() if not key.startswith("_")}
            attached.append({"asset_id": asset_id, **cleaned})
        return attached
