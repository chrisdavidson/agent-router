# Research notes

These notes explain the design choices behind agent-router:

- the Jev API it mirrors
- what it takes from Tenjin
- the router and tool-retrieval literature
- local alternatives to Jev

Measured results are in the [README](../README.md#backends-and-results).


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
\n
## Jev (TypeSafe)

- **What it is.** Jev is TypeSafe's hosted "System One" decision model. It launched on 2026-09-15.
  It is proprietary: no weights and no license to self-host.
- **Question primitives.** Jev answers three kinds of question (docs.typesafe.ai/primitives):
  - `choice`: pick one of several options
  - `noul`: yes / no
  - `score`: a value on a spectrum
- **What agent-router uses.** Only `choice`. Its answer is `{type: "choice", choice,
  probabilities, confidence}`: the most likely option, a distribution over all options, and a
  confidence from 0 to 1.
- **API shape.**
  - Endpoint: `POST https://api.typesafe.ai/v1/systemone`, model `jev-latest`. OpenRouter serves
    the same model as `~typesafe/jev-latest` at `POST https://openrouter.ai/api/alpha/decisions`.
  - Request body: `{"state": ..., "model": ..., "questions": {"route": {"type": "choice",
    "instructions": ..., "criteria": {id: {what, not_for?, examples?}}}}}`.
  - Response: `answers.route`.
  - A question takes at most 255 options.
- **No built-in abstain.** Jev has no `none` option. Its docs suggest adding one yourself, so
  agent-router always adds `none` ("the agent's own tools are enough").
- **Cost and latency.** Measured here at about $0.000015 per decision through OpenRouter.
  Latency on the 59-case holdout: median 231 ms, mean 240 ms.
- **Timeout used here.** The runtime default is 2 s. The eval runs used 15 s.

## Inspiration: Tenjin

[BackTrackCo/tenjin-agent](https://github.com/BackTrackCo/tenjin-agent) is licensed as "Other"
and requires a CLA. **agent-router took design ideas from it and reused no code.** The ideas:

- Hook into the agent at the prompt, at web tools and at subagent calls.
- At each hook, ask Jev a `choice` question over a fixed catalog instead of letting an LLM write
  the suggestion.
- Surface the result as a single one-line suggestion that the agent may ignore.

agent-router keeps that shape and changes three things:

- The catalog is MIT-only, and the loader enforces it.
- The default decider is an offline MIT classifier. Jev is the confirming stage of a cascade.
- Hints are templates over catalog fields, so no model output reaches the agent.

## Router literature

| Work | arXiv / source | License | Idea | Used here |
|---|---|---|---|---|
| RouteLLM | 2406.18665 | Apache-2.0 | Learns routers from preference data to send each query to a strong or a weak LLM | Framing: a cheap classifier decides and a threshold trades quality for cost. No code used |
| semantic-router (aurelio-labs) | GitHub | MIT | Embeds example utterances per route and picks the route by nearest-neighbour similarity | The `semantic-router` backend. The local decider uses the same exemplar approach |
| Gorilla | 2305.15334 | Apache-2.0 | An LLM fine-tuned with retrieval to write API calls | Background: retrieval over a tool catalog |
| ToolLLM | 2307.16789 | Apache-2.0 | Tool use over 16k+ real APIs, with an API retriever | Background: tool retrieval as a separate stage |
| Toolshed | 2410.14594 | paper | RAG-style tool knowledge bases for scaling tool-equipped agents | Background: `what` / `examples` per tool as retrieval text |
| ToolRet | 2503.01763 | paper | Benchmark that shows IR models struggle at tool retrieval | Reason to calibrate and to test on decoys |
| RAG-MCP | 2505.03275 | paper | Retrieves MCP tools before prompting, to cut prompt bloat and selection errors | Same goal: offer one relevant tool instead of all of them |
| MCP-Zero | 2506.01056 | MIT | Lets the agent request tools on demand | Contrast: here the router proposes tools and the agent chooses |
| ScaleMCP | 2505.06416 | paper | Dynamic MCP tool retrieval with auto-synchronising tool stores | Background |
| SkillRouter | 2603.22455 | MIT | A 1.2B retrieve-and-rerank model routes to skills in large registries using the skills' bodies (74.0% Hit@1) | Skill routing as a classification step. Our catalog is small, so exemplars suffice |
| "Skill or Skip?" (SelSkill) | 2606.00510 | paper | Learns *when* to invoke a skill or skip it, using uncertainty to pick decision points | Why `none` is a first-class option and FPR is a headline metric |
| Conformal abstention | 2405.01563 | paper | Calibrated abstention with conformal guarantees | Motivates calibrated thresholds and an explicit `none`. We do not use conformal sets yet |
| RouteNLP | 2604.23577 | paper | A closed-loop router with conformal cascading: a small model first, escalating on calibrated confidence | Direct model for the `cascade`: local first, escalating to Jev unless p(none) ≥ a gate fitted on the cal split |
| NeMo Guardrails | GitHub | Apache-2.0 | A programmable rail layer between the user and the LLM | Hook-layer pattern. Not bundled |
| Llama Guard | Meta | Llama license | An LLM used as a classifier with a fixed label set | The constrained-label pattern ("can only point, never write"). Not bundled (license) |

Where the table says "paper", no code license applies because nothing was reused. Only the MIT and
Apache-2.0 projects ship code, and none of that code is vendored here.
