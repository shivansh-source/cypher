"""Regulatory framework mapping and compliance evidence generation.

Maps findings and controls (never optimizer output) to Indian regulatory
frameworks — see repo-root ``CLAUDE.md`` principle 6. May read from
``core/`` (findings/controls) but never certifies a recommendation as
compliant.

- ``control_library/`` — versioned, effective-dated, sourced regulatory
  facts (see its README for the file shape and sourcing rules).
- ``library_loader.py`` — loads/validates control library YAML files.
- ``attestations.py`` — append-only manual attestation storage and expiry.
- ``mapper.py`` — evaluates control status and weighted scores from a
  snapshot plus attestations.
- ``evidence_generator.py`` — renders deterministic, auditor-facing
  evidence packages from computed status.
"""
