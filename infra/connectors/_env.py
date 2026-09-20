"""Tiny shared environment-variable helpers for connectors.

Not a connector itself and not part of the schema contract — purely a
DRY-ing of "read this env var, and raise a clear, connector-named error if
a required one is missing" across the connectors that talk to live tool
APIs (``wazuh_connector.py``, ``greenbone_connector.py``) and the shared
object-store helper (``_object_store.py``).
"""

from __future__ import annotations

import os


def get_optional(name: str) -> str | None:
    """Read an environment variable, returning ``None`` if unset or empty.

    Args:
        name: The environment variable's name.

    Returns:
        The variable's value, or ``None`` if it is unset or an empty string.
    """
    value = os.environ.get(name)
    return value if value else None


def require(name: str, connector_name: str, error_type: type[Exception]) -> str:
    """Read a required environment variable or raise a connector-specific error.

    Args:
        name: The environment variable's name.
        connector_name: The requesting connector's stable ``name``, included
            in the error message so a failure is traceable to its source.
        error_type: The connector-specific exception class to raise (e.g.
            ``WazuhConnectorError``) — never a generic exception, so callers
            can catch exactly the failures their own connector can produce.

    Returns:
        The variable's value.

    Raises:
        error_type: If the environment variable is unset or empty.
    """
    value = get_optional(name)
    if value is None:
        raise error_type(
            f"{connector_name}: required environment variable {name} is not set"
        )
    return value
