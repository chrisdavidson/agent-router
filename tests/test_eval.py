import json
import logging

import numpy as np
import pytest

from agent_router.core.catalog import load_catalog
from agent_router.core.types import NONE_ID, Action, ChoiceResult, Decision, HookPoint
from agent_router.deciders import local
from agent_router.deciders.embedders import HashingEmbedder, Model2VecEmbedder
from agent_router.deciders.local import LocalJevDecider, LocalParams, content_tokens, jaccard
from agent_router.evaluate import (
    DEFAULT_EVAL_SET,
    DEFAULT_GRID,
    TARGET_ACCURACY,
    TARGET_FPR,
    EvalCase,
    calibrate,
    grid_search,
    load_cases,
    make_router,
    predicted_label,
    rank_candidates,
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


def test_eval_texts_are_not_copies_of_catalog_criteria(cases, catalog):
    exemplars = [ex for e in catalog.entries for ex in (e.what, *e.examples, *e.not_for)] + list(
        catalog.native_examples
    )
    ex_tokens = [(ex, content_tokens(ex)) for ex in exemplars]
    for c in cases:
        fields_ = (c.text, *(str(v) for v in (c.tool_input or {}).values()), *c.recent)
        for field in fields_:
            if not field.strip():
                continue
            toks = content_tokens(field)
            for ex, et in ex_tokens:
                assert field.strip().lower() != ex.strip().lower(), (c.id, ex)
                assert jaccard(toks, et) < 0.5, (c.id, field, ex)


def test_eval_set_has_context_cases(cases):
    """Multi-turn cases: misleading recent prompts must not move the decision."""
    ctx = [c for c in cases if c.recent]
    assert len(ctx) >= 8
    assert all(isinstance(c.recent, tuple) for c in ctx)
    assert all(isinstance(r, str) for c in ctx for r in c.recent)
    for split in ("cal", "test"):
        part = [c for c in ctx if c.split == split]
        assert any(c.expected == NONE_ID for c in part), split
        assert any(c.expected != NONE_ID for c in part), split
    assert any(c.point == HookPoint.TOOL for c in ctx)


def test_eval_case_event_carries_recent(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text(
        "cases:\n"
        "  - {id: c1, split: test, point: prompt, expected: none, text: run the tests,\n"
        "     recent: [parse orders.json, convert page.html]}\n"
        "  - {id: c2, split: cal, point: prompt, expected: none, text: hi}\n"
    )
    c1, c2 = load_cases(path)
    assert c1.recent == ("parse orders.json", "convert page.html")
    assert c2.recent == ()
    assert c1.event(turn_id=3).recent == c1.recent


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


SMALL_GRID = {
    "none_floor": [0.3, 0.5],
    "temperature": [0.08, 0.15],
    "not_for_penalty": [0.5],
    "threshold": [0.4, 0.6],
}


@pytest.fixture(scope="module")
def small_result(cases, catalog):
    cal = [c for c in cases if c.split == "cal"]
    return grid_search(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)


def test_default_grid_is_small_and_soft():
    assert "alpha" not in DEFAULT_GRID  # fixed at its default
    assert min(DEFAULT_GRID["temperature"]) >= 0.08
    assert (TARGET_ACCURACY, TARGET_FPR) == (0.85, 0.10)


def test_grid_search_result(small_result, catalog):
    res = small_result
    assert res.params.none_floor in SMALL_GRID["none_floor"]
    assert res.params.temperature in SMALL_GRID["temperature"]
    assert res.params.alpha == LocalParams().alpha
    assert res.threshold in SMALL_GRID["threshold"]
    if res.feasible:
        assert res.false_positives <= 1
        assert res.saturated <= 0.5
    assert 0.0 <= res.cv_accuracy <= 1.0 and 0.0 <= res.cv_fpr <= 1.0
    assert 0.0 <= res.cv_agreement <= 1.0
    assert set(res.edge_params) <= {"none_floor", "temperature", "threshold"}
    assert res.catalog_version == catalog.version
    assert res.embedder == local.embedder_id(HashingEmbedder())


def test_calibrate_returns_params_and_threshold(cases, catalog, small_result):
    cal = [c for c in cases if c.split == "cal"]
    params, threshold = calibrate(cal, SMALL_GRID, embedder=HashingEmbedder(), catalog=catalog)
    assert isinstance(params, LocalParams)
    assert (params, threshold) == (small_result.params, small_result.threshold)


def test_grid_search_matches_run_eval(cases, catalog, small_result):
    """The fast threshold sweep agrees with a real router run at the chosen point."""
    cal = [c for c in cases if c.split == "cal"]
    res = small_result
    dec = LocalJevDecider(
        embedder=HashingEmbedder(), params=res.params, native_examples=catalog.native_examples
    )
    rep = run_eval(lambda: make_router(dec, catalog, threshold=res.threshold), cal)
    assert rep.accuracy == pytest.approx(res.accuracy)
    assert rep.fpr == pytest.approx(res.fpr)


def test_grid_edge_is_reported(cases, catalog):
    cal = [c for c in cases if c.split == "cal"]
    grid = {"none_floor": [0.3], "temperature": [0.08, 0.1], "threshold": [0.4, 0.6]}
    res = grid_search(cal, grid, embedder=HashingEmbedder(), catalog=catalog)
    assert "temperature" in res.edge_params  # a 2-value axis is always on an edge
    assert "none_floor" not in res.edge_params  # a fixed axis is not searched


def _rank(acc_rows, fp_rows, tiebreak, allowed=None, max_fp=1):
    correct = np.array(acc_rows, dtype=bool)
    fps = np.array(fp_rows, dtype=bool)
    allowed = np.ones(len(correct), bool) if allowed is None else np.array(allowed)
    return list(rank_candidates(correct, fps, allowed, np.array(tiebreak, float), max_fp))


def test_rank_prefers_accuracy_then_conservative_and_softer():
    # columns: threshold, none_floor, temperature, not_for_penalty
    same = [[1, 1, 0, 0]] * 3
    nofp = [[0, 0, 0, 0]] * 3
    tb = [[0.5, 0.3, 0.08, 1.0], [0.5, 0.3, 0.2, 1.0], [0.6, 0.3, 0.08, 1.0]]
    assert _rank(same, nofp, tb)[0] == 2  # higher threshold first
    assert _rank(same[:2], nofp[:2], tb[:2])[0] == 1  # then the higher temperature
    better = [[1, 1, 1, 0], [1, 1, 0, 0]]
    assert _rank(better, nofp[:2], tb[:2])[0] == 0  # accuracy beats tie-breaks


def test_rank_fp_bound_and_allowed():
    correct = [[1, 1, 1, 1], [1, 1, 0, 0], [1, 1, 1, 0]]
    fps = [[0, 0, 1, 1], [0, 0, 0, 0], [0, 0, 0, 1]]  # 2, 0, 1 false positives
    tb = [[0.5, 0.3, 0.1, 1.0]] * 3
    assert _rank(correct, fps, tb)[0] == 2  # best accuracy with <= 1 FP
    assert _rank(correct, fps, tb, allowed=[True, True, False])[0] == 1
    # nothing feasible: fewest FPs first
    assert _rank(correct, fps, tb, allowed=[False] * 3)[0] == 1


def test_write_and_load_calibration(tmp_path, monkeypatch, catalog, small_result):
    res = small_result
    path = tmp_path / "calibration.json"
    write_calibration({"hashing": res}, path)
    write_calibration({"model2vec": res}, path)  # merges, keeps hashing
    data = json.loads(path.read_text())
    assert set(data) >= {"hashing", "model2vec"}
    block = data["hashing"]
    assert block["threshold"] == res.threshold
    assert block["catalog_version"] == catalog.version
    assert block["embedder"] == local.embedder_id(HashingEmbedder())
    assert {"cv_accuracy", "cv_fpr", "edge_params", "feasible", "saturated"} <= set(block)

    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    if not res.feasible:
        pytest.skip("small grid found no feasible point")
    params, threshold = local.load_calibration("hashing")
    assert params == res.params
    assert threshold == res.threshold
    d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params == res.params
    assert d.recommended_threshold == res.threshold
    # explicit params always win
    d2 = LocalJevDecider(embedder=HashingEmbedder(), params=LocalParams())
    assert d2.params == LocalParams()
    # make_router picks up the recommended threshold
    r = make_router("local", catalog, embedder=HashingEmbedder())
    assert r.config.threshold == pytest.approx(res.threshold)


def _block(**over):
    block = {
        "none_floor": 0.11,
        "temperature": 0.2,
        "threshold": 0.3,
        "feasible": True,
        "catalog_version": load_catalog().version,
        "embedder": local.embedder_id(HashingEmbedder()),
    }
    return block | over


def _write(tmp_path, monkeypatch, data):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    return path


def test_unit_tests_do_not_see_shipped_calibration():
    assert local.CALIBRATION_PATH != local.DEFAULT_CALIBRATION_PATH
    d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params == LocalParams()
    assert d.recommended_threshold is None


def test_no_calibration_file_keeps_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "CALIBRATION_PATH", tmp_path / "missing.json")
    d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params == LocalParams()
    assert d.recommended_threshold is None
    assert local.load_calibration("hashing") is None


def test_calibration_picked_by_actual_embedder(tmp_path, monkeypatch):
    m2v = local.embedder_id(Model2VecEmbedder())
    _write(tmp_path, monkeypatch, {"hashing": _block(), "model2vec": _block(embedder=m2v)})
    assert local.embedder_key(HashingEmbedder()) == "hashing"
    assert local.embedder_key(Model2VecEmbedder()) == "model2vec"
    assert local.embedder_key(object()) is None
    assert m2v == "model2vec:minishlab/potion-base-8M"
    assert LocalJevDecider(embedder=HashingEmbedder()).params.none_floor == 0.11
    assert LocalJevDecider(embedder=object()).params == LocalParams()


@pytest.mark.parametrize(
    "over",
    [
        {"catalog_version": "some-older-catalog"},
        {"embedder": "hashing:dim=1024,char=3-5"},
        {"feasible": False},
    ],
)
def test_mismatched_or_infeasible_calibration_falls_back(tmp_path, monkeypatch, caplog, over):
    _write(tmp_path, monkeypatch, {"hashing": _block(**over)})
    with caplog.at_level(logging.WARNING, logger="agent_router.deciders.local"):
        d = LocalJevDecider(embedder=HashingEmbedder())
    assert d.params == LocalParams()
    assert d.recommended_threshold is None
    assert "using defaults" in caplog.text


def test_explicit_catalog_version_is_checked(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {"hashing": _block()})
    assert LocalJevDecider(embedder=HashingEmbedder(), catalog_version="other").params == (
        LocalParams()
    )
    ok = LocalJevDecider(embedder=HashingEmbedder(), catalog_version=load_catalog().version)
    assert ok.params.none_floor == 0.11


def test_corrupt_calibration_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    path.write_text("{not json")
    monkeypatch.setattr(local, "CALIBRATION_PATH", path)
    assert local.load_calibration("hashing") is None


def test_shipped_calibration_matches_catalog_and_embedders(shipped_calibration, catalog):
    data = json.loads(shipped_calibration.read_text())
    ids = {
        "model2vec": "model2vec:minishlab/potion-base-8M",
        "hashing": local.embedder_id(HashingEmbedder()),
    }
    for key, emb_id in ids.items():
        block = data[key]
        assert {"none_floor", "temperature", "threshold", "alpha", "not_for_penalty"} <= set(block)
        assert block["catalog_version"] == catalog.version, "re-run `agent-router calibrate`"
        assert block["embedder"] == emb_id
        assert block["alpha"] == LocalParams().alpha
    assert data["model2vec"]["feasible"] is True
    # an infeasible block is shipped for the record but never applied
    hashing = LocalJevDecider(embedder=HashingEmbedder())
    if data["hashing"]["feasible"]:
        assert hashing.recommended_threshold == data["hashing"]["threshold"]
    else:
        assert hashing.params == LocalParams() and hashing.recommended_threshold is None


# Honest regression floor for the local model2vec classifier ALONE, set from the holdout
# measured after the conservative calibration (see task-7-report.md, fix round 1):
# floor = measured accuracy - 0.05, ceiling = measured FPR + 0.05. The product targets
# TARGET_ACCURACY / TARGET_FPR are asserted on the local -> Jev cascade path, not here.
MODEL2VEC_HOLDOUT_MIN_ACCURACY = 0.74  # measured 0.797 (n=59); 0.797 (n=64, context cases)
MODEL2VEC_HOLDOUT_MAX_FPR = 0.22  # measured 0.167 (4/24); 0.148 (4/27 negatives)


@pytest.mark.model
def test_calibrated_model2vec_holdout(catalog, shipped_calibration):
    data = json.loads(shipped_calibration.read_text())
    assert "model2vec" in data, "run `agent-router calibrate` first"
    emb = Model2VecEmbedder()
    emb.load()
    router = make_router("local", catalog, embedder=emb)
    assert router.decider.recommended_threshold is not None, "calibration was not applied"
    holdout = load_cases(split="test")
    rep = run_eval(lambda: router, holdout)
    assert rep.errors == 0
    assert rep.accuracy >= MODEL2VEC_HOLDOUT_MIN_ACCURACY, rep.summary()
    assert rep.fpr <= MODEL2VEC_HOLDOUT_MAX_FPR, rep.summary()


# --- the default decision path: local -> Jev cascade ----------------------------------------


def test_shipped_cascade_calibration_matches_local_block(shipped_calibration, catalog):
    data = json.loads(shipped_calibration.read_text())
    assert "cascade" in data, "run `agent-router calibrate-cascade`"
    block, m2v = data["cascade"], data["model2vec"]
    assert block["feasible"] is True
    assert block["catalog_version"] == catalog.version
    assert block["embedder"] == m2v["embedder"]
    # the gate is only meaningful for the local params it was fit with
    assert block["local_params"] == {k: m2v[k] for k in block["local_params"]}
    assert 0.0 < block["native_gate"] <= 1.01
    assert block["cal_accuracy"] >= block["cal_jev_accuracy"]
    assert block["cal_fpr"] <= block["cal_jev_fpr"]


@pytest.mark.live
def test_cascade_holdout_meets_targets(catalog, shipped_calibration, monkeypatch):
    """The default path on the holdout: TARGET_ACCURACY / TARGET_FPR. Calls Jev (needs
    OPENROUTER_API_KEY or TYPESAFE_API_KEY) and the model2vec weights. Run once, with -s."""
    from agent_router.deciders.cascade import CascadeDecider
    from agent_router.evaluate import routing_stats

    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "model2vec")
    data = json.loads(shipped_calibration.read_text())
    router = make_router("cascade", catalog, timeout=15.0)
    dec = router.decider
    assert isinstance(dec, CascadeDecider)
    assert dec.native_gate == data["cascade"]["native_gate"], "cascade calibration not applied"
    assert dec.primary.recommended_threshold is not None, "local calibration not applied"
    assert router.config.threshold == data["cascade"]["threshold"]
    rep = run_eval(lambda: router, load_cases(split="test"))
    stats = routing_stats(rep)
    print(f"\ncascade holdout: {rep.summary()} {json.dumps(stats)}")
    for r in rep.results:
        if r.predicted != r.expected:
            print(f"  miss {r.id}: expected {r.expected}, got {r.predicted} via {r.backend}")
    assert rep.errors == 0
    assert stats["fallbacks"] == 0, "Jev failed during the holdout; the score is not Jev's"
    assert rep.accuracy >= TARGET_ACCURACY, rep.summary()
    assert rep.fpr <= TARGET_FPR, rep.summary()
