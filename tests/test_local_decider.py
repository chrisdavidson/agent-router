import json
import logging
import math
import zlib

import numpy as np
import pytest

from agent_router.core.catalog import load_catalog
from agent_router.core.types import NONE_ID, OptionSpec
from agent_router.deciders import embedders
from agent_router.deciders.base import MAX_OPTIONS, DeciderError
from agent_router.deciders.embedders import (
    HashingEmbedder,
    Model2VecEmbedder,
    default_embedder,
)
from agent_router.deciders.local import LocalJevDecider, LocalParams

NONE_OPT = OptionSpec(what="")


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def options(catalog):
    return {NONE_ID: NONE_OPT, **{e.id: e.option() for e in catalog.entries}}


@pytest.fixture(scope="module")
def decider(catalog):
    return LocalJevDecider(embedder=HashingEmbedder(), native_examples=catalog.native_examples)


def _check_contract(result, options):
    assert result.choice in options
    assert set(result.probabilities) == set(options)
    assert math.isclose(sum(result.probabilities.values()), 1.0, abs_tol=1e-9)
    assert all(0.0 <= p <= 1.0 for p in result.probabilities.values())
    assert 0.0 <= result.confidence <= 1.0
    assert result.choice == max(result.probabilities, key=result.probabilities.get)
    assert result.backend == "local"
    assert result.latency_ms >= 0.0


# --- HashingEmbedder -------------------------------------------------------


def test_hashing_rows_normalised_and_deterministic():
    emb = HashingEmbedder()
    a = emb.encode(["compute 2**200 exactly", "git status"])
    b = HashingEmbedder().encode(["compute 2**200 exactly", "git status"])
    assert a.shape == (2, 2**14)
    np.testing.assert_allclose(np.linalg.norm(a, axis=1), 1.0, rtol=1e-6)
    np.testing.assert_array_equal(a, b)


def test_hashing_uses_process_stable_hash():
    # Pin the bucket to crc32 so results do not depend on PYTHONHASHSEED.
    assert HashingEmbedder.bucket("w:git") == zlib.crc32(b"w:git") % 2**14
    vec = HashingEmbedder().encode(["git"])[0]
    assert vec[HashingEmbedder.bucket("w:git")] > 0


def test_hashing_empty_text_is_zero_row():
    vec = HashingEmbedder().encode(["", "!!!"])
    assert not np.isnan(vec).any()
    # "!!!" still has char n-grams; "" has none.
    assert np.linalg.norm(vec[0]) == 0.0


def test_hashing_similar_texts_closer_than_unrelated():
    v = HashingEmbedder().encode(
        ["count lines of code by language", "count the lines of python code", "git status"]
    )
    assert v[0] @ v[1] > v[0] @ v[2]


# --- default_embedder ------------------------------------------------------


def test_default_embedder_env_hashing(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")
    assert isinstance(default_embedder(), HashingEmbedder)


def test_default_embedder_falls_back_on_load_failure(monkeypatch, caplog):
    monkeypatch.delenv("AGENT_ROUTER_EMBEDDER", raising=False)

    def boom(self):
        raise OSError("no network")

    monkeypatch.setattr(Model2VecEmbedder, "load", boom)
    with caplog.at_level(logging.WARNING, logger=embedders.__name__):
        emb = default_embedder()
    assert isinstance(emb, HashingEmbedder)
    assert "falling back" in caplog.text


def test_default_embedder_explicit_model2vec_also_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "model2vec")
    monkeypatch.setattr(Model2VecEmbedder, "load", lambda self: (_ for _ in ()).throw(OSError()))
    with caplog.at_level(logging.WARNING, logger=embedders.__name__):
        assert isinstance(default_embedder(), HashingEmbedder)


def test_default_embedder_unknown_value_raises(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "word2vec")
    with pytest.raises(ValueError, match="AGENT_ROUTER_EMBEDDER"):
        default_embedder()


# --- LocalJevDecider: contract --------------------------------------------


def test_params_defaults():
    p = LocalParams()
    assert (p.alpha, p.none_floor, p.temperature, p.not_for_penalty) == (0.8, 0.35, 0.07, 0.5)


def test_contract_and_backend(decider, options):
    assert decider.name == "local"
    for text in ["compute 2**200 exactly", "git status", "hello there", "jq .name x.json"]:
        _check_contract(decider.decide(text, options), options)


def test_probabilities_are_plain_floats_json_serialisable(decider, options):
    r = decider.decide("compute 2**200 exactly", options)
    assert all(type(p) is float for p in r.probabilities.values())
    assert type(r.confidence) is float
    json.dumps({"p": r.probabilities, "c": r.confidence, "ms": r.latency_ms})


def test_missing_none_raises(decider, options):
    opts = {k: v for k, v in options.items() if k != NONE_ID}
    with pytest.raises(DeciderError):
        decider.decide("compute 2**200 exactly", opts)


def test_too_many_options_raises(decider):
    opts = {NONE_ID: NONE_OPT, **{f"o{i}": OptionSpec(what=f"option {i}") for i in range(255)}}
    assert len(opts) == MAX_OPTIONS + 1
    with pytest.raises(DeciderError):
        decider.decide("anything", opts)


def test_max_options_allowed(decider):
    opts = {NONE_ID: NONE_OPT, **{f"o{i}": OptionSpec(what=f"option {i}") for i in range(254)}}
    _check_contract(decider.decide("option 7", opts), opts)


def test_only_none_option_gives_full_confidence(decider):
    r = decider.decide("anything", {NONE_ID: NONE_OPT})
    assert r.choice == NONE_ID
    assert r.probabilities == {NONE_ID: 1.0}
    assert r.confidence == 1.0


def test_empty_state_is_valid_and_abstains(decider, options):
    r = decider.decide("", options)
    _check_contract(r, options)
    assert r.choice == NONE_ID


def test_embedder_failure_becomes_decider_error(options):
    class Broken:
        def encode(self, texts):
            raise RuntimeError("boom")

    with pytest.raises(DeciderError):
        LocalJevDecider(embedder=Broken()).decide("x", options)


# --- LocalJevDecider: behaviour -------------------------------------------


def test_catalog_example_picks_exact_calc(decider, options):
    r = decider.decide("compute 2**200 exactly", options)
    assert r.choice == "exact-calc"


def test_native_example_picks_none(decider, options):
    r = decider.decide("git status", options)
    assert r.choice == NONE_ID


def test_without_native_examples_git_status_still_valid(options):
    r = LocalJevDecider(embedder=HashingEmbedder()).decide("git status", options)
    _check_contract(r, options)


# Held-out paraphrases (not in catalog.yaml), written before the implementation.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is 3**50 exactly", "exact-calc"),
        ("count lines of code in src by language", "repo-stats"),
        ("convert help.html to markdown", "html-to-markdown"),
        ("git diff", NONE_ID),
        ("run the linter", NONE_ID),
    ],
)
def test_held_out_paraphrases(decider, options, text, expected):
    assert decider.decide(text, options).choice == expected


def test_deterministic_across_calls(decider, options):
    a = decider.decide("how many lines of python are in src", options)
    b = decider.decide("how many lines of python are in src", options)
    assert a.choice == b.choice
    assert a.probabilities == b.probabilities
    assert a.confidence == b.confidence


def test_deterministic_across_instances(catalog, options):
    mk = lambda: LocalJevDecider(  # noqa: E731
        embedder=HashingEmbedder(), native_examples=catalog.native_examples
    )
    assert (
        mk().decide("jq keys", options).probabilities
        == mk().decide("jq keys", options).probabilities
    )


def test_not_for_penalty_lowers_probability():
    state = "symbolic calculus derivative of x squared"
    base = OptionSpec(what="exact arithmetic and math evaluation", examples=("compute 2**200",))
    penalised = OptionSpec(what=base.what, examples=base.examples, not_for=(state,))
    d = LocalJevDecider(embedder=HashingEmbedder())
    p0 = d.decide(state, {NONE_ID: NONE_OPT, "calc": base}).probabilities["calc"]
    p1 = d.decide(state, {NONE_ID: NONE_OPT, "calc": penalised}).probabilities["calc"]
    assert p1 < p0


def test_none_option_own_examples_count():
    opts = {
        NONE_ID: OptionSpec(what="", examples=("deploy to production",)),
        "calc": OptionSpec(what="exact arithmetic", examples=("compute 2**200",)),
    }
    r = LocalJevDecider(embedder=HashingEmbedder()).decide("deploy to production", opts)
    assert r.choice == NONE_ID


def test_higher_none_floor_increases_abstention(options):
    lo = LocalJevDecider(embedder=HashingEmbedder(), params=LocalParams(none_floor=0.0))
    hi = LocalJevDecider(embedder=HashingEmbedder(), params=LocalParams(none_floor=0.9))
    text = "what is 3**50 exactly"
    assert (
        hi.decide(text, options).probabilities[NONE_ID]
        > lo.decide(text, options).probabilities[NONE_ID]
    )


def test_exemplar_embeddings_are_cached(catalog, options):
    calls: list[int] = []

    class Counting(HashingEmbedder):
        def encode(self, texts):
            calls.append(len(texts))
            return super().encode(texts)

    d = LocalJevDecider(embedder=Counting(), native_examples=catalog.native_examples)
    d.decide("first", options)
    first = sum(calls)
    calls.clear()
    d.decide("second", options)
    assert sum(calls) == 1  # only the state is encoded the second time
    assert first > 1


# --- Model2Vec (downloads weights) -----------------------------------------


@pytest.mark.model
def test_model2vec_rows_normalised():
    emb = Model2VecEmbedder()
    v = emb.encode(["compute 2**200 exactly", "git status", "convert page.html to markdown"])
    assert v.ndim == 2 and v.shape[0] == 3 and v.shape[1] > 0
    np.testing.assert_allclose(np.linalg.norm(v, axis=1), 1.0, rtol=1e-5)
