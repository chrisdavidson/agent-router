import json
import math
import os

import httpx
import pytest

from agent_router.core.catalog import load_catalog
from agent_router.core.types import NONE_ID, OptionSpec
from agent_router.deciders.base import DeciderError
from agent_router.deciders.local import LocalJevDecider
from agent_router.deciders.registry import available_backends, make_decider
from agent_router.deciders.typesafe import INSTRUCTIONS, TypeSafeJevDecider

OPTIONS = {
    NONE_ID: OptionSpec(what=""),
    "exact-calc": OptionSpec(
        what="Exact arithmetic",
        not_for=("symbolic calculus",),
        examples=("compute 2**200 exactly", "what is 17% of 2,340"),
    ),
    "json-query": OptionSpec(what="Query JSON files with JMESPath"),
}

LIVE_SAMPLE = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {
        "route": {
            "type": "choice",
            "choice": "none",
            "probabilities": {"none": 0.59, "json-query": 0, "exact-calc": 0.41},
            "confidence": 0.39,
        }
    },
    "usage": {"input_tokens": 360, "output_tokens": 41, "cost": 0.00001512},
    "id": "gen-dec-123",
    "provider": "TypeSafe",
}


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def _client(handler, seen=None):
    def wrapped(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped))


def _ok(payload=LIVE_SAMPLE):
    return lambda request: httpx.Response(200, json=payload)


def _check_contract(result, options):
    assert result.choice in options
    assert set(result.probabilities) == set(options)
    assert math.isclose(sum(result.probabilities.values()), 1.0, abs_tol=1e-9)
    assert all(p >= 0 for p in result.probabilities.values())
    assert 0.0 <= result.confidence <= 1.0


# -- hosted Jev -------------------------------------------------------------


def test_jev_openrouter_request_shape_and_parse(no_keys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: list[httpx.Request] = []
    d = TypeSafeJevDecider(client=_client(_ok(), seen))
    result = d.decide("what is 3/7 + 5/11", OPTIONS)

    (req,) = seen
    assert req.method == "POST"
    assert str(req.url) == "https://openrouter.ai/api/alpha/decisions"
    assert req.headers["Authorization"] == "Bearer sk-or-test"
    body = json.loads(req.content)
    assert body["state"] == "what is 3/7 + 5/11"
    assert body["model"] == "~typesafe/jev-latest"
    q = body["questions"]["route"]
    assert q["type"] == "choice"
    assert q["instructions"] == INSTRUCTIONS
    assert set(q["criteria"]) == set(OPTIONS)
    assert q["criteria"]["exact-calc"] == {
        "what": "Exact arithmetic",
        "not_for": ["symbolic calculus"],
        "examples": ["compute 2**200 exactly", "what is 17% of 2,340"],
    }
    # empty lists are omitted
    assert q["criteria"]["json-query"] == {"what": "Query JSON files with JMESPath"}
    assert q["criteria"][NONE_ID]["what"]  # none gets a non-empty description

    assert d.name == "jev"
    assert result.choice == NONE_ID
    assert result.backend == "jev:typesafe/jev-1.13-20260917"
    assert math.isclose(result.confidence, 0.39)
    assert math.isclose(result.probabilities["exact-calc"], 0.41)
    _check_contract(result, OPTIONS)


def test_jev_typesafe_transport(no_keys, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    seen: list[httpx.Request] = []
    TypeSafeJevDecider(client=_client(_ok(), seen)).decide("x", OPTIONS)
    (req,) = seen
    assert str(req.url) == "https://api.typesafe.ai/v1/systemone"
    assert req.headers["Authorization"] == "Bearer ts-key"
    assert json.loads(req.content)["model"] == "jev-latest"


def test_jev_auto_prefers_openrouter(no_keys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-a")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-b")
    seen: list[httpx.Request] = []
    TypeSafeJevDecider(client=_client(_ok(), seen)).decide("x", OPTIONS)
    assert seen[0].url.host == "openrouter.ai"


def test_jev_explicit_transport_and_key(no_keys):
    seen: list[httpx.Request] = []
    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(_ok(), seen))
    d.decide("x", OPTIONS)
    assert seen[0].url.host == "api.typesafe.ai"
    assert seen[0].headers["Authorization"] == "Bearer k"


def test_jev_no_key_raises(no_keys):
    d = TypeSafeJevDecider(client=_client(_ok()))
    with pytest.raises(DeciderError, match="API_KEY"):
        d.decide("x", OPTIONS)


def test_jev_422_raises(no_keys):
    d = TypeSafeJevDecider(
        api_key="k",
        transport="typesafe",
        client=_client(lambda r: httpx.Response(422, json={"error": "bad criteria"})),
    )
    with pytest.raises(DeciderError, match="422"):
        d.decide("x", OPTIONS)


def test_jev_network_error_raises(no_keys):
    def boom(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(boom))
    with pytest.raises(DeciderError):
        d.decide("x", OPTIONS)


def test_jev_malformed_response_raises(no_keys):
    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(_ok({"answers": {}})))
    with pytest.raises(DeciderError):
        d.decide("x", OPTIONS)


def test_jev_choice_not_in_options_raises(no_keys):
    bad = json.loads(json.dumps(LIVE_SAMPLE))
    bad["answers"]["route"]["choice"] = "rm-rf"
    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(_ok(bad)))
    with pytest.raises(DeciderError, match="rm-rf"):
        d.decide("x", OPTIONS)


def test_jev_normalises_probabilities(no_keys):
    odd = json.loads(json.dumps(LIVE_SAMPLE))
    odd["answers"]["route"]["choice"] = "exact-calc"
    # json-query missing, sum != 1, an unknown key present
    odd["answers"]["route"]["probabilities"] = {"exact-calc": 0.6, "none": 0.2, "zzz": 0.5}
    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(_ok(odd)))
    result = d.decide("x", OPTIONS)
    _check_contract(result, OPTIONS)
    assert result.choice == "exact-calc"
    assert result.probabilities["json-query"] == 0.0
    assert math.isclose(result.probabilities["exact-calc"], 0.75)


def test_jev_requires_none_option(no_keys):
    d = TypeSafeJevDecider(api_key="k", transport="typesafe", client=_client(_ok()))
    with pytest.raises(DeciderError, match="none"):
        d.decide("x", {"exact-calc": OPTIONS["exact-calc"]})


@pytest.mark.live
def test_jev_live_openrouter():
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    catalog = load_catalog()
    options = {NONE_ID: OptionSpec(what=""), **{e.id: e.option() for e in catalog.entries}}
    d = TypeSafeJevDecider(transport="openrouter", timeout=30.0)
    result = d.decide("what's 3/7 + 5/11 as an exact fraction", options)
    print(
        f"\nlive jev: backend={result.backend} choice={result.choice} "
        f"confidence={result.confidence:.2f} latency_ms={result.latency_ms:.0f} "
        f"probabilities={result.probabilities}"
    )
    _check_contract(result, options)
    assert result.backend.startswith("jev:")


# -- semantic-router --------------------------------------------------------


def test_semantic_router_contract():
    pytest.importorskip("semantic_router")
    from agent_router.deciders.semantic_router_backend import SemanticRouterDecider

    d = SemanticRouterDecider(native_examples=("list the files in this folder", "run the tests"))
    assert d.name == "semantic-router"
    calc = d.decide("compute 2**200 exactly please", OPTIONS)
    _check_contract(calc, OPTIONS)
    assert calc.choice == "exact-calc"
    assert calc.backend == "semantic-router"

    none = d.decide("please run the tests", OPTIONS)
    _check_contract(none, OPTIONS)
    assert none.choice == NONE_ID

    # unseen vocabulary scores nothing: abstain to none
    unseen = d.decide("zzqx blorp", OPTIONS)
    _check_contract(unseen, OPTIONS)
    assert unseen.choice == NONE_ID


def test_semantic_router_requires_none_option():
    pytest.importorskip("semantic_router")
    from agent_router.deciders.semantic_router_backend import SemanticRouterDecider

    with pytest.raises(DeciderError):
        SemanticRouterDecider().decide("x", {"exact-calc": OPTIONS["exact-calc"]})


def test_semantic_router_missing_package(monkeypatch):
    import builtins

    from agent_router.deciders import semantic_router_backend

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "semantic_router" or name.startswith("semantic_router."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(DeciderError, match=r"agent-router\[semantic-router\]"):
        semantic_router_backend.SemanticRouterDecider()


# -- registry ---------------------------------------------------------------


def test_available_backends_no_keys(no_keys):
    avail = available_backends()
    assert avail["local"] is True
    assert avail["jev"] is False
    assert {"local", "semantic-router", "jev"} <= set(avail)


def test_available_backends_with_key(no_keys, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert available_backends()["jev"] is True


def test_make_decider_local_passes_native_examples(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")
    catalog = load_catalog()
    d = make_decider("local", catalog)
    assert isinstance(d, LocalJevDecider)
    assert d.native_examples == catalog.native_examples


def test_make_decider_jev_and_semantic_router(no_keys):
    catalog = load_catalog()
    assert isinstance(make_decider("jev", catalog), TypeSafeJevDecider)
    if available_backends()["semantic-router"]:
        d = make_decider("semantic-router", catalog)
        assert d.name == "semantic-router"
        assert d.native_examples == catalog.native_examples


def test_make_decider_unknown():
    with pytest.raises(ValueError, match="unknown"):
        make_decider("nope", load_catalog())


def test_jev_overall_deadline_bounds_a_slow_response(no_keys):
    import time

    def slow(request):
        time.sleep(0.6)
        return httpx.Response(200, json=LIVE_SAMPLE)

    d = TypeSafeJevDecider(api_key="sk-or-test", client=_client(slow), timeout=0.15)
    t0 = time.perf_counter()
    with pytest.raises(DeciderError, match="deadline"):
        d.decide("x", OPTIONS)
    assert time.perf_counter() - t0 < 0.45


def test_jev_uses_a_short_connect_timeout(no_keys):
    seen = []
    d = TypeSafeJevDecider(api_key="sk-or-test", client=_client(_ok(), seen), timeout=2.0)
    d.decide("x", OPTIONS)
    t = seen[0].extensions["timeout"]
    assert t["connect"] == 1.0 and t["read"] == 2.0
