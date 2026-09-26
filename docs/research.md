# Research notes

## Local Jev alternatives

TypeSafe Jev's `choice` primitive (one option, a probability per option, a confidence) can
be approximated locally with the "Jev in 25 lines" technique: list the options as letters,
ask a small instruction-tuned LLM for the single best letter, read the next-token logits
of the letter tokens and normalise them (`l - logaddexp.reduce(l)`). agent-router ships
this as the `logprob` backend (local llama.cpp GGUF, default `unsloth/Qwen3-0.6B-GGUF`
`Qwen3-0.6B-Q4_K_M.gguf`, extra `llm`) and the `openrouter` backend (same readout over any
OpenAI-compatible `/chat/completions` with `top_logprobs`). Both live in
`src/agent_router/deciders/logprob.py` and are MIT.

| Project | License | Popularity | What it is | Use here |
|---|---|---|---|---|
| NobodyWho, "Jev in 25 lines" (nobodywho.ai blog; HN item 49812769) | blog post | HN front page | The letter-logit readout above, with numpy normalisation | Re-implemented as `logprob` / `openrouter` (MIT) |
| AnyJev (github.com/MorrisZJ/AnyJev, PyPI `anyjev`) | Apache-2.0 | 769★ | Any causal LM as a Jev-style model; L0 debiasing (cyclic-shift marginalisation, label-prior correction), L1 temperature scaling | **NON-MIT optional plugin**: `anyjev` backend, extra `anyjev` (pulls torch + transformers). Our `permutations>1` borrows the L0 idea |
| Kev (jaredpalmer/kev) | Apache-2.0 | 7.1k★ | Jev-like decision library | Reference only |
| Laya (NandhaKishorM/laya) | Apache-2.0 | 25k★ | Jev-like local decision model | Reference only |
| jevlike (vinnylarouge/jevlike) | MIT | 1.3k★ | MIT Jev-style classifier; needs training, no published text checkpoint | Not usable out of the box |
| zlh1992/jev_local_qwen | none stated | — | Local Qwen Jev clone | Not usable (no license) |

Notes:

- The `anyjev` adapter (`src/agent_router/deciders/anyjev_backend.py`) is MIT glue code
  only; anyjev itself is Apache-2.0 and is imported lazily, only when selected. It
  defaults to `device="cpu"` (anyjev's `HFBackend` defaults to CUDA) and `prior="none"`
  (the `batch` prior is stateful across calls).
- Small models lean towards answering the word "no"/"none" instead of a letter when the
  prompt says "choose none"; the prompt therefore uses a neutral question and describes
  the abstain option in words. On `compute 2**200 exactly` with 3 options, Qwen3-0.6B
  Q4_K_M gives exact-calc 0.91 / none 0.07 / json-query 0.01 (2026-09-26).

### OpenRouter

- Jev itself is on OpenRouter as `~typesafe/jev-latest`, a "decisions" model served only
  by `POST https://openrouter.ai/api/alpha/decisions`, not by `chat/completions`. See the
  `jev` backend (`deciders/typesafe.py`). `typesafe/jev-router` is a different product
  (an LLM-selection router), not the `choice` classifier.
- The `openrouter` logprob backend calls `https://openrouter.ai/api/v1/chat/completions`
  with `model="qwen/qwen3.7-flash"`, `max_tokens=1, temperature=0, logprobs=true,
  top_logprobs=20, reasoning={"enabled": false}, provider={"require_parameters": true}`.
  Without `reasoning` disabled the content is `None`. Verified 2026-09-26: top_logprobs
  `[('A',-0.043),('C',-3.418),(' A',-5.043),('B',-6.293),(' C',-7.293)]` for the calc
  question. `"A"` and `" A"` are merged by logsumexp; letters missing from top_logprobs
  get the smallest logprob seen minus 5.
- The Alibaba provider caps `top_logprobs` at 5 (HTTP 400 "Range of top_logprobs should
  be [0, 5]"); the backend retries once with 5 when that happens.
