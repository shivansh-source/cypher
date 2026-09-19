"""Connectors that pull raw output from security tools and normalize it into
the shared contract at ``schema/aggregated_assets.schema.json``, plus the
deployment skeleton (``docker-compose.yml``) for running them.

See ``infra/connectors/base.py`` for the fetch -> normalize -> attach
contract every connector obeys, and repo-root ``CLAUDE.md`` principle 3:
nothing outside this package may know which tool produced a given piece of
data.
"""
