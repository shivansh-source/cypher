"""Connector for identity and access management posture (e.g. Azure AD/Entra,
AWS IAM, Okta).

Normalizes IAM data into ``schema/aggregated_assets.schema.json``
``assets[].identity_access`` entries: privileged account counts and MFA
enforcement per asset.
"""

from __future__ import annotations

from typing import Any

from infra.connectors.base import Connector


class IAMConnector(Connector):
    """Fetches and normalizes identity/access posture data.

    See :class:`infra.connectors.base.Connector` for the fetch -> normalize
    -> attach contract this class must obey.
    """

    name: str = "iam_connector"

    def fetch(self) -> Any:
        """Retrieve raw account/role/MFA data from the IAM provider's API.

        Returns:
            Parsed but untransformed account, role, and MFA-status data.

        Raises:
            An error appropriate to the transport. Must not return an empty
            result to mean "could not fetch".
        """
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        """Map IAM data to schema-shaped ``identity_access`` fragments.

        Args:
            raw: Exactly what :meth:`fetch` returned.

        Returns:
            A list of dicts matching ``assets[].identity_access``, with
            ``privileged_accounts_count`` and ``mfa_enforced`` derived
            from the provider's actual role/policy assignments — not
            estimated.

        Must never:
            Guess ``mfa_enforced`` from a default policy that isn't
            actually applied to the specific account/asset in question.
        """
        raise NotImplementedError

    def resolve_asset_id(self, normalized_fragment: dict[str, Any]) -> str:
        """Resolve an IAM principal's associated asset to a stable asset_id.

        Args:
            normalized_fragment: One normalized fragment.

        Returns:
            The stable ``asset_id`` string, resolved via the same identity
            mechanism as ``cmdb_connector.py``.
        """
        raise NotImplementedError
