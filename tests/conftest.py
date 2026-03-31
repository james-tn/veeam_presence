"""Shared test configuration — uses real data/ pkl files, pre-loads caches."""

import os
import sys
import importlib
import pytest

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Real data directory
REAL_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
# Synthetic fixtures (fallback)
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Exclude legacy integration test that imports old top-level agent patterns
collect_ignore = [os.path.join(os.path.dirname(__file__), "integration_test.py")]


@pytest.fixture(autouse=True, scope="session")
def setup_data():
    """Use real data/ pkl files. Falls back to synthetic fixtures if data/ missing."""
    import config
    original_data_dir = config.DATA_DIR

    # Prefer real data, fall back to fixtures
    if os.path.isdir(REAL_DATA_DIR) and any(f.endswith(".pkl") for f in os.listdir(REAL_DATA_DIR)):
        config.DATA_DIR = REAL_DATA_DIR
        print(f"\n  [conftest] Using real data from {REAL_DATA_DIR}")
    else:
        config.DATA_DIR = FIXTURE_DIR
        pkl_files = [f for f in os.listdir(FIXTURE_DIR) if f.endswith(".pkl")]
        if len(pkl_files) < 14:
            from tests.fixtures.generate_fixtures import generate_all
            generate_all()
        print(f"\n  [conftest] Using synthetic fixtures from {FIXTURE_DIR}")

    # Import modules directly (not re-exported functions from __init__)
    qoi_mod = importlib.import_module("tools.query_office_intel")
    qp_mod = importlib.import_module("tools.query_person")
    from response_cache import load_pregenerated

    # Force-reload caches
    qoi_mod._cache.clear()
    qoi_mod.load_cache()

    qp_mod._enriched = None
    qp_mod._load_enriched()

    load_pregenerated()

    yield

    config.DATA_DIR = original_data_dir
