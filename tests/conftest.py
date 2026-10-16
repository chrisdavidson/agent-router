"""Shared test setup.

Unit tests must not depend on the shipped ``calibration.json``: for the whole session the
local decider looks for calibration at a path that does not exist, so it uses the
``LocalParams`` defaults. Tests that want the shipped file opt in with ``shipped_calibration``.
Jev API keys are removed for every test not marked ``live``.
"""

import os

import pytest

from agent_router.deciders import local

# The plugin cache is the user's real one unless told otherwise; a test must not find (or miss)
# a manifest in it. Set at import so modules that resolve a manifest while being collected see it.
os.environ.setdefault("AGENT_ROUTER_PLUGIN_CACHE", "/nonexistent/plugin-cache")


@pytest.fixture(scope="session", autouse=True)
def _no_shipped_calibration(tmp_path_factory):
    missing = tmp_path_factory.mktemp("no-calibration") / "calibration.json"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(local, "CALIBRATION_PATH", missing)
        yield


@pytest.fixture(autouse=True)
def _no_jev_keys(request, monkeypatch):
    """Offline by default: without a Jev key the default backend is ``local`` and nothing
    reaches the network. ``live`` tests keep the real keys."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


@pytest.fixture
def shipped_calibration(monkeypatch):
    """Opt in to the packaged ``calibration.json``."""
    monkeypatch.setattr(local, "CALIBRATION_PATH", local.DEFAULT_CALIBRATION_PATH)
    return local.DEFAULT_CALIBRATION_PATH
