import json

import pytest

from agent_router.core.catalog import load_catalog
from agent_router.core.types import NONE_ID, Action, ChoiceResult, Decision, HookPoint
from agent_router.deciders import local
from agent_router.deciders.embedders import HashingEmbedder, Model2VecEmbedder
from agent_router.deciders.local import LocalJevDecider, LocalParams, content_tokens, jaccard
from agent_router.evaluate import (
    DEFAULT_EVAL_SET,
    EvalCase,
    calibrate,
    grid_search,
    load_cases,
    make_router,
    predicted_label,
    run_eval,
    write_calibration,
)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def cases():
    return load_cases()


# --- eval set shape ---------------------------------------------------------


def test_eval_set_counts(cases, catalog):
    assert len(cases) >= 60
    for entry in catalog.entries:
        assert sum(c.expected == entry.id for c in cases) >= 8, entry.id
    assert sum(c.expected == NONE_ID for c in cases) >= 20
    assert sum(c.decoy for c in cases) >= 5
    assert all(c.expected == NONE_ID for c in cases if c.decoy)
    assert len({c.id for c in cases}) == len(cases)


def test_eval_set_splits_cover_every_entry_and_point(cases, catalog):
    assert {c.split for c in cases} == {"cal", "test"}
    for split in ("cal", "test"):
        part = [c for c in cases if c.split == split]
        for entry in catalog.entries:
            points = {c.point for c in part if c.expected == entry.id}
            assert points == set(entry.points), (split, entry.id, points)
        assert sum(c.decoy for c in part) >= 3
        assert sum(c.expected == NONE_ID and not c.decoy for c in part) >= 10


def test_eval_set_has_tool_and_skill_cases_with_inputs(cases):
    tools = [c for c in cases if c.point == HookPoint.TOOL]
    skills = [c for c in cases if c.point == HookPoint.SKILL]
    assert {c.tool_name for c in tools} >= {"Bash", "Read", "Glob"}
    assert all(c.tool_input for c in tools + skills)
    assert all(c.tool_name == "Skill" for c in skills)
    native_bash = {
        c.tool_input["command"] for c in tools if c.tool_name == "Bash" and c.expected == NONE_ID
    }
    assert {"pytest -q", "git diff"} <= native_bash


def test_every_expected_label_is_reachable(cases, catalog):
    for c in cases:
        eligible = {e.id for e in catalog.eligible(c.point, c.tool_name)}
        assert c.expected == NONE_ID or c.expected in eligible, c.id
        skill = (c.tool_input or {}).get("skill")
        assert not catalog.owns_target(c.tool_name, skill=skill), c.id


def test_eval_texts_are_not_copies_of_catalog_examples(cases, catalog):
    exemplars = [ex for e in catalog.entries for ex in e.examples] + list(catalog.native_examples)
    ex_tokens = [(ex, content_tokens(ex)) for ex in exemplars]
    for c in cases:
        for field in (c.text, *(str(v) for v in (c.tool_input or {}).values())):
            if not field.strip():
                continue
            toks = content_tokens(field)
            for ex, et in ex_tokens:
                assert field.strip().lower() != ex.strip().lower(), (c.id, ex)
                assert jaccard(toks, et) < 0.5, (c.id, field, ex)


def test_load_cases_split_filter():
    test = load_cases(split="test")
    assert test and all(c.split == "test" for c in test)
    assert len(load_cases(split="all")) == len(load_cases())
    with pytest.raises(ValueError):
        load_cases(split="nope")


def test_default_eval_set_exists():
    assert DEFAULT_EVAL_SET.is_file()


# --- harness ------------------------------------------------------------------


class FixedRouter:
    """Stand-in router: returns a scripted decision per case text."""

    def __init__(self, script):
        self.script = script
        self.turns = []

    def route(self, event):
        self.turns.append(event.turn_id)
        return self.script[event.text]


def _suggest(entry, p=0.9):
    res = ChoiceResult(choice=entry, probabilities={entry: p, NONE_ID: 1 - p}, confidence=0.5)
    return Decision(Action.SUGGEST, "ok", entry_id=entry, result=res)


def test_predicted_label():
    assert predicted_label(_suggest("exact-calc")) == "exact-calc"
    assert predicted_label(Decision(Action.ENFORCE, "x", entry_id="repo-stats")) == "repo-stats"
    assert predicted_label(Decision(Action.NATIVE, "below", entry_id="exact-calc")) == NONE_ID
    assert predicted_label(Decision(Action.SKIPPED, "no eligible entries")) == NONE_ID


def test_run_eval_metrics():
    cases = [
        EvalCase(id="a", text="a", point=HookPoint.PROMPT, expected="exact-calc"),
        EvalCase(id="b", text="b", point=HookPoint.PROMPT, expected="exact-calc"),
        EvalCase(id="c", text="c", point=HookPoint.PROMPT, expected="json-query"),
        EvalCase(id="d", text="d", point=HookPoint.PROMPT, expected=NONE_ID),
        EvalCase(id="e", text="e", point=HookPoint.PROMPT, expected=NONE_ID, decoy=True),
        EvalCase(id="f", text="f", point=HookPoint.PROMPT, expected=NONE_ID),
    ]
    script = {
        "a": _suggest("exact-calc"),
        "b": Decision(Action.NATIVE, "decider chose none"),
        "c": _suggest("exact-calc"),  # misroute
        "d": _suggest("repo-stats"),  # false positive
        "e": Decision(Action.NATIVE, "decider chose none"),
        "f": Decision(Action.NATIVE, "decider error: DeciderError: boom"),
    }
    router = FixedRouter(script)
    rep = run_eval(lambda: router, cases)
    assert rep.n == 6
    assert rep.accuracy == pytest.approx(3 / 6)
    assert rep.fpr == pytest.approx(1 / 3)
    assert rep.misroute_rate == pytest.approx(1 / 3)
    assert rep.errors == 1
    assert rep.confusions[("json-query", "exact-calc")] == 1
    assert rep.confusions[(NONE_ID, "repo-stats")] == 1
    assert rep.per_entry["exact-calc"]["recall"] == pytest.approx(0.5)
    assert rep.per_entry["exact-calc"]["precision"] == pytest.approx(0.5)
    assert len(set(router.turns)) == 6  # unique turn per case: no once-per-turn dedupe
    d = rep.to_dict()
    json.dumps(d)
    assert d["accuracy"] == pytest.approx(0.5)
    assert {"id", "expected", "predicted", "action", "reason"} <= set(d["cases"][0])


def test_run_eval_real_router_hashing(cases, catalog):
    test = [c for c in cases if c.split == "test"]
    rep = run_eval(lambda: make_router("local", catalog, embedder=HashingEmbedder()), test)
    assert rep.n == len(test)
    assert 0.0 <= rep.accuracy <= 1.0
    assert rep.errors == 0


def test_make_router_uses_explicit_advisory_config(catalog, tmp_path):
    r = make_router("local", catalog, embedder=HashingEmbedder(), threshold=0.42)
    assert r.config.mode == "advisory"
    assert r.config.threshold == pytest.approx(0.42)
    assert r.audit.path is None


# --- calibration ----------------------------------------------------------------


SMALL_GRID = {"none_floor": [0.3, 0.5], "temperature": [0.05, 0.1], "threshold": [0.4, 0.6]}


def test_grid_search_respects_fpr_and_returns_grid_point(cases, catalog):
    cal = [c for c in cases if c.split == "cal"]
    res = grid_search(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)
    assert res.params.none_floor in SMALL_GRID["none_floor"]
    assert res.params.temperature in SMALL_GRID["temperature"]
    assert res.threshold in SMALL_GRID["threshold"]
    if res.feasible:
        assert res.fpr <= 0.10
    params, threshold = calibrate(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)
    assert isinstance(params, LocalParams)
    assert (params.none_floor, params.temperature, threshold) == (
        res.params.none_floor,
        res.params.temperature,
        res.threshold,
    )


def test_grid_search_matches_run_eval(cases, catalog):
    """The fast threshold sweep agrees with a real router run at the chosen point."""
    cal = [c for c in cases if c.split == "cal"]
    res = grid_search(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)
    dec = LocalJevDecider(
        embedder=HashingEmbedder(), params=res.params, native_examples=catalog.native_examples
    )
    rep = run_eval(lambda: make_router(dec, catalog, threshold=res.threshold), cal)
    assert rep.accuracy == pytest.approx(res.accuracy)
    assert rep.fpr == pytest.approx(res.fpr)


def test_write_and_load_calibration(tmp_path, monkeypatch, cases, catalog):
    path = tmp_path / "calibration.json"
    cal = [c for c in cases if c.split == "cal"]
    res = grid_search(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)
    write_calibration({"hashing": res}, path)
    write_calibration({"model2vec": res}, path)  # merges, keeps hashing
    data = json.loads(path.read_text())
    assert set(data) >= {"hashing", "model2vec"}
    assert data["hashing"]["threshold"] == res.threshold

    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    params, threshold = local.load_calibration("hashing")
    assert params.none_floor == res.params.none_floor
    assert threshold == res.threshold
    d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params.none_floor == res.params.none_floor
    assert d.recommended_threshold == res.threshold
    # explicit params always win
    d2 = LocalJevDecider(embedder=HashingEmbedder(), params=LocalParams())
    assert d2.params == LocalParams()
    # make_router picks up the recommended threshold
    r = make_router("local", catalog, embedder=HashingEmbedder())
    assert r.config.threshold == pytest.approx(res.threshold)


def test_no_calibration_file_keeps_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "CALIBRATION_PATH", tmp_path / "missing.json")
    d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params == LocalParams()
    assert d.recommended_threshold is None
    assert local.load_calibration("hashing") is None


def test_calibration_picked_by_actual_embedder(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {
                "hashing": {"none_floor": 0.11, "temperature": 0.2, "threshold": 0.3},
                "model2vec": {"none_floor": 0.22, "temperature": 0.1, "threshold": 0.6},
            }
        )
    )
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    assert local.embedder_key(HashingEmbedder()) == "hashing"
    assert local.embedder_key(Model2VecEmbedder()) == "model2vec"
    assert local.embedder_key(object()) is None
    assert LocalJevDecider(embedder=HashingEmbedder()).params.none_floor == 0.11
    assert LocalJevDecider(embedder=object()).params == LocalParams()


def test_corrupt_calibration_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    path.write_text("{not json")
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    assert local.load_calibration("hashing") is None


def test_shipped_calibration_has_both_embedders():
    data = json.loads(local.CALIBRATION_PATH.read_text())
    for key in ("model2vec", "hashing"):
        block = data[key]
        assert {"none_floor", "temperature", "threshold", "alpha", "not_for_penalty"} <= set(block)


# --- model test -------------------------------------------------------------------


@pytest.mark.model
def test_calibrated_model2vec_holdout(catalog):
    data = json.loads(local.CALIBRATION_PATH.read_text())
    assert "model2vec" in data, "run `agent-router calibrate` first"
    emb = Model2VecEmbedder()
    emb.load()
    holdout = load_cases(split="test")
    rep = run_eval(lambda: make_router("local", catalog, embedder=emb), holdout)
    assert rep.errors == 0
    assert rep.accuracy >= 0.85, rep.summary()
    assert rep.fpr <= 0.10, rep.summary()
