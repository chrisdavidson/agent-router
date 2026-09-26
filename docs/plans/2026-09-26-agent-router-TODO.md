# agent-router MVP — TODO

Plan: `docs/superpowers/plans/2026-09-26-agent-router.md` · Spec: `docs/superpowers/specs/2026-09-26-agent-router-design.md`
Branch: `feat/router-mvp`

- [x] Research: Jev/TypeSafe API, Tenjin reference (non-MIT, ideas only), arxiv/OSS router survey, SDK hook probes
- [x] Decisions: own Jev-spec decider + plugins · advisory (enforce optional) · offline MIT tools · Python/uv
- [x] Spec + plan written
- [x] Task 1: Foundation (types, catalog, decider protocol, catalog.yaml)
- [x] Task 1b: catalog tests
- [x] Task 2: Local Jev-spec decider
- [x] Task 3: Catalog tools, MCP server, commit-writer skill
- [x] Task 4: Router, hints, audit, config
- [x] Task 5: Hosted Jev + semantic-router backends, adapter docs
- [x] Task 5b: Local Qwen logprob backend + AnyJev adapter (Reddit/HN variants)
- [x] Task 6: Claude SDK adapter + inner agent runner (+ live test)
- [x] Task 7: Eval set, calibration, CLI
- [x] Task 8: Visual demo (playground / live / replay)
- [x] Task 10: Cascade decider local→Jev as default (user decision)
- [x] Task 9: README, Makefile, docs, verification
- [x] Final fix wave (whole-branch + docs review)
  - [x] A1 local decider scores the current step only; eval context cases; re-measured holdout
  - [x] A2 CLI/demo honour AGENT_ROUTER_* env (mode, threshold, disabled, audit)
  - [x] A3 docs/adapters.md: deny carries `hint`, enforce at tool point only
  - [x] B1–B6 Jev error wrapping, unknown choice recorded as none, decider-error reason, research table, bs4 dep, cache lock
  - [x] B7–B11 README results/config, architecture rules and stage schema, sample audit, Makefile route, this TODO
- [ ] Open the PR to the project owner
