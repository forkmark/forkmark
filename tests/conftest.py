"""Shared pytest fixtures.

Test isolation: several suites mutate process-global environment variables
directly via ``os.environ`` (e.g. ``FM_ENABLE_AGENT_COMPARISON``) to exercise
feature gating. Without cleanup those values leak into later tests and cause
order-dependent failures that only show up in a full single-process run (CI),
not when running one file at a time. This autouse fixture snapshots and restores
``os.environ`` around every test so the suite is order-independent.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _restore_environ():
    snapshot = dict(os.environ)
    yield
    # Drop keys added during the test...
    for key in list(os.environ.keys()):
        if key not in snapshot:
            del os.environ[key]
    # ...and restore any changed or removed keys to their pre-test values.
    for key, value in snapshot.items():
        if os.environ.get(key) != value:
            os.environ[key] = value
