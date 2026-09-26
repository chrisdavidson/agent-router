import json
import math
import os
import re
import sys

import httpx
import numpy as np
import pytest

from agent_router.core.types import NONE_ID, OptionSpec
from agent_router.deciders.base import DeciderError
from agent_router.deciders.logprob import (
    LogprobJevDecider,
    build_messages,
    letter_order,
    merge_letter_logprobs,
)

OPTIONS = {
    NONE_ID: OptionSpec(what=""),
    "exact-calc": OptionSpec(
        what="Exact arithmetic",
        examples=("compute 2**200 exactly", "what is 17% of 2,340"),
    ),
    "json-query": OptionSpec(what="Query JSON files with JMESPath"),
}

_LINE = re.compile(r"^([A-Z])\. (.*)$", re.M)


class FakeLlm:
    """Scripted stand-in for the token/logits model protocol.

    Letter ``X`` tokenizes to id ``ord(X)`` and `` X`` to ``ord(X) + 100``; vocab is 256.
    ``score(what) -> float`` gives the content logit of the option whose ``what`` line
    starts with that text; ``position_bias[j]`` is added to the letter at position j.
    """

    chat_template = None

    def __init__(self, score, position_bias=(), space_share=0.0):
        self.score = score
        self.position_bias = position_bias
        self.space_share = space_share
        self.prompts: list[str] = []

    def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False):
        s = text.decode()
        if len(s) == 1 and s.isupper():
            return [ord(s)]
        if len(s) == 2 and s[0] == " " and s[1].isupper():
            return [ord(s[1]) + 100]
        return [1, 2, 3]

    def next_logits(self, tokens, prompt: str):
        self.prompts.append(prompt)
        logits = np.full(256, -50.0)
        for j, (letter, what) in enumerate(_LINE.findall(prompt)):
            bias = self.position_bias[j] if j < len(self.position_bias) else 0.0
            logit = self.score(what) + bias
            logits[ord(letter)] = logit
            if self.space_share:
                # split the letter's mass between "A" and " A" (same total)
                logits[ord(letter)] = logit + math.log(1 - self.space_share)
                logits[ord(letter) + 100] = logit + math.log(self.space_share)
        return logits


def _scorer(table):
    def score(what):
        for prefix, val in table.items():
            if what.startswith(prefix):
                return val
        return 0.0

    return score


def _check_contract(result, options):
    assert result.choice in options
    assert set(result.probabilities) == set(options)
    assert math.isclose(sum(result.probabilities.values()), 1.0, abs_tol=1e-9)
    assert all(p >= 0 for p in result.probabilities.values())
    assert 0.0 <= result.confidence <= 1.0


# -- prompt / letters --------------------------------------------------------


def test_letter_order_puts_none_last():
    assert letter_order(OPTIONS) == ["exact-calc", "json-query", NONE_ID]


def test_letter_order_rejects_more_than_26():
    opts = {f"o{i}": OptionSpec(what=f"w{i}") for i in range(26)} | {NONE_ID: OptionSpec("")}
    with pytest.raises(DeciderError, match="26"):
        letter_order(opts)


def test_build_messages_lists_letters_whats_and_examples():
    system, user = build_messages("compute 2**200", OPTIONS, letter_order(OPTIONS))
    assert "letter" in system.lower()
    assert "compute 2**200" in user
    assert "A. Exact arithmetic" in user
    assert "compute 2**200 exactly" in user  # an example
    assert "B. Query JSON files with JMESPath" in user
    assert re.search(r"^C\. \S", user, re.M)  # none gets a non-empty description
    assert "D." not in user


def test_merge_letter_logprobs_logsumexp_of_variants():
    merged = merge_letter_logprobs([("A", -0.043), ("C", -3.418), (" A", -5.043), ("B", -6.293)], 3)
    assert math.isclose(merged["A"], np.logaddexp(-0.043, -5.043))
    assert merged["C"] == -3.418
    assert merged["B"] == -6.293


def test_merge_letter_logprobs_ignores_out_of_range_letters_and_words():
    merged = merge_letter_logprobs([("A", -1.0), ("D", -0.1), ("Answer", -0.2), (" b", -3)], 2)
    assert set(merged) == {"A"}


# -- llama.cpp engine (fake) -------------------------------------------------


def test_fake_llm_maps_letters_to_options_and_normalises():
    llm = FakeLlm(_scorer({"Exact": 3.0, "Query": 0.0}))
    d = LogprobJevDecider(llm=llm)
    result = d.decide("compute 2**200 exactly", OPTIONS)
    _check_contract(result, OPTIONS)
    assert result.choice == "exact-calc"
    lg = np.array([3.0, 0.0, 0.0])  # A=exact-calc, B=json-query, C=none
    expected = np.exp(lg - np.logaddexp.reduce(lg))
    assert math.isclose(result.probabilities["exact-calc"], expected[0], rel_tol=1e-9)
    assert math.isclose(result.probabilities[NONE_ID], expected[2], rel_tol=1e-9)
    assert result.backend.startswith("logprob")
    assert d.name == "logprob"


def test_space_variant_mass_is_merged():
    plain = LogprobJevDecider(llm=FakeLlm(_scorer({"Exact": 2.0})))
    split = LogprobJevDecider(llm=FakeLlm(_scorer({"Exact": 2.0}), space_share=0.3))
    a = plain.decide("x", OPTIONS).probabilities
    b = split.decide("x", OPTIONS).probabilities
    for oid in OPTIONS:
        assert math.isclose(a[oid], b[oid], rel_tol=1e-9)


def test_confidence_is_one_minus_normalised_entropy():
    d = LogprobJevDecider(llm=FakeLlm(_scorer({})))  # all equal -> uniform
    result = d.decide("x", OPTIONS)
    assert math.isclose(result.confidence, 0.0, abs_tol=1e-9)
    sharp = LogprobJevDecider(llm=FakeLlm(_scorer({"Exact": 40.0}))).decide("x", OPTIONS)
    assert sharp.confidence > 0.99


def test_permutations_average_out_position_bias():
    # content prefers json-query slightly; position A gets a large bonus
    llm = FakeLlm(_scorer({"Query": 1.0}), position_bias=(3.0, 0.0, 0.0))
    single = LogprobJevDecider(llm=llm).decide("x", OPTIONS)
    assert single.choice == "exact-calc"  # biased: whatever sits at A wins

    llm2 = FakeLlm(_scorer({"Query": 1.0}), position_bias=(3.0, 0.0, 0.0))
    debiased = LogprobJevDecider(llm=llm2, permutations=3).decide("x", OPTIONS)
    _check_contract(debiased, OPTIONS)
    assert debiased.choice == "json-query"
    assert len(llm2.prompts) == 3
    # every option occupied position A exactly once
    firsts = {_LINE.findall(p)[0][1] for p in llm2.prompts}
    assert len(firsts) == 3


def test_permutations_capped_at_option_count():
    llm = FakeLlm(_scorer({}))
    LogprobJevDecider(llm=llm, permutations=10).decide("x", OPTIONS)
    assert len(llm.prompts) == 3


def test_permutations_must_be_positive():
    with pytest.raises(ValueError):
        LogprobJevDecider(llm=FakeLlm(_scorer({})), permutations=0)


def test_options_must_include_none():
    d = LogprobJevDecider(llm=FakeLlm(_scorer({})))
    with pytest.raises(DeciderError):
        d.decide("x", {"exact-calc": OPTIONS["exact-calc"]})


def test_llm_failure_becomes_decider_error():
    class Boom(FakeLlm):
        def next_logits(self, tokens, prompt):
            raise RuntimeError("ctx overflow")

    d = LogprobJevDecider(llm=Boom(_scorer({})))
    with pytest.raises(DeciderError, match="ctx overflow"):
        d.decide("x", OPTIONS)


def test_missing_llama_cpp_is_decider_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    d = LogprobJevDecider()  # constructing never loads anything
    with pytest.raises(DeciderError, match=r"agent-router\[llm\]"):
        d.decide("x", OPTIONS)


def test_render_uses_chat_template_with_thinking_disabled():
    tmpl = (
        "{% for m in messages %}<|{{ m.role }}|>{{ m.content }}{% endfor %}"
        "{% if add_generation_prompt %}<|assistant|>"
        "{% if enable_thinking is defined and not enable_thinking %}<think></think>{% endif %}"
        "{% endif %}"
    )

    class Templated(FakeLlm):
        chat_template = tmpl

    llm = Templated(_scorer({}))
    LogprobJevDecider(llm=llm).decide("x", OPTIONS)
    assert llm.prompts[0].startswith("<|system|>")
    assert llm.prompts[0].endswith("<|assistant|><think></think>")


# -- openai engine (OpenRouter) ----------------------------------------------

LIVE_CHAT = {
    "id": "gen-1",
    "model": "qwen/qwen3.7-flash",
    "choices": [
        {
            "message": {"role": "assistant", "content": "A"},
            "logprobs": {
                "content": [
                    {
                        "token": "A",
                        "logprob": -0.043,
                        "top_logprobs": [
                            {"token": "A", "logprob": -0.043},
                            {"token": "C", "logprob": -3.418},
                            {"token": " A", "logprob": -5.043},
                            {"token": "B", "logprob": -6.293},
                            {"token": " C", "logprob": -7.293},
                        ],
                    }
                ]
            },
        }
    ],
}


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def _client(payload, seen, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_request_shape_and_parse(no_keys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: list[httpx.Request] = []
    d = LogprobJevDecider(engine="openai", client=_client(LIVE_CHAT, seen))
    assert d.name == "openrouter"
    result = d.decide("compute 2**200 exactly", OPTIONS)

    (req,) = seen
    assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer sk-or-test"
    body = json.loads(req.content)
    assert body["model"] == "qwen/qwen3.7-flash"
    assert body["max_tokens"] == 1
    assert body["temperature"] == 0
    assert body["logprobs"] is True
    assert body["top_logprobs"] == 20
    assert body["reasoning"] == {"enabled": False}
    assert body["provider"] == {"require_parameters": True}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]

    _check_contract(result, OPTIONS)
    assert result.choice == "exact-calc"
    lg = np.array([np.logaddexp(-0.043, -5.043), -6.293, np.logaddexp(-3.418, -7.293)])
    expected = np.exp(lg - np.logaddexp.reduce(lg))
    assert math.isclose(result.probabilities["exact-calc"], expected[0], rel_tol=1e-9)
    assert math.isclose(result.probabilities["json-query"], expected[1], rel_tol=1e-9)
    assert math.isclose(result.probabilities[NONE_ID], expected[2], rel_tol=1e-9)
    assert "qwen/qwen3.7-flash" in result.backend


def test_openai_missing_letter_gets_floor(no_keys):
    payload = json.loads(json.dumps(LIVE_CHAT))
    payload["choices"][0]["logprobs"]["content"][0]["top_logprobs"] = [
        {"token": "A", "logprob": -0.1},
        {"token": "Sure", "logprob": -4.0},
        {"token": "C", "logprob": -2.5},
    ]
    d = LogprobJevDecider(engine="openai", api_key="k", client=_client(payload, []))
    result = d.decide("x", OPTIONS)
    _check_contract(result, OPTIONS)
    lg = np.array([-0.1, -4.0 - 5.0, -2.5])  # B floor = min over all top_logprobs - 5
    expected = np.exp(lg - np.logaddexp.reduce(lg))
    assert math.isclose(result.probabilities["json-query"], expected[1], rel_tol=1e-9)


def test_openai_no_key_is_decider_error(no_keys):
    d = LogprobJevDecider(engine="openai", client=_client(LIVE_CHAT, []))
    with pytest.raises(DeciderError, match="OPENROUTER_API_KEY"):
        d.decide("x", OPTIONS)


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [{"message": {"content": None}, "logprobs": None}]},
        {
            "choices": [
                {"logprobs": {"content": [{"top_logprobs": [{"token": "Hi", "logprob": -1}]}]}}
            ]
        },
        {"error": "nope"},
    ],
)
def test_openai_unusable_response_is_decider_error(no_keys, payload):
    d = LogprobJevDecider(engine="openai", api_key="k", client=_client(payload, []))
    with pytest.raises(DeciderError):
        d.decide("x", OPTIONS)


def test_openai_retries_with_5_when_provider_caps_top_logprobs(no_keys):
    seen: list[httpx.Request] = []
    capped = {"error": {"message": "Range of top_logprobs should be [0, 5]"}}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if json.loads(request.content)["top_logprobs"] > 5:
            return httpx.Response(400, json=capped)
        return httpx.Response(200, json=LIVE_CHAT)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    d = LogprobJevDecider(engine="openai", api_key="k", client=client)
    assert d.decide("x", OPTIONS).choice == "exact-calc"
    assert [json.loads(r.content)["top_logprobs"] for r in seen] == [20, 5]


def test_openai_http_error_is_decider_error(no_keys):
    d = LogprobJevDecider(engine="openai", api_key="k", client=_client({}, [], status=429))
    with pytest.raises(DeciderError, match="429"):
        d.decide("x", OPTIONS)


def test_unknown_engine():
    with pytest.raises(ValueError):
        LogprobJevDecider(engine="vllm")


# -- registry ----------------------------------------------------------------


def test_registry_builds_logprob_and_openrouter():
    from agent_router.core.catalog import load_catalog
    from agent_router.deciders.registry import BACKENDS, available_backends, make_decider

    assert {"logprob", "openrouter", "anyjev"} <= set(BACKENDS)
    assert {"logprob", "openrouter", "anyjev"} <= set(available_backends())
    catalog = load_catalog()
    lp = make_decider("logprob", catalog)
    assert isinstance(lp, LogprobJevDecider) and lp.engine == "llama_cpp"
    orr = make_decider("openrouter", catalog)
    assert isinstance(orr, LogprobJevDecider) and orr.engine == "openai"


# -- real models (opt-in) ----------------------------------------------------


@pytest.mark.live
def test_live_openrouter_logprob():
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    d = LogprobJevDecider(engine="openai", timeout=30.0)
    result = d.decide("compute 2**200 exactly", OPTIONS)
    print("\nopenrouter:", result)
    _check_contract(result, OPTIONS)
    assert result.choice == "exact-calc"


@pytest.mark.model
def test_model_llama_cpp_qwen3_gguf():
    pytest.importorskip("llama_cpp")
    pytest.importorskip("huggingface_hub")
    d = LogprobJevDecider()
    result = d.decide("compute 2**200 exactly", OPTIONS)
    print("\nllama.cpp:", result)
    print("prompt tail:", repr(d.last_prompt[-80:]))
    _check_contract(result, OPTIONS)
    assert result.choice == "exact-calc"
