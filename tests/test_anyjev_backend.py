import math
import sys
import types

import numpy as np
import pytest

from agent_router.core.types import NONE_ID, OptionSpec
from agent_router.deciders.anyjev_backend import AnyJevDecider
from agent_router.deciders.base import DeciderError

OPTIONS = {
    NONE_ID: OptionSpec(what=""),
    "exact-calc": OptionSpec(what="Exact arithmetic", examples=("compute 2**200 exactly",)),
    "json-query": OptionSpec(what="Query JSON files with JMESPath"),
}


@pytest.fixture
def fake_anyjev(monkeypatch):
    """Minimal stand-in for anyjev 0.0.2's public API (Decider, Question, HFBackend)."""
    calls: dict = {"backend": [], "decider": [], "decide": []}

    class Question:
        def __init__(self, kind, text, options, name=None):
            self.kind, self.text, self.options, self.name = kind, text, tuple(options), name

        @staticmethod
        def choice(text, options, name=None):
            opts = tuple(options)
            if len(opts) < 2 or len(set(opts)) != len(opts):
                raise ValueError("bad options")
            return Question("choice", text, opts, name)

    class Decision:
        def __init__(self, q, probs, level):
            self.question, self.probs, self.level = q, np.asarray(probs), level

        @property
        def confidence(self):  # anyjev's own confidence is max-prob; the adapter must not use it
            return float(np.max(self.probs))

    class DecisionSet:
        def __init__(self, decs, level):
            self._items, self.level = decs, level

        def __getitem__(self, key):
            if isinstance(key, int):
                return self._items[key]
            return {d.question.name: d for d in self._items}[key]

    class Decider:
        def __init__(self, backend, **kwargs):
            self.backend = backend
            calls["decider"].append(kwargs)

        def decide(self, state, questions, level=None):
            (q,) = questions
            calls["decide"].append((state, q))
            raw = np.array([4.0 if o.startswith("Exact") else 1.0 for o in q.options])
            return DecisionSet([Decision(q, raw / raw.sum(), "L0")], "L0")

    class HFBackend:
        def __init__(self, model_name, device="cuda", **kwargs):
            self.name = model_name
            calls["backend"].append((model_name, device))

    anyjev = types.ModuleType("anyjev")
    anyjev.Decider, anyjev.Question = Decider, Question
    backends = types.ModuleType("anyjev.backends")
    hf = types.ModuleType("anyjev.backends.hf")
    hf.HFBackend = HFBackend
    monkeypatch.setitem(sys.modules, "anyjev", anyjev)
    monkeypatch.setitem(sys.modules, "anyjev.backends", backends)
    monkeypatch.setitem(sys.modules, "anyjev.backends.hf", hf)
    return calls


def test_maps_anyjev_choice_into_choice_result(fake_anyjev):
    d = AnyJevDecider()
    assert d.name == "anyjev"
    result = d.decide("compute 2**200 exactly", OPTIONS)

    assert result.choice == "exact-calc"
    assert set(result.probabilities) == set(OPTIONS)
    assert math.isclose(sum(result.probabilities.values()), 1.0)
    assert math.isclose(result.probabilities["exact-calc"], 4 / 6)
    assert math.isclose(result.probabilities[NONE_ID], 1 / 6)
    # confidence is 1 - H/log n, not anyjev's max-prob
    p = np.array([4, 1, 1]) / 6
    assert math.isclose(result.confidence, 1 + float((p * np.log(p)).sum()) / math.log(3))
    assert result.backend == "anyjev:L0:Qwen/Qwen3-0.6B"


def test_question_lists_options_none_last_with_descriptions(fake_anyjev):
    AnyJevDecider().decide("x", OPTIONS)
    ((_, q),) = fake_anyjev["decide"]
    assert q.kind == "choice"
    assert q.options[0].startswith("Exact arithmetic")
    assert q.options[1].startswith("Query JSON")
    assert q.options[2]  # none has a non-empty label


def test_builds_backend_on_cpu_with_router_safe_defaults(fake_anyjev):
    d = AnyJevDecider(model="Qwen/Qwen3-1.7B")
    d.decide("x", OPTIONS)
    d.decide("y", OPTIONS)
    assert fake_anyjev["backend"] == [("Qwen/Qwen3-1.7B", "cpu")]  # loaded once, lazily
    (kwargs,) = fake_anyjev["decider"]
    assert kwargs["level"] == "L0"
    assert kwargs["prior"] == "none"


def test_options_must_include_none(fake_anyjev):
    with pytest.raises(DeciderError):
        AnyJevDecider().decide("x", {"exact-calc": OPTIONS["exact-calc"]})


def test_anyjev_failure_becomes_decider_error(fake_anyjev, monkeypatch):
    def boom(self, state, questions, level=None):
        raise RuntimeError("CUDA not available")

    monkeypatch.setattr(sys.modules["anyjev"].Decider, "decide", boom)
    with pytest.raises(DeciderError, match="CUDA"):
        AnyJevDecider().decide("x", OPTIONS)


def test_missing_anyjev_is_decider_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anyjev", None)
    d = AnyJevDecider()
    with pytest.raises(DeciderError, match=r"agent-router\[anyjev\]"):
        d.decide("x", OPTIONS)


def test_registry_builds_anyjev():
    from agent_router.core.catalog import load_catalog
    from agent_router.deciders.registry import make_decider

    assert isinstance(make_decider("anyjev", load_catalog()), AnyJevDecider)
