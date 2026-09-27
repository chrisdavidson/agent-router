"""Cascade decider (local -> Jev): offline, with fake stage deciders."""

from __future__ import annotations

import json
import math

import pytest

from agent_router.core.audit import AuditLog
from agent_router.core.catalog import load_catalog
from agent_router.core.config import RouterConfig
from agent_router.core.router import Router
from agent_router.core.types import (
    NONE_ID,
    Action,
    ChoiceResult,
    HookPoint,
    OptionSpec,
    RouterEvent,
)
from agent_router.deciders import cascade, local, registry
from agent_router.deciders.base import DeciderError, recommended_threshold
from agent_router.deciders.cascade import CascadeDecider
from agent_router.evaluate import (
    EvalCase,
    calibrate_cascade,
    make_router,
    routing_stats,
    run_eval,
    write_calibration,
)

OPTIONS = {
    "exact-calc": OptionSpec("exact arithmetic"),
    "json-query": OptionSpec("query JSON"),
    NONE_ID: OptionSpec("native"),
}


class Fake:
    def __init__(self, name, choice=NONE_ID, probs=None, error=None, **attrs):
        self.name = name
        self.choice = choice
        self.probs = probs or {NONE_ID: 1.0, "exact-calc": 0.0, "json-query": 0.0}
        self.error = error
        self.calls = 0
        for k, v in attrs.items():
            setattr(self, k, v)

    def decide(self, state, options):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ChoiceResult(
            choice=self.choice,
            probabilities=dict(self.probs),
            confidence=0.5,
            backend=self.name,
            latency_ms=1.0,
        )


def _local(choice, **probs):
    full = {"exact-calc": 0.0, "json-query": 0.0, NONE_ID: 0.0, **probs}
    return Fake("local", choice, full)


def _jev(choice="exact-calc", p=0.97):
    rest = (1 - p) / 2
    probs = {"exact-calc": rest, "json-query": rest, NONE_ID: rest, choice: p}
    return Fake("jev:jev-1", choice, probs)


def test_confident_none_answers_locally_without_escalation():
    primary, confirm = _local(NONE_ID, **{NONE_ID: 0.95, "exact-calc": 0.05}), _jev()
    d = CascadeDecider(primary, confirm, native_gate=0.9)
    res = d.decide("list files", OPTIONS)
    assert d.name == "cascade"
    assert confirm.calls == 0
    assert res.choice == NONE_ID
    assert res.backend == "cascade:local"
    assert res.probabilities == primary.probs
    assert [s["role"] for s in res.stages] == ["primary"]
    assert d.last_stages == list(res.stages)


def test_unsure_none_escalates_to_confirm():
    primary = _local(NONE_ID, **{NONE_ID: 0.6, "exact-calc": 0.4})
    confirm = _jev("exact-calc", 0.97)
    res = CascadeDecider(primary, confirm, native_gate=0.9).decide("2**64", OPTIONS)
    assert confirm.calls == 1
    assert res.choice == "exact-calc"
    assert res.backend == "cascade:jev:jev-1"
    assert res.probabilities == confirm.probs
    roles = [(s["role"], s["backend"], s["choice"]) for s in res.stages]
    assert roles == [("primary", "local", NONE_ID), ("confirm", "jev:jev-1", "exact-calc")]


def test_any_non_none_choice_escalates_even_when_confident():
    primary = _local("exact-calc", **{"exact-calc": 0.999, NONE_ID: 0.001})
    confirm = _jev(NONE_ID, 0.9)
    res = CascadeDecider(primary, confirm, native_gate=0.9).decide("x", OPTIONS)
    assert confirm.calls == 1
    assert res.choice == NONE_ID  # Jev vetoes the local suggestion


def test_gate_is_inclusive_and_above_one_always_escalates():
    primary = _local(NONE_ID, **{NONE_ID: 1.0})
    assert CascadeDecider(primary, _jev(), native_gate=1.0).decide("x", OPTIONS).backend == (
        "cascade:local"
    )
    confirm = _jev()
    CascadeDecider(primary, confirm, native_gate=1.01).decide("x", OPTIONS)
    assert confirm.calls == 1


def test_stages_are_plain_and_json_serialisable():
    primary = _local(NONE_ID, **{NONE_ID: 0.5, "exact-calc": 0.5})
    res = CascadeDecider(primary, _jev()).decide("x", OPTIONS)
    for s in res.stages:
        assert set(s) >= {"role", "backend", "choice", "probabilities", "confidence", "latency_ms"}
        assert all(type(v) is float for v in s["probabilities"].values())
    json.dumps(list(res.stages))
    assert res.latency_ms > 0


@pytest.mark.parametrize("error", [DeciderError("HTTP 500"), DeciderError("deadline")])
def test_confirm_failure_biases_an_unsure_local_choice_to_none(error):
    primary = _local("exact-calc", **{"exact-calc": 0.8, "json-query": 0.15, NONE_ID: 0.05})
    confirm = Fake("jev", error=error)
    res = CascadeDecider(primary, confirm).decide("x", OPTIONS)
    assert res.backend == "cascade:local-fallback"
    assert res.choice == NONE_ID
    assert math.isclose(sum(res.probabilities.values()), 1.0)
    assert res.probabilities["exact-calc"] == 0.0
    assert math.isclose(res.probabilities[NONE_ID], 0.85)
    assert max(res.probabilities, key=res.probabilities.get) == NONE_ID
    assert 0.0 <= res.confidence <= 1.0
    assert res.stages[-1]["role"] == "confirm" and res.stages[-1]["error"]


def test_confirm_failure_keeps_a_very_confident_local_choice():
    primary = _local("exact-calc", **{"exact-calc": 0.97, NONE_ID: 0.03})
    res = CascadeDecider(primary, Fake("jev", error=DeciderError("down"))).decide("x", OPTIONS)
    assert res.backend == "cascade:local-fallback"
    assert res.choice == "exact-calc"
    assert res.probabilities == primary.probs


def test_confirm_failure_on_unsure_none_stays_none():
    primary = _local(NONE_ID, **{NONE_ID: 0.5, "exact-calc": 0.5})
    res = CascadeDecider(primary, Fake("jev", error=DeciderError("down"))).decide("x", OPTIONS)
    assert res.choice == NONE_ID and res.backend == "cascade:local-fallback"


def test_confirm_failure_routes_native_through_router():
    catalog = load_catalog()
    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    dec = CascadeDecider(primary, Fake("jev", error=DeciderError("down")))
    router = Router(catalog, dec, RouterConfig(threshold=0.3), AuditLog(None))
    event = RouterEvent(HookPoint.PROMPT, "s", 1, "what is 17% of 2340 exactly?")
    d = router.route(event)
    assert d.action == Action.NATIVE
    rec = router.audit.records[-1]
    assert rec["backend"] == "cascade:local-fallback"
    assert [s["role"] for s in rec["stages"]] == ["primary", "confirm"]


def test_primary_failure_escalates_and_both_failing_raises():
    confirm = _jev()
    res = CascadeDecider(Fake("local", error=DeciderError("x")), confirm).decide("x", OPTIONS)
    assert res.choice == "exact-calc" and confirm.calls == 1
    assert res.stages[0]["error"]
    with pytest.raises(DeciderError):
        CascadeDecider(
            Fake("local", error=DeciderError("x")), Fake("jev", error=DeciderError("y"))
        ).decide("x", OPTIONS)


def test_timeout_and_threshold_delegate():
    confirm = _jev()
    confirm.timeout = 2.0
    confirm.recommended_threshold = None
    primary = _local(NONE_ID, **{NONE_ID: 1.0})
    primary.recommended_threshold = 0.35
    d = CascadeDecider(primary, confirm)
    d.timeout = 9.0
    assert confirm.timeout == 9.0 and d.timeout == 9.0
    assert recommended_threshold(d) is None  # never inherits the local stage's threshold
    confirm.recommended_threshold = 0.6
    assert recommended_threshold(d) == 0.6
    assert recommended_threshold(CascadeDecider(primary, confirm, threshold=0.5)) == 0.5


# -- registry / calibration ---------------------------------------------------------


@pytest.fixture
def hashing(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")


def test_default_backend_follows_jev_availability(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert registry.available_backends()["cascade"] is False
    assert registry.default_backend() == "local"
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test")
    assert registry.available_backends()["cascade"] is True
    assert registry.default_backend() == "cascade"
    assert "cascade" in registry.BACKENDS


def test_make_decider_cascade_is_local_then_jev(hashing):
    from agent_router.deciders.local import LocalJevDecider
    from agent_router.deciders.typesafe import TypeSafeJevDecider

    catalog = load_catalog()
    d = registry.make_decider("cascade", catalog)
    assert isinstance(d, CascadeDecider)
    assert isinstance(d.primary, LocalJevDecider)
    assert isinstance(d.confirm, TypeSafeJevDecider)
    assert d.native_gate == cascade.DEFAULT_NATIVE_GATE  # no calibration file in unit tests


def test_make_decider_local_passes_catalog_version(hashing, monkeypatch):
    seen = {}
    real = local.LocalJevDecider.__init__

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        real(self, *args, **kwargs)

    monkeypatch.setattr(local.LocalJevDecider, "__init__", spy)
    catalog = load_catalog()
    registry.make_decider("local", catalog)
    assert seen["catalog_version"] == catalog.version


def _write_block(path, **over):
    block = {
        "native_gate": 0.97,
        "threshold": 0.5,
        "catalog_version": load_catalog().version,
        "embedder": local.embedder_id(local.HashingEmbedder()),
        "feasible": True,
    }
    block.update(over)
    path.write_text(json.dumps({"cascade": block}))


def test_make_decider_cascade_loads_calibrated_gate(hashing, tmp_path, monkeypatch):
    path = tmp_path / "calibration.json"
    _write_block(path)
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    d = registry.make_decider("cascade", load_catalog())
    assert d.native_gate == 0.97
    assert recommended_threshold(d) == 0.5


@pytest.mark.parametrize(
    "over",
    [{"catalog_version": "other"}, {"embedder": "model2vec:x"}, {"feasible": False}],
)
def test_cascade_calibration_refused_on_mismatch(hashing, tmp_path, monkeypatch, over):
    path = tmp_path / "calibration.json"
    _write_block(path, **over)
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    d = registry.make_decider("cascade", load_catalog())
    assert d.native_gate == cascade.DEFAULT_NATIVE_GATE
    assert recommended_threshold(d) is None


def test_decision_payload_carries_stages():
    from agent_router.adapters.claude_sdk import decision_payload
    from agent_router.core.types import Decision

    primary = _local(NONE_ID, **{NONE_ID: 0.5, "exact-calc": 0.5})
    res = CascadeDecider(primary, _jev()).decide("x", OPTIONS)
    event = RouterEvent(HookPoint.PROMPT, "s", 1, "x")
    payload = decision_payload(event, Decision(Action.SUGGEST, "r", "exact-calc", "h", res))
    assert [s["role"] for s in payload["stages"]] == ["primary", "confirm"]
    json.dumps(payload)


# -- RouterConfig picks up the decider's calibrated threshold ------------------------


def test_config_from_env_uses_recommended_threshold(monkeypatch):
    monkeypatch.delenv("AGENT_ROUTER_THRESHOLD", raising=False)
    assert RouterConfig.from_env().threshold == RouterConfig().threshold
    assert RouterConfig.from_env(recommended_threshold=0.35).threshold == 0.35
    monkeypatch.setenv("AGENT_ROUTER_THRESHOLD", "0.7")
    assert RouterConfig.from_env(recommended_threshold=0.35).threshold == 0.7


def test_agent_make_router_applies_decider_threshold(monkeypatch):
    from agent_router import agent

    monkeypatch.delenv("AGENT_ROUTER_THRESHOLD", raising=False)
    dec = Fake("x", recommended_threshold=0.42)
    monkeypatch.setattr(registry, "make_decider", lambda name, catalog: dec)
    seen = []
    monkeypatch.setattr(registry, "default_backend", lambda: seen.append(1) or "cascade")
    router = agent.make_router()
    assert seen and router.decider is dec
    assert router.config.threshold == 0.42


# -- evaluation: escalation stats and native_gate calibration ----------------------------

CAL_CASES = [
    EvalCase("a", "list the files here", HookPoint.PROMPT, NONE_ID, split="cal"),
    EvalCase("b", "what is 2**64 exactly", HookPoint.PROMPT, "exact-calc", split="cal"),
    EvalCase("c", "run the test suite", HookPoint.PROMPT, NONE_ID, split="cal"),
    EvalCase("d", "compute 17% of 2340", HookPoint.PROMPT, "exact-calc", split="cal"),
]


class ByText:
    """Fake stage decider answering per case text: {text: (choice, p_choice)}."""

    def __init__(self, name, table, error=None):
        self.name = name
        self.table = table
        self.error = error
        self.calls: list[str] = []

    def decide(self, state, options):
        self.calls.append(state)
        if self.error is not None:
            raise self.error
        choice, p = self.table[state]
        others = [o for o in options if o != choice]
        probs = {o: (1 - p) / len(others) for o in others} | {choice: p}
        return ChoiceResult(choice, probs, 0.5, backend=self.name, latency_ms=2.0)


def _stage_fakes():
    primary = ByText(
        "local",
        {
            "list the files here": (NONE_ID, 0.99),
            "what is 2**64 exactly": (NONE_ID, 0.8),
            "run the test suite": (NONE_ID, 0.95),
            "compute 17% of 2340": ("exact-calc", 0.9),
        },
    )
    confirm = ByText("jev", {c.text: (c.expected, 0.97) for c in CAL_CASES})
    return primary, confirm


def test_routing_stats_counts_escalations_and_fallbacks():
    catalog = load_catalog()
    primary, confirm = _stage_fakes()
    router = make_router(CascadeDecider(primary, confirm, 0.9), catalog, threshold=0.5)
    rep = run_eval(lambda: router, CAL_CASES)
    assert rep.accuracy == 1.0  # b (p_none 0.8 < 0.9) and d (not none) went to jev
    stats = routing_stats(rep)
    assert stats["n"] == 4
    assert stats["escalated"] == 2 and stats["escalation_rate"] == 0.5
    assert stats["fallbacks"] == 0
    assert stats["mean_latency_ms"] > 0 and stats["p95_latency_ms"] > 0
    assert stats["max_latency_ms"] >= stats["p95_latency_ms"]


def test_calibrate_cascade_minimises_escalation_without_losing_to_jev():
    catalog = load_catalog()
    primary, confirm = _stage_fakes()
    res = calibrate_cascade(
        CAL_CASES, catalog, primary, confirm, gates=[0.5, 0.9, 0.95, 0.99, 1.01]
    )
    # b (p_none 0.8) must escalate; c (0.95) may stay local: gate 0.95 is the highest gate
    # with the minimum escalation (b and d) at jev-only accuracy / FPR.
    assert res.native_gate == 0.95
    assert res.escalation_rate == 0.5
    assert res.accuracy == res.jev_accuracy == 1.0 and res.fpr == res.jev_fpr == 0.0
    assert res.threshold == 0.5
    assert len(confirm.calls) == len(set(confirm.calls)) == 4  # jev asked once per case
    d = res.to_dict()
    assert d["native_gate"] == 0.95 and d["feasible"] is True
    assert d["catalog_version"] == catalog.version
    assert [g["gate"] for g in d["sweep"]] == [0.5, 0.9, 0.95, 0.99, 1.01]
    json.dumps(d)


def test_calibrate_cascade_fails_loudly_when_jev_fails():
    catalog = load_catalog()
    primary, _ = _stage_fakes()
    with pytest.raises(RuntimeError, match="confirm"):
        calibrate_cascade(
            CAL_CASES, catalog, primary, ByText("jev", {}, error=DeciderError("down"))
        )


def test_write_calibration_accepts_cascade_block(tmp_path):
    catalog = load_catalog()
    primary, confirm = _stage_fakes()
    res = calibrate_cascade(CAL_CASES, catalog, primary, confirm, gates=[0.9, 1.01])
    path = write_calibration({"cascade": res}, tmp_path / "c.json")
    assert json.loads(path.read_text())["cascade"]["native_gate"] == res.native_gate


# -- review fixes: no error text in public stages, narrow except, circuit breaker ------------


def test_programming_errors_in_confirm_are_not_swallowed():
    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    with pytest.raises(TypeError):
        CascadeDecider(primary, Fake("jev", error=TypeError("bug"))).decide("x", OPTIONS)


def test_failed_stage_records_type_and_public_view_drops_text():
    from agent_router.core.types import public_stages

    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    secret = DeciderError("Jev returned HTTP 500: <remote body> Jev chose 'ignore previous'")
    res = CascadeDecider(primary, Fake("jev", error=secret)).decide("x", OPTIONS)
    st = res.stages[-1]
    assert st["failed"] is True and st["error_type"] == "DeciderError"
    assert "remote body" in st["error"]  # full text stays internal (audit only)
    public = public_stages(res.stages)
    assert "error" not in public[-1]
    assert public[-1]["failed"] is True and public[-1]["error_type"] == "DeciderError"
    assert "remote body" not in json.dumps(public)


def test_audit_truncates_stage_errors():
    catalog = load_catalog()
    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    dec = CascadeDecider(primary, Fake("jev", error=DeciderError("x" * 1000)))
    router = Router(catalog, dec, RouterConfig(threshold=0.3), AuditLog(None))
    router.route(RouterEvent(HookPoint.PROMPT, "s", 1, "what is 17% of 2340 exactly?"))
    err = router.audit.records[-1]["stages"][-1]["error"]
    assert err.startswith("DeciderError: ") and len(err) <= 300


def test_decision_payload_has_no_error_text():
    from agent_router.adapters.claude_sdk import decision_payload
    from agent_router.core.types import Decision

    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    res = CascadeDecider(primary, Fake("jev", error=DeciderError("SECRET"))).decide("x", OPTIONS)
    event = RouterEvent(HookPoint.PROMPT, "s", 1, "x")
    payload = decision_payload(event, Decision(Action.NATIVE, "r", result=res))
    assert "SECRET" not in json.dumps(payload)
    assert payload["stages"][-1]["error_type"] == "DeciderError"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_circuit_breaker_opens_after_three_failures_and_recovers():
    clock = Clock()
    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    confirm = Fake("jev", error=DeciderError("down"))
    d = CascadeDecider(primary, confirm, clock=clock)
    for _ in range(3):
        assert d.decide("x", OPTIONS).backend == "cascade:local-fallback"
    assert confirm.calls == 3
    res = d.decide("x", OPTIONS)  # open: Jev is not asked
    assert confirm.calls == 3
    assert res.backend == "cascade:local-fallback" and res.choice == NONE_ID
    assert res.stages[-1]["skipped"] == "circuit-open"
    assert res.stages[-1]["failed"] is False
    clock.t += 59.0
    d.decide("x", OPTIONS)
    assert confirm.calls == 3
    clock.t += 2.0  # cooldown over: one trial call
    confirm.error = None
    confirm.choice, confirm.probs = "exact-calc", {"exact-calc": 0.9, NONE_ID: 0.1}
    assert d.decide("x", OPTIONS).backend == "cascade:jev"
    assert confirm.calls == 4
    confirm.error = DeciderError("down again")  # success reset the count
    d.decide("x", OPTIONS)
    d.decide("x", OPTIONS)
    assert confirm.calls == 6  # two failures: still closed


def test_circuit_breaker_trial_failure_reopens():
    clock = Clock()
    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    confirm = Fake("jev", error=DeciderError("down"))
    d = CascadeDecider(primary, confirm, clock=clock)
    for _ in range(3):
        d.decide("x", OPTIONS)
    clock.t += 61.0
    d.decide("x", OPTIONS)  # trial fails
    assert confirm.calls == 4
    d.decide("x", OPTIONS)
    assert confirm.calls == 4  # open again


def test_circuit_open_with_failed_primary_raises():
    clock = Clock()
    confirm = Fake("jev", error=DeciderError("down"))
    d = CascadeDecider(_local("exact-calc", **{"exact-calc": 0.8}), confirm, clock=clock)
    for _ in range(3):
        d.decide("x", OPTIONS)
    d.primary = Fake("local", error=DeciderError("x"))
    with pytest.raises(DeciderError):
        d.decide("x", OPTIONS)


def test_circuit_breaker_is_thread_safe():
    import threading

    primary = _local("exact-calc", **{"exact-calc": 0.8, NONE_ID: 0.2})
    confirm = Fake("jev", error=DeciderError("down"))
    d = CascadeDecider(primary, confirm, clock=Clock())
    threads = [threading.Thread(target=d.decide, args=("x", OPTIONS)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert confirm.calls >= 3
    before = confirm.calls
    assert d.decide("x", OPTIONS).stages[-1]["skipped"] == "circuit-open"
    assert confirm.calls == before


class _Recording(Fake):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.states = []

    def decide(self, state, options):
        self.states.append(state)
        return super().decide(state, options)


def test_confirm_stage_gets_the_full_state_with_recent_context():
    """The local stage scores the current step itself; Jev sees the recent context."""
    primary = _Recording("local", "exact-calc", {"exact-calc": 0.6, NONE_ID: 0.4})
    confirm = _Recording("jev:jev-1", "exact-calc", {"exact-calc": 0.9, NONE_ID: 0.1})
    router = Router(
        load_catalog(), CascadeDecider(primary, confirm, 0.9), RouterConfig(), AuditLog(None)
    )
    router.route(
        RouterEvent(
            point=HookPoint.PROMPT,
            session_id="s",
            turn_id=1,
            text="what is 2**200 exactly",
            recent=("convert page.html to markdown",),
        )
    )
    assert confirm.states and "previous: convert page.html to markdown" in confirm.states[0]
    assert primary.states[0] == confirm.states[0]  # the same state; local trims it itself
