# Prompt: add a machine-readable summary block to the first-principles report

For: the agent that maintains `~/Projects/first-principles-skill` (plugin `first-principles`,
currently 9.14.0). From: agent-router's first-principles integration, which reads the agent's
reports. Read this whole file before starting; the **Done when** section is the test.

---

## The task

Make the `first-principles:first-principles` agent end every analysis report with one fenced
JSON block that states, in fixed fields, the decisions the prose already contains: the
assumptions and their verdicts, the ground truths and whether each was read at source, the
chains and their confidence, the Self-Audit Gate's scores for **every** pass, whether any
re-entry edge fired, and the recommended conclusion with its confidence.

The block adds no new reasoning. It restates what the report already says, in a form a program
can read without guessing. The prose stays the deliverable; the block sits in the existing
`## Appendix — process output` area, which the template already reserves for process output.

## Why

agent-router keeps a decision trace of each run (`integrations/first-principles/trace.py` in
`~/Projects/agent-router`). Today it recovers those decisions by pattern-matching the report's
prose. Every new scenario words the same fact differently, so the parser keeps missing things or
misreading them. In the 14 worked-example reruns of 2026-09-29 (all complete, all gates
cleared), it still got these wrong:

| Example | Report says | Parser concluded |
|---|---|---|
| personal-general | "The Fix/Repeat loop did not fire, and no re-entry edge fired during the run." | re-entry **fired**, from the §4 sentence "There was therefore no Phase 2 re-entry" |
| software-systems | "**Disclosed:** The Self-Audit Gate's Fix/Repeat edge fired once." | no re-entry recorded |
| 7 of the 8 runs that re-scored | a first scoring pass, then a Fix, then a second pass | 1 pass; the first pass's bands are gone because the gate section was rewritten in place |
| product-business-2, estimate-fermi | "That pass already cleared the gate" / "Result: gate cleared" | no gate result line |
| science-engineering, self-application | "…has three parts (chains C3, C4):" followed by a list | the recommendation cut off at the colon |

The parser was patched for one wording of a re-entry denial in the last commit before this run,
and the next run produced another. More patterns will not end this: the prose varies with the
scenario, and it should. A fixed block written by the agent that made the decisions will.

## What the block must contain

Design the exact schema yourself and ship it as a file in `shared/` (for example
`shared/spine/references/summary-schema.json`, emitted like the other spine references). It must
carry at least the following, using the vocabulary the template and rubric already define, not
new words:

- `schema_version`: an integer, starting at 1. Later changes add fields only; a removed or
  renamed field bumps it.
- `run_mode`: the Step 0 mode the run used (e.g. `full-composer`), exactly as Step 0 names it.
- `assumptions`: one item per Assumptions Table row: `id` (`A-1`…), `type` (`physical law`,
  `current constraint`, `convention`, `untested belief`), `verdict` (`Accept`, `Challenge`,
  `Discard`).
- `ground_truths`: one item per ground truth: `id` (`GT-1`…) and `read_at_source` (false exactly
  when the report writes it `GT-N?`).
- `chains`: `id` (`C1`…), `confidence` (`HIGH`, `MEDIUM`, `LOW`), and the ground-truth and chain
  ids it rests on.
- `dead_ends`: the name of each §5 dead end.
- `techniques`: which companion techniques were applied, and for each one not applied, its phase
  and the reason given.
- `gate`: `passes`: a list with one entry per scoring pass, **in order, including a pass that
  was later rewritten**. Each entry holds the six criteria's bands (`Absent`, `Hand-wavy`,
  `Sound`, `Rigorous`) and whether that pass cleared both the gate and the Hand-wavy cap. Also
  `fix_repeat_fired` (boolean) and `cleared` (the final result).
- `re_entry`: `fired` (boolean), and, when true, which edge and what triggered it, in one short
  sentence. `fired` is a statement of fact, not a phrase to be searched: false means no edge
  fired anywhere in the run.
- `conclusion`: the recommendation in full (all of it, including any list it introduces) and its
  confidence.

Every id in the block must be one the prose uses, and every value must agree with the prose. If
they disagree, the prose is wrong or the block is wrong; either way it is a defect the checker
below must catch.

Keep within the template's existing rules: the block is process output about the analysis, not
environment state (no model, tool, session or permission facts). Where it goes in the Appendix,
and whether the analysis file or the agent's final message also carries it, is your call. Say
which in the template.

## Constraints

- Edit `shared/` only, then `python3 scripts/sync-content.py --write`. Never hand-edit the
  generated `first-principles/` tree.
- Move all version stamps in lockstep (VERSION-01) and add a `CHANGELOG.md` entry.
- Do not change the methodology: no phase, criterion, band or verdict changes. The block
  restates decisions; it must not add a step that changes them.
- Do not make the block the deliverable. A reader who ignores it loses nothing.
- Keep the added cost small. Measure the report's length and the run's cost before and after on
  the same scenarios, and report both.

## How to test it

1. **Offline checker.** Add `scripts/check-summary-block.py` with a `--self-test` mode (no live
   session, stdlib plus whatever the other checkers already use), and register it in the
   firewall battery like the other gates. Given a report, it must:
   - find exactly one block and parse it;
   - validate it against the schema;
   - cross-check it against the prose: ids exist in their sections; each chain's confidence
     matches its `**Confidence:**` line; each assumption's type and verdict match its table row;
     `GT-N?` matches `read_at_source: false`; the last pass's bands match the
     `## Self-Audit Gate (process output)` section; `cleared` follows from the bands by the
     rubric's own rule (no `Absent`, at most one `Hand-wavy`); the conclusion's confidence
     matches §6.

   Its self-test fixtures must include, as controls that must **fail**:
   - a missing block, two blocks, and malformed JSON;
   - a chain confidence that disagrees with its `**Confidence:**` line;
   - `re_entry.fired: true` on a report whose gate says no edge fired (the personal-general case
     above);
   - `re_entry.fired: false` on a report that discloses a Fix/Repeat (the software-systems case);
   - `gate.passes` with one entry on a report that shows a first scoring pass before its Fix;
   - a `conclusion` cut short of the list it introduces.

   The same reports with a correct block must pass.

2. **Worked examples.** Add a correct block to each of the 14 `shared/examples/*.md`, since the
   agent learns the format from them, and run the checker over all 14.

3. **Live runs.** Rerun the 14 worked examples through the agent (your
   `tests/example-rerun/run_examples.py`, or agent-router's
   `integrations/first-principles/run_examples.py --jobs 3 --out <dir>`, which also records
   cost and turns). Run the checker over every report produced.

4. **Regression.** Run `bash scripts/check-firewall-battery.sh`, `python3
   scripts/sync-content.py --check` and `claude plugin validate ./first-principles`.

## Done when

- [ ] The schema file exists in `shared/`, is emitted by sync, and the output template tells the
      agent where the block goes and what it holds.
- [ ] `scripts/check-summary-block.py --self-test` passes, with every control listed above
      failing for the right reason, and it runs in the firewall battery.
- [ ] All 14 worked examples carry a block that passes the checker.
- [ ] In a live rerun of the 14 examples, **14 of 14** reports carry exactly one block that
      passes the checker, including its cross-checks against the prose.
- [ ] In that rerun, the gate still clears at least as often as in the 2026-09-29 baseline
      (14/14), and median cost per run rises by no more than 10% against that baseline
      ($2.73; per-example figures are in agent-router's
      `integrations/first-principles/runs/2026-09-29-examples-latest/summary.md`).
- [ ] The firewall battery is green, sync shows no drift, the plugin validates, version stamps
      agree, and the CHANGELOG says what the block is for.
- [ ] Your final report lists: the schema (fields and enums), where the block is written, the
      14-run table (block present / checker result / cost / words, before and after), and any
      run where the block and the prose disagreed, with which one was wrong.

If a live run falls short (say 13 of 14), do not loosen the checker to pass it. Report the
failing run, what the block got wrong, and whether the template, the example, or the checker
needs the change.

## After this ships (not part of this task)

agent-router's `trace.py` will read the block when present and fall back to prose parsing for
older reports, recording which source each run's decisions came from.
