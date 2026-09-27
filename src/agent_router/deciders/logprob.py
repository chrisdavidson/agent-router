"""Logprob Jev decider: "Jev in 25 lines" (nobodywho.ai) over a small LLM.

The prompt lists the options as letters ``A``, ``B``, ... (``none`` last), each with its
``what`` and up to two examples, and asks for the single best letter. The next-token
scores of the letter tokens are read (``"A"`` and ``" A"`` merged by logsumexp), then::

    logprobs      = l - numpy.logaddexp.reduce(l)
    probabilities = exp(logprobs)          # keyed by option id
    confidence    = 1 - H(p) / log(n)

``permutations > 1`` is AnyJev-L0-style debiasing: the options are shown in that many
cyclic rotations and the per-option probabilities are averaged, so a model that favours
whatever sits at ``A`` no longer wins by position alone.

Engines:

- ``llama_cpp`` (registry ``logprob``): a local GGUF via llama-cpp-python, default
  ``unsloth/Qwen3-0.6B-GGUF`` / ``Qwen3-0.6B-Q4_K_M.gguf``. The model's own chat template
  is rendered with ``enable_thinking=False`` so the next token is the answer letter.
  ``pip install agent-router[llm]``.
- ``openai`` (registry ``openrouter``): any OpenAI-compatible ``/chat/completions`` with
  ``logprobs``/``top_logprobs``; default OpenRouter ``qwen/qwen3.7-flash`` with
  ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

import os
import string
import time
from collections.abc import Iterable, Sequence
from typing import Any, Literal, Protocol

import httpx
import numpy as np

from agent_router.core.types import NONE_ID, ChoiceResult, OptionSpec
from agent_router.deciders._math import entropy_confidence
from agent_router.deciders.base import DeciderError
from agent_router.deciders.typesafe import NONE_WHAT

Engine = Literal["llama_cpp", "openai"]

LETTERS = string.ascii_uppercase
MAX_LETTER_OPTIONS = len(LETTERS)
MISSING_LETTER_PENALTY = 5.0
FALLBACK_TOP_LOGPROBS = 5

SYSTEM = (
    "You route an AI agent's step to a tool. Reply with the single letter of the best "
    "option only: no words, no punctuation."
)

QUESTION = "Which option best matches this agent step?"

DEFAULT_REPO_ID = "unsloth/Qwen3-0.6B-GGUF"
DEFAULT_FILENAME = "Qwen3-0.6B-Q4_K_M.gguf"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3.7-flash"
LLM_HINT = "local logprob backend needs llama-cpp-python: pip install agent-router[llm]"


class TokenLogitsModel(Protocol):
    """What the llama_cpp engine needs; ``LlamaCppModel`` adapts a ``llama_cpp.Llama``."""

    chat_template: str | None

    def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
        """Token ids of ``text``."""
        ...

    def next_logits(self, tokens: Sequence[int], prompt: str) -> np.ndarray:
        """Full-vocabulary logits at the position after ``tokens`` (``prompt`` is their text)."""
        ...


class LlamaCppModel:
    """Adapter from ``llama_cpp.Llama`` to ``TokenLogitsModel``.

    llama-cpp-python 0.3.x no longer copies logits into ``Llama.scores`` unless
    ``logits_all=True`` (which costs n_ctx x n_vocab floats), so the last position's logits
    are read straight from the context with ``get_logits_ith(-1)``.
    """

    def __init__(self, llm: Any) -> None:
        self.llm = llm
        self.chat_template = (getattr(llm, "metadata", None) or {}).get("tokenizer.chat_template")

    def tokenize(self, text: bytes, add_bos: bool = True, special: bool = False) -> list[int]:
        return list(self.llm.tokenize(text, add_bos=add_bos, special=special))

    def next_logits(self, tokens: Sequence[int], prompt: str) -> np.ndarray:
        n_ctx = self.llm.n_ctx()
        if len(tokens) >= n_ctx:
            raise DeciderError(f"prompt is {len(tokens)} tokens, context is {n_ctx}")
        self.llm.reset()
        self.llm.eval(list(tokens))
        ptr = self.llm._ctx.get_logits_ith(-1)
        return np.ctypeslib.as_array(ptr, shape=(self.llm.n_vocab(),)).astype(np.float64)


# -- prompt ------------------------------------------------------------------


def letter_order(options: dict[str, OptionSpec]) -> list[str]:
    """Option ids in letter order: catalog order, ``none`` last."""
    if len(options) > MAX_LETTER_OPTIONS:
        raise DeciderError(
            f"{len(options)} options exceeds the letter readout maximum of {MAX_LETTER_OPTIONS}"
        )
    ids = [oid for oid in options if oid != NONE_ID]
    if NONE_ID in options:
        ids.append(NONE_ID)
    return ids


def describe_option(oid: str, spec: OptionSpec) -> str:
    what = (spec.what or "").strip() or (NONE_WHAT if oid == NONE_ID else oid)
    examples = [e for e in spec.examples if e and e.strip()][:2]
    if examples:
        what += " (e.g. " + "; ".join(examples) + ")"
    return what


def build_messages(
    state: str, options: dict[str, OptionSpec], order: Sequence[str]
) -> tuple[str, str]:
    """(system, user) messages showing ``order[j]`` as letter ``LETTERS[j]``."""
    # Neutral wording, no bare word "none": small models otherwise answer "no"/"none"
    # instead of a letter, or lean towards the abstain option.
    lines = ["Agent step:", state.strip() or "(empty)", "", QUESTION, "Options:"]
    lines += [f"{LETTERS[j]}. {describe_option(oid, options[oid])}" for j, oid in enumerate(order)]
    lines.append("Answer with one letter.")
    return SYSTEM, "\n".join(lines)


def render_chat(template: str | None, system: str, user: str) -> str:
    """Render the model's chat template with thinking disabled; plain text if none."""
    if not template:
        return f"{system}\n\n{user}\nAnswer:"
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    def raise_exception(message: str) -> None:
        raise ValueError(message)

    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
    env.globals["raise_exception"] = raise_exception
    return env.from_string(template).render(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        add_generation_prompt=True,
        enable_thinking=False,
        bos_token="",
        eos_token="",
    )


def merge_letter_logprobs(pairs: Iterable[tuple[str, float]], n: int) -> dict[str, float]:
    """Merge ``(token, logprob)`` pairs into one logprob per letter among the first ``n``.

    ``"A"``, ``" A"`` and ``"\\nA"`` all count as ``A`` (logsumexp); other tokens are ignored.
    """
    allowed = set(LETTERS[:n])
    out: dict[str, float] = {}
    for token, lp in pairs:
        letter = token.strip()
        if letter not in allowed:
            continue
        out[letter] = float(np.logaddexp(out[letter], lp)) if letter in out else float(lp)
    return out


# -- decider -----------------------------------------------------------------


class LogprobJevDecider:
    name = "logprob"

    def __init__(
        self,
        repo_id: str = DEFAULT_REPO_ID,
        filename: str = DEFAULT_FILENAME,
        permutations: int = 1,
        llm: Any = None,
        engine: Engine = "llama_cpp",
        n_ctx: int = 2048,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout: float = 5.0,
        client: httpx.Client | None = None,
        top_logprobs: int = 20,
    ) -> None:
        if engine not in ("llama_cpp", "openai"):
            raise ValueError(f"engine must be llama_cpp or openai, not {engine!r}")
        if permutations < 1:
            raise ValueError("permutations must be >= 1")
        self.engine: Engine = engine
        self.name = "openrouter" if engine == "openai" else "logprob"
        self.repo_id = repo_id
        self.filename = filename
        self.permutations = permutations
        self.n_ctx = n_ctx
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self._client = client
        self.top_logprobs = top_logprobs
        self._llm: TokenLogitsModel | None = None
        if llm is not None:
            self._llm = llm if hasattr(llm, "next_logits") else LlamaCppModel(llm)
        self._letter_ids: dict[str, list[int]] = {}
        self._llm_from_hub = False
        self._served: str | None = None
        self.last_prompt = ""

    # -- decide ------------------------------------------------------------

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        start = time.perf_counter()
        if NONE_ID not in options:
            raise DeciderError(f"options must include {NONE_ID!r}")
        order = letter_order(options)
        n = len(order)
        score = self._llama_scores if self.engine == "llama_cpp" else self._openai_scores

        total = dict.fromkeys(order, 0.0)
        rotations = min(self.permutations, n)
        for s in range(rotations):
            perm = order[s:] + order[:s]
            system, user = build_messages(state, options, perm)
            lg = np.asarray(score(system, user, n), dtype=np.float64)
            probs = np.exp(lg - np.logaddexp.reduce(lg))
            for oid, p in zip(perm, probs, strict=True):
                total[oid] += float(p) / rotations

        z = sum(total.values())
        probabilities = {oid: total[oid] / z for oid in options}
        choice = max(order, key=lambda oid: probabilities[oid])
        if self.engine == "llama_cpp":
            backend = f"logprob:{self.filename}" if self._llm_from_hub else "logprob"
        else:
            backend = f"{self.name}:{self._served or self.model}"
        return ChoiceResult(
            choice=choice,
            probabilities=probabilities,
            confidence=entropy_confidence(probabilities.values()),
            backend=backend,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    # -- llama.cpp engine --------------------------------------------------

    def _load(self) -> TokenLogitsModel:
        if self._llm is not None:
            return self._llm
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise DeciderError(LLM_HINT) from exc
        try:
            llm = Llama.from_pretrained(
                repo_id=self.repo_id,
                filename=self.filename,
                n_ctx=self.n_ctx,
                logits_all=False,
                verbose=False,
            )
        except ImportError as exc:  # huggingface-hub missing
            raise DeciderError(LLM_HINT) from exc
        except Exception as exc:
            raise DeciderError(f"could not load {self.repo_id}/{self.filename}: {exc}") from exc
        self._llm = LlamaCppModel(llm)
        self._llm_from_hub = True
        return self._llm

    def _ids_for_letters(self, llm: TokenLogitsModel, n: int) -> list[list[int]]:
        out = []
        for letter in LETTERS[:n]:
            if letter not in self._letter_ids:
                ids: list[int] = []
                for variant in (letter, " " + letter):
                    toks = llm.tokenize(variant.encode(), add_bos=False, special=False)
                    if len(toks) == 1 and toks[0] not in ids:
                        ids.append(toks[0])
                if not ids:
                    raise DeciderError(f"letter {letter!r} is not a single token for this model")
                self._letter_ids[letter] = ids
            out.append(self._letter_ids[letter])
        return out

    def _llama_scores(self, system: str, user: str, n: int) -> list[float]:
        llm = self._load()
        try:
            prompt = render_chat(llm.chat_template, system, user)
            self.last_prompt = prompt
            tokens = llm.tokenize(prompt.encode(), add_bos=True, special=True)
            letter_ids = self._ids_for_letters(llm, n)
            logits = np.asarray(llm.next_logits(tokens, prompt), dtype=np.float64)
        except DeciderError:
            raise
        except Exception as exc:
            raise DeciderError(f"llama.cpp readout failed: {type(exc).__name__}: {exc}") from exc
        return [float(np.logaddexp.reduce(logits[ids])) for ids in letter_ids]

    # -- OpenAI-compatible engine -----------------------------------------

    def _post(self, url: str, body: dict[str, Any], key: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {key}"}
        try:
            if self._client is not None:
                return self._client.post(url, json=body, headers=headers, timeout=self.timeout)
            with httpx.Client(timeout=self.timeout) as client:
                return client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise DeciderError(f"logprob request failed: {type(exc).__name__}: {exc}") from exc

    def _openai_scores(self, system: str, user: str, n: int) -> list[float]:
        key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise DeciderError("no API key for the openai logprob engine: set OPENROUTER_API_KEY")
        url = self.base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": self.top_logprobs,
            "reasoning": {"enabled": False},
            "provider": {"require_parameters": True},
        }
        self.last_prompt = user
        resp = self._post(url, body, key)
        if (
            resp.status_code == 400
            and "top_logprobs" in resp.text
            and body["top_logprobs"] > FALLBACK_TOP_LOGPROBS
        ):
            # Some providers (e.g. Alibaba on OpenRouter, 2026-09-26) cap top_logprobs at 5.
            body["top_logprobs"] = FALLBACK_TOP_LOGPROBS
            resp = self._post(url, body, key)
        if not resp.is_success:
            raise DeciderError(
                f"logprob endpoint returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            data = resp.json()
            top = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
            pairs = [(str(t["token"]), float(t["logprob"])) for t in top]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DeciderError(f"no top_logprobs in response: {exc!r}") from exc
        self._served = data.get("model") if isinstance(data, dict) else None
        merged = merge_letter_logprobs(pairs, n)
        if not merged:
            raise DeciderError("no option letter among the top_logprobs")
        # Letters outside the top-k get a floor: the smallest logprob seen over the WHOLE
        # top_logprobs list (letters or not), minus MISSING_LETTER_PENALTY.
        floor = min(lp for _, lp in pairs) - MISSING_LETTER_PENALTY
        return [merged.get(letter, floor) for letter in LETTERS[:n]]
