"""Thin tool wrappers callable by the LLM tool-calling loop.

Every module in this package wraps a call into ``core/`` or
``governance/`` and returns structured output with provenance. None of them
compute anything themselves — see each module's docstring, and repo-root
``CLAUDE.md`` principles 1 and 2.
"""
