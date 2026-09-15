from __future__ import annotations

import pytest

from src import config


@pytest.fixture(autouse=True)
def trusted_local_test_mode(monkeypatch):
    """Existing backend contracts exercise a trusted local operator by default.

    Public-demo tests explicitly select public-demo and assert stricter boundaries.
    This never changes the application's secure public-demo runtime default.
    """
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "local")
