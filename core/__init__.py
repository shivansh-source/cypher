"""Snapshot lifecycle, quality gates, the Open FAIR + Monte Carlo engine, the
budget optimizer, and every named modelling assumption.

This is the only package in the repo permitted to produce a rupee-denominated
risk figure. It reads only ``schema/aggregated_assets.schema.json``-shaped
data and has no knowledge of any specific security tool — see repo-root
``CLAUDE.md`` principle 3.
"""
