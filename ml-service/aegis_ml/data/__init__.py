"""Telemetry schemas, feature extraction, and the deterministic generator.

Submodules are imported directly; this package re-exports nothing, so there is
one obvious path to each name:

* :mod:`aegis_ml.data.records` — the canonical ``flow@1`` and ``log@1`` records
* :mod:`aegis_ml.data.features` — ``features@1`` extraction and its schema hash
* :mod:`aegis_ml.data.windowing` — sliding per-entity windows (T-108)
* :mod:`aegis_ml.data.splits` — leakage-safe train/valid/test (T-109)
* :mod:`aegis_ml.data.synthetic` — the seven-scenario seeded generator
"""
