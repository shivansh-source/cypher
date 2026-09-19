"""Connectors that pull raw output from security tools and normalize it into
the shared contract at ``schema/aggregated_assets.schema.json``.

Every connector in this package obeys the fetch -> normalize -> attach
contract defined in ``base.py``. Nothing outside this package may know which
tool produced a given piece of data — see the repo-root ``CLAUDE.md``,
principle 3.
"""
