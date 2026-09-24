"""Load the repo-root ``.env`` into the process environment at startup.

Both entry points (``interfaces/api/app.py``'s ``create_app`` and
``interfaces/cli/riskctl.py``'s ``build_cli``) call :func:`load_dotenv`, so
``uvicorn --factory interfaces.api.app:create_app`` and ``riskctl`` pick up
``GROQ_API_KEY``, ``SNAPSHOT_STORE_PATH`` and the rest of ``.env`` without
the shell having to export them first. Every module that reads configuration
keeps reading ``os.environ`` as before; this only fills it in.

Deliberately a small standard-library parser rather than a dependency: the
file format used here is plain ``KEY=value`` lines (see ``.env.example``).
"""

from __future__ import annotations

import os
from pathlib import Path

#: The repo-root ``.env``, resolved from this file rather than the working
#: directory, so the API and CLI find it wherever they are started from.
DEFAULT_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _parse_value(raw: str) -> str:
    """One value: quotes stripped if quoted, else a trailing `` # comment`` dropped."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    comment = value.find(" #")
    return value[:comment].rstrip() if comment != -1 else value


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict.

    Supports ``KEY=value``, an optional ``export`` prefix, ``#`` comment
    lines, quoted values, and trailing `` # comments`` on unquoted values.
    Lines without ``=`` and entries whose value is empty are skipped, so an
    unfilled ``KEY=`` line leaves that variable unset (and its code default in
    force) rather than setting it to an empty string.
    """
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        key, separator, raw_value = stripped.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = _parse_value(raw_value)
        if value:
            parsed[key] = value
    return parsed


def load_dotenv(path: Path = DEFAULT_DOTENV_PATH) -> list[str]:
    """Copy ``path``'s variables into ``os.environ``, never overriding one already set.

    A variable exported in the shell (or set by a deployment) always wins
    over the file. A missing file is not an error: ``.env`` is optional and
    gitignored.

    Args:
        path: The ``.env`` file to load.

    Returns:
        The names of the variables this call set, for logging.

    Must never:
        Log or return any value — ``.env`` holds credentials.
    """
    if not path.is_file():
        return []
    loaded: list[str] = []
    for key, value in parse_dotenv(path.read_text()).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
