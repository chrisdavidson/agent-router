# Tool gaps (offline measurement)

Counts, hosts and construct names only; no prompt or command text. Regenerate with
`python3 integrations/first-principles/tool_gaps.py --write` (or `make tool-gaps`).
Measured 2026-10-17 over 70 trace files: 71 agent runs in 70 sessions, from the hooks' state and
the saved runs (`runs/*/state`, untracked; a snapshot of this checkout's recordings, not
reproducible from a fresh clone).

## What the router's checkpoints did

Every checkpoint in the audit logs, by where it fired and what the router made of it.

| Checkpoint / outcome | Count |
|---|---|
| prompt / acted on | 14 |
| prompt / classified none | 59 |
| prompt / skip pattern | 36 |
| tool / acted on | 16 |
| tool / classified none | 135 |
| tool / did not fit | 296 |
| tool / own tool | 71 |
| tool / skip pattern | 920 |

The agents also used the catalog's calculator 628 times; that
is covered, so it is not counted below.

## What the agent kept doing

One row per pattern; each call counts once, in the first pattern it matches. *Router* is
what the router made of those calls: `did not fit` (checked, no catalog entry fits),
`skip pattern`, `classified none`, `acted on`, or `not checked` (WebFetch / WebSearch
are not routed, and older traces have no call id to join).

| Pattern | Calls | Failed | Runs | Sessions | Router | Candidate |
|---|---|---|---|---|---|---|
| Multi-step compute scripts | 197 | 2 | 56 | 55 | 132 did not fit, 65 not checked | **yes** |
| Sources that came back without the content | 67 | 19 | 25 | 24 | 67 not checked | **yes** |
| Reading documents (PDF) as text | 42 | 4 | 18 | 17 | 15 did not fit, 27 not checked | **yes** |
| Fetching pages with curl / wget | 30 | 4 | 13 | 13 | 20 did not fit, 10 not checked | **yes** |
| Repository history and search (git, gh) | 22 | 0 | 7 | 7 | 18 did not fit, 4 not checked | **yes** |
| Looking at files (ls, cat, grep, sed -n, ...) | 102 | 1 | 31 | 30 | 72 did not fit, 30 not checked | housekeeping |
| Housekeeping (date, echo, mkdir, cd, ...) | 27 | 0 | 10 | 9 | 16 did not fit, 11 not checked | housekeeping |
| Other shell commands | 26 | 0 | 15 | 14 | 22 did not fit, 4 not checked | housekeeping |

A candidate is a pattern that is not housekeeping, with at least 5 calls
in at least 2 sessions.

## Candidates

### Multi-step compute scripts

- **Need:** exact results from a short script (imports, loops, several printed values).
- **Proposal:** extend calc_script, or a sandboxed script runner.
- **Evidence:** 197 calls (2 failed) in 56 runs and 55 sessions; router: 132 did not fit, 65 not checked.
- **Hosts:** www.fincen.gov (1), www.legis.state.pa.us (1).

### Sources that came back without the content

- **Need:** the fact at its source when the page is blocked, gone or lacks it.
- **Proposal:** a source fallback: an archived copy or an alternate source.
- **Evidence:** 67 calls (19 failed) in 25 runs and 24 sessions; router: 67 not checked.
- **Hosts:** www.osti.gov (8), atb.nrel.gov (7), en.wikipedia.org (5), www.oregon.gov (5), developer.nrel.gov (5), www.ftb.ca.gov (4), www.sos.nm.gov (2), www.multco.us (2).

### Reading documents (PDF) as text

- **Need:** the text of a PDF or other document, to search or quote.
- **Proposal:** a document-to-text tool: fetch a PDF or file and return its text.
- **Evidence:** 42 calls (4 failed) in 18 runs and 17 sessions; router: 15 did not fit, 27 not checked.
- **Hosts:** www.ftb.ca.gov (5), sos.wyo.gov (3), www.oregon.gov (2), www.projectlibre.com (1), wyoleg.gov (1), www.pa.gov (1), www.osti.gov (1), sam.nrel.gov (1).

### Fetching pages with curl / wget

- **Need:** a page's own text (WebFetch returns a small model's summary instead).
- **Proposal:** a raw fetch tool: the page's text, not a summary of it.
- **Evidence:** 30 calls (4 failed) in 13 runs and 13 sessions; router: 20 did not fit, 10 not checked.
- **Hosts:** developer.nrel.gov (7), www.irs.gov (5), raw.githubusercontent.com (3), pages.stern.nyu.edu (3), www.deertrailinnovationgroup.com (2), taxfoundation.org (2), www.palegis.us (1), www.pa.gov (1).

### Repository history and search (git, gh)

- **Need:** what a repository says or said at a version.
- **Proposal:** a repository history / search tool.
- **Evidence:** 22 calls (0 failed) in 7 runs and 7 sessions; router: 18 did not fit, 4 not checked.

## Reading it

A candidate is a need that recurs with no catalog entry to meet it, not a decision that
a tool should be built. The next step stores candidates and lets the router classify
against them in shadow (recorded, never shown to the agent), so how often each would
have been the right call is measured before anything is added to the catalog.
