"""Shared test setup.

Unit tests must not depend on the shipped ``calibration.json``: for the whole session the
local decider looks for calibration at a path that does not exist, so it uses the
``LocalParams`` defaults. Tests that want the shipped file opt in with ``shipped_calibration``.
"""

import pytest

from agent_router.deciders import local


@pytest.fixture(scope="session", autouse=True)
def _no_shipped_calibration(tmp_path_factory):
    missing = tmp_path_factory.mktemp("no-calibration") / "calibration.json"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(local, "CALIBRATION_PATH", missing)
        yield


@pytest.fixture
def shipped_calibration(monkeypatch):
    """Opt in to the packaged ``calibration.json``."""
    monkeypatch.setattr(local, "CALIBRATION_PATH", local.DEFAULT_CALIBRATION_PATH)
    return local.DEFAULT_CALIBRATION_PATH
