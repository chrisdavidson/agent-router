**Disclosed:** One re-entry edge fired, the Self-Audit Gate's Fix/Repeat loop. Trigger: Criterion 3 scored Hand-wavy on the first pass, and Criteria 1, 4, 5 and 6 scored Sound. What changed:

- The Essence Statement became one sentence.
- Three HIGH chains (C10–C12) were added, built only from the definitional ground truths.
- Compound hops were split.
- Missing verification paths and assumption prices were added.
- One claim in §6 that no chain supported was cut.

The re-score cleared the gate.

## Answer

**Recommendation:** Keep the monolith. Shard the test suite (about 14.375 min on 8 shards), add changed-file test selection and rolling restarts, then raise deploy cadence under a 20-minute pipeline budget (chain C9).

**Band (from §6):** MEDIUM (chain C7, chain C9)

**Would change it:** 30 days of CI and merge history showing the real pipeline breakdown, the per-engineer wait, and the share of changes that cross domains (chain C5, chain C8).

## 1. Problem Essence

**Core problem:** Which constraint — the 45-minute pipeline, the 2-a-day deploy cadence, or the monolith's shape — actually limits how fast this team's changes reach production, and is splitting into microservices the cheapest, lowest-risk way to remove it, or neither necessary nor sufficient?

**Success criteria:**

1. Break the 45-minute pipeline and the 2-a-day cadence into their parts, and say which part makes up most of a change's lead time (from ready-to-ship to running in production).
2. Give every candidate a lead-time effect and an engineering cost, with all arithmetic shown and recomputed. The candidates are: keep things as they are, speed up the pipeline inside the monolith, split into microservices, and a combination.
3. Name the observations that would change the answer, including when extracting services *would* be justified.
4. Never raise the failure risk of the revenue path (catalog → cart → checkout → fulfillment) without saying so and putting a size on it.

Symptom versus cause: "deploys are too slow" describes a symptom and does not name a cause. "We need microservices" is a solution that leadership has stated as if it were a finding. It started this analysis but is not the question being answered. The criteria above say what the answer must achieve. None of them requires the answer to be "microservices: yes" or "microservices: no".

## 2. Assumptions Table

Inversion applied to leadership's claim. Claim: "splitting into microservices will make deploys fast enough." Inverted: "after the split, deploys are still not fast enough." Any one of these conditions guarantees that inverted outcome:

1. Most changes touch several services, so each change needs several ordered deploys.
2. Each service still needs the full end-to-end suite before anyone trusts a deploy.
3. Most of the lead time is spent waiting for the next batch, and a split does not change that.
4. Coordinating restarts gives way to coordinating versions across services.
5. The migration ties the team up for so long that the pipeline is still 45 minutes a year later.

Each condition depends on a precondition. All four are load-bearing and unverified:

- P1: most changes stay inside one domain (from condition 1).
- P2: a domain's own subset of tests is enough to trust a deploy (from condition 2).
- P3: pipeline duration, not the cadence policy, makes up most of the lead time (from condition 3).
- P4: the migration finishes within the planning horizon (from condition 5).

P1 → A-15, P2 → A-3 and A-11, P3 → A-5, P4 → A-9.

| Assumption | Type | Treatment | Verdict | Verification |
|------------|------|-----------|---------|--------------|
| A-1 — Slow deploys cost the business a material amount | untested belief | Verify or flag | Challenge — nobody has measured the cost; chain C5 puts it anywhere from 1.6% to 37.5% of engineering time | unverified — flagged GT-14? |
| A-2 — Microservices shorten deploy time | untested belief | Verify or flag | Challenge — a split only shrinks the set of tests each deploy runs, and sharding plus test selection do the same inside the monolith (chain C4) | derivation C4; rests on GT-12? |
| A-3 — Every deploy has to run the full test suite | convention | Challenge before use | Challenge — running everything on every deploy is a policy, and test sharding and changed-file test selection both relax it without touching the architecture | GT-4? (user-reported, unverified) |
| A-4 — Every deploy needs a coordinated restart of the application | convention | Challenge before use | Challenge — a rolling or blue-green restart of stateless app servers removes the coordination; this holds only while schema migrations stay backward compatible | GT-4? (user-reported, unverified) |
| A-5 — The 45-minute pipeline is what holds the cadence at 2 deploys a day | untested belief | Verify or flag | Discard — the pipeline can serially fit 480 / 45 = 10.67 deploys in a working day, more than five times the current 2 (chain C1) | C1 arithmetic, recomputed |
| A-6 — The pipeline splits into about 5 min setup, 35 min tests and 5 min deploy/restart | untested belief | Verify or flag | Challenge — this is an estimate, not a measurement, and chains C4 and C7 depend on it | unverified — flagged GT-12? |
| A-7 — Each engineer produces about 1 deployable change per working day | untested belief | Verify or flag | Challenge — estimate | unverified — flagged GT-13? |
| A-8 — Each engineer waits on CI about 2 times a day and half of that waiting is lost | untested belief | Verify or flag | Challenge — estimate, bracketed at 1.5–36 engineer-hours a day | unverified — flagged GT-14? |
| A-9 — The split extracts about 60% of the 350 KLOC at roughly 2 KLOC per engineer-week (range 1–5) | untested belief | Verify or flag | Challenge — estimate that spans a factor of 5 | unverified — flagged GT-15? |
| A-10 — Deploys and CI waits happen only inside an 8-hour (480-minute) working day | current constraint | Record expiry conditions | Accept — expires if the team starts deploying after hours with on-call cover; until then the window is 480 min a day | unverified — flagged GT-11? |
| A-11 — Each service's test time is proportional to its share of the code | untested belief | Verify or flag | Challenge — surfaced by the audit at C4; if false, the split is uneven and the largest service has the slowest pipeline, which strengthens C4's endpoint | unverified — flagged |
| A-12 — A deploy pipeline should run at no more than 50% utilisation so a queue does not form | convention | Challenge before use | Accept — queueing delay rises steeply as utilisation approaches 1; the 0.5 cut-off is a convention and not a law (surfaced by the audit at C3) | convention, flagged |
| A-13 — The test suite can run on parallel workers with no dependence on test order or shared state | untested belief | Verify or flag | Challenge — chains C4 and C7 depend on this; a 6-year-old Rails suite may share database state and need isolation work first (surfaced by the audit at C4) | unverified — flagged |
| A-14 — Production deploys run one pipeline at a time | convention | Challenge before use | Accept — this is the conservative case for one deployable unit; running in parallel through a merge queue only adds capacity (surfaced by the audit at C1) | convention, flagged |
| A-15 — Most changes stay inside one of the four domains | untested belief | Verify or flag | Challenge — microservices only deliver independent deploys if this holds (inversion precondition P1), and nobody has measured it | unverified — flagged |
| A-16 — With 8 shards, each run uses 8 × 5 + 35 + 5 = 80 runner-minutes of CI compute, against 45 today | untested belief | Verify or flag | Accept — follows by arithmetic from GT-12?, and inherits its flag (surfaced by the audit at C9) | unverified — flagged via GT-12? |
| A-17 — Changes become ready at times spread evenly across the day | untested belief | Verify or flag | Challenge — C2's 120-minute mean wait depends on it; C2's confidence line puts a price on it (surfaced by the audit at C2) | unverified — flagged |
| A-18 — Time lost waiting scales in proportion to pipeline duration | untested belief | Verify or flag | Accept — the first-order model for idle-wait time; it applies the same way to C6 and C7, so it cannot change which of them wins (surfaced by the audit at C6, C7) | unverified — flagged |
| A-19 — A checkout touches catalog, cart and fulfillment code | untested belief | Verify or flag | Accept — follows from what checkout is for (pricing items in a cart and handing an order to fulfillment); the call graph has not been inspected (surfaced by the audit at C8) | unverified — flagged |

## 3. Ground Truths

Irreducibility drill (five-whys, reduce-to-primitives mode): each unsuffixed entry below was reduced until it rested on a definition or an identity of arithmetic, with nothing left to reduce. Every other entry is either a figure the user reported or an estimate, and none of them has a source.

- **GT-1?** The CI/CD pipeline takes about 45 minutes end to end (reported figure, not measured) — unverified: given in the problem statement with no CI log, dashboard or other source named; Phase 3 failure record below.
- **GT-2?** The team ships about 2 deploys a day (reported figure) — unverified: given in the problem statement with no source; Phase 3 failure record below.
- **GT-3?** The team has 12 engineers (reported figure) — unverified: given in the problem statement with no source; Phase 3 failure record below.
- **GT-4?** Every deploy runs the full test suite and a coordinated application restart (reported practice) — unverified: given in the problem statement with no source; Phase 3 failure record below.
- **GT-5?** Catalog, cart, checkout and fulfillment live in one Rails monolith of about 350 KLOC, about 6 years old (reported figure) — unverified: given in the problem statement with no source; Phase 3 failure record below.
- **GT-6** A resource that handles one job at a time, where each job takes time T, can finish at most W / T jobs in a window of length W — source: the definition of serial throughput; read-at-source: stated in full in this entry, and the identity has nothing further to reduce to.
- **GT-7** Suppose items become ready at times spread evenly through a window, and batches leave at evenly spaced intervals I. An item then waits I / 2 on average for the next batch — source: the mean of a uniform distribution on [0, I] is I / 2; read-at-source: derived in this entry.
- **GT-8** Divide a workload of wall time t into k equal independent parts on k workers and it takes t / k. Fixed serial steps s and r do not shrink, so T(k) = s + t / k + r, and T(k) falls toward s + r as k grows (Amdahl's law) — source: definition plus arithmetic; read-at-source: derived in this entry.
- **GT-9** Turning an in-process call into a network call between processes adds failure modes the in-process call does not have: the callee can be down, slow, or running a different version while the caller runs — source: the definition of a process boundary; read-at-source: stated in this entry.
- **GT-10** A fixed set of tests run on fixed hardware does the same amount of compute work whichever repository or deployable unit holds it — source: conservation of work (time = work / throughput); read-at-source: stated in this entry.
- **GT-11?** Deploys happen only within an 8-hour working window of 8 × 60 = 480 minutes (assumed, from A-10) — unverified: deploy hours were not given; estimate.
- **GT-12?** The 45 minutes splits into s = 5 min setup, t = 35 min tests and r = 5 min deploy/restart; check: 5 + 35 + 5 = 45 (estimate) — unverified: no breakdown was given; estimate.
- **GT-13?** About 1 deployable change per engineer per working day (estimate) — unverified: no merge-rate data; estimate.
- **GT-14?** Each engineer waits on about 2 CI runs a day and loses about 50% of each wait; the bracket runs from 2 deploys watched by one person up to 4 runs per engineer with all of the wait lost (estimate) — unverified: no measurement; estimate.
- **GT-15?** A four-service split extracts about 60% of the code (0.6 × 350 = 210 KLOC) at about 2 KLOC per engineer-week, with a range of 1–5 (estimate) — unverified: no extraction data; estimate.
- **GT-16?** Sharding the tests, adding changed-file test selection and a rolling restart costs 2–8 engineer-weeks (estimate) — unverified: no data; estimate.
- **GT-17?** Each engineer contributes about 46 working weeks a year (estimate) — unverified: no data; estimate.

**Phase 3 failure records:** GT-1? to GT-5? are all given in the problem statement, and no source is cited for any of them. No files or directories were supplied. The working directory was checked for a CI log or a deploy history and none was found, so the read failed: unreachable (no source cited). GT-11? and GT-13? to GT-17? are estimates that this analysis made. They have no source, so nothing could be opened. GT-12? is also an estimate, and its parts were checked to add up to 45.

```text
?-marked: GT-1?, GT-2?, GT-3?, GT-4?, GT-5?, GT-11?, GT-12?, GT-13?, GT-14?, GT-15?, GT-16?, GT-17? (12 of 17)
Read-at-source: GT-6, GT-7, GT-8, GT-9, GT-10 — definitions/identities stated and derived in full in their own §3 entries; they feed the HIGH chains C10 (GT-6, GT-7), C11 (GT-8, GT-10) and C12 (GT-9)
```

## 4. Derivation Chains

### Conclusion C1: The 45-minute pipeline does not cap deploys at 2 a day

GT-1? (pipeline ≈45 min) + GT-2? (2 deploys/day) + GT-6 (serial throughput W/T) + GT-11? (480-min window)
→ serial capacity is 480 / 45 = 10.67, so at most 10 complete deploys fit in one working day *[Assumes: A-14]*
→ the current 2 deploys use 2 × 45 = 90 min of the window
→ 90 min is 90 / 480 = 18.75% of the window
→ the remaining 1 − 0.1875 = 81.25% of the pipeline's deploy capacity sits unused
→ the 2-a-day cadence is a batching choice, not a ceiling the pipeline imposes

**Pre-check:** head GT-1?, GT-2?, GT-6, GT-11? · ?-marked: GT-1?, GT-2?, GT-11? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-1?, GT-2? and GT-11? were reported or assumed and have no source. Thirty days of CI run history (median end-to-end duration, deploys per day, deploy hours) would remove them as causes of the downgrade. If A-14 failed (runs could overlap), capacity would only go up, so the endpoint stands. Rival ("reruns of flaky tests use up the capacity") is ruled out in §5, "Flaky reruns as a hidden capacity cap".

### Conclusion C2: Most of a change's lead time is spent waiting for the next deploy, not in the pipeline

GT-1? (pipeline ≈45 min) + GT-2? (2 deploys/day) + GT-7 (mean wait I/2) + GT-11? (480-min window)
→ two evenly spaced deploys in the window are 480 / 2 = 240 min apart
→ a change that becomes ready at a random time waits 240 / 2 = 120 min on average for the next deploy *[Assumes: A-17]*
→ mean lead time from ready to production is 120 + 45 = 165 min
→ the pipeline accounts for 45 / 165 = 27.3% of that lead time
→ waiting for the batch accounts for the other 120 / 165 = 72.7%
→ raising deploy cadence is the lever on the larger 72.7% share
→ a service split on its own leaves the batching policy, and so the 120-min wait, unchanged

**Pre-check:** head GT-1?, GT-2?, GT-7, GT-11? · ?-marked: GT-1?, GT-2?, GT-11? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short: GT-1?, GT-2? and GT-11? are unverified. Pairing merge timestamps with deploy timestamps over 30 days would remove them as causes of the downgrade. A-17 has a price: if readiness bunches up within x minutes before each deploy, the mean wait is x / 2. That stays above the 45-minute pipeline while x > 2 × 45 = 90 min, so the endpoint stands unless nearly all work becomes ready in the last 90 minutes before a deploy. Rival ("merges bunch up just before deploys, so the pipeline dominates") is ruled out in §5, "Merges cluster before deploys".

### Conclusion C3: The 45 minutes becomes the binding limit only when each change deploys on its own

GT-1? (pipeline ≈45 min) + GT-3? (12 engineers) + GT-13? (≈1 change/engineer/day) + GT-6 (serial throughput) + GT-11? (480-min window)
→ deploying every change separately takes 12 × 1 = 12 pipeline runs a day
→ those runs need 12 × 45 = 540 min of a 480-min window
→ utilisation is 540 / 480 = 1.125
→ above 1, the deploy queue grows every day without limit
→ deploying per change is feasible at all only if the pipeline takes at most 480 / 12 = 40 min
→ keeping utilisation at or below 0.5 needs at most 0.5 × 480 / 12 = 20 min *[Assumes: A-12]*
→ a pipeline target of 20 minutes or less removes the binding limit for small-batch deploys

**Pre-check:** head GT-1?, GT-3?, GT-13?, GT-6, GT-11? · ?-marked: GT-1?, GT-3?, GT-13?, GT-11? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-1?, GT-3?, GT-11? and GT-13? are unverified. Thirty days of CI run history would remove GT-1? and GT-11?, the team roster would remove GT-3?, and the count of merges per day from version-control history would remove GT-13?. A-12 has a price: with a 0.75 cut-off the target becomes 0.75 × 480 / 12 = 30 min. The 40-minute feasibility bound does not depend on A-12, so 45 minutes is still binding. Rival ("batch 3 changes per run through a merge queue instead") is recorded in §5 as a complement, not a substitute.

### Conclusion C4: Splitting the tests by service saves no more time than splitting them by shard

GT-4? (full suite every deploy) + GT-8 (T(k) = s + t/k + r) + GT-10 (same tests, same work) + GT-12? (s=5, t=35, r=5)
→ running the suite on k parallel workers gives T(k) = 5 + 35 / k + 5 minutes *[Assumes: A-13]*
→ four shards give 5 + 8.75 + 5 = 18.75 min
→ eight shards give 5 + 4.375 + 5 = 14.375 min
→ as k grows without limit, the floor is s + r = 5 + 5 = 10 min for monolith and services alike
→ four equal services, each running a quarter of the tests, give 5 + 35 × 0.25 + 5 = 18.75 min per pipeline *[Assumes: A-11]*
→ the service split saves the same test time as four shards, and eight shards beat it
→ cutting pipeline time does not require service boundaries

**Pre-check:** head GT-4?, GT-8, GT-10, GT-12? · ?-marked: GT-4?, GT-12? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-4? and GT-12? are unverified; per-stage timings from the CI tool would remove them. The A-11 price: if tests are spread unevenly (say checkout holds half of them), checkout's own pipeline takes 5 + 17.5 + 5 = 27.5 min, which only strengthens the endpoint. The A-13 price: a suite that shares state needs isolation work before it can be sharded. A service split also needs per-service data isolation, so the endpoint stands, and the extra cost goes into C7 (break-even below). Rival ("smaller per-service restarts are what microservices really add") is ruled out in §5.

### Conclusion C5: The cost of the 45-minute wait could be anywhere from minor to large, because nobody has measured it

GT-3? (12 engineers) + GT-1? (pipeline ≈45 min) + GT-14? (CI waits per engineer, share lost) + GT-11? (480-min window)
→ the team has 12 × 8 = 96 engineer-hours of capacity a day *[Assumes: A-10]*
→ central loss is 12 × 2 runs × 45 min × 0.5 = 540 min = 9 eng-h/day
→ 9 eng-h/day is 9 / 96 = 9.4% of capacity
→ low-end loss (only the 2 deploys watched, one person each) is 2 × 45 = 90 min = 1.5 eng-h/day
→ 1.5 eng-h/day is 1.5 / 96 = 1.6% of capacity
→ high-end loss (4 runs per engineer, every minute lost) is 12 × 4 × 45 = 2160 min = 36 eng-h/day
→ 36 eng-h/day is 36 / 96 = 37.5% of capacity
→ the bracket runs from 1.6% to 37.5%, so whether the wait is a material cost is unmeasured, not established

**Pre-check:** head GT-3?, GT-1?, GT-14?, GT-11? · ?-marked: GT-3?, GT-1?, GT-14?, GT-11? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-14? drives a 24× range (36 / 1.5 = 24). Counting CI runs triggered per engineer per day from the CI tool, plus a one-week self-report of how much waiting time is lost, would remove it. CI run history would remove GT-1? and GT-11?, and the team roster would remove GT-3?. The A-10 price: with a 10-hour day the capacity is 12 × 10 = 120 eng-h, the central share is 9 / 120 = 7.5%, and the endpoint (unmeasured, spanning more than an order of magnitude) stands. Rival: not applicable — the endpoint itself says the matter is unsettled.

### Conclusion C6: Microservices are a large investment with a slow payback

GT-5? (350 KLOC, four domains) + GT-15? (210 KLOC at 1–5 KLOC/eng-wk) + GT-17? (46 weeks/eng/yr) + C4 (18.75 min per service) + C5 (9 eng-h/day central loss)
→ extraction effort is 210 / 2 = 105 eng-weeks
→ the bracket runs from 210 / 5 = 42 to 210 / 1 = 210 eng-weeks
→ the team supplies 12 × 46 = 552 eng-weeks a year
→ 105 eng-weeks is 105 / 552 = 19.0% of a team-year (bracket 7.6%–38.0%)
→ at 18.75 min the central loss drops to 9 × 18.75 / 45 = 3.75 eng-h/day *[Assumes: A-18]*
→ the daily saving is 9 − 3.75 = 5.25 eng-h
→ 5.25 eng-h/day × 5 days / 40 h recovers 0.656 eng-weeks per week
→ payback is 105 / 0.656 = 160 weeks, bracketed from 42 / 0.656 = 64 to 210 / 0.656 = 320 weeks

**Pre-check:** head GT-5?, GT-15?, GT-17?, C4 (MEDIUM), C5 (MEDIUM) · ?-marked: GT-5?, GT-15?, GT-17? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-15? spans a factor of 5. Extracting the smallest domain as a timed spike would measure the real KLOC per engineer-week and remove it. GT-5? and GT-17? would be removed by a line count and the team's capacity plan. C4 and C5 are MEDIUM. The A-18 price: A-18 scales C6 and C7 identically, so it cannot change which option wins. The payback also leaves out the operating cost that C8 identifies, so it understates the true cost. Rival ("extract only one service") is ruled out in §5.

### Conclusion C7: Speeding up the pipeline inside the monolith pays back in weeks, at least 6 times faster than microservices

GT-16? (2–8 eng-weeks) + C4 (14.375 min at 8 shards) + C5 (9 eng-h/day central loss) + C6 (5.25 eng-h/day saving, 42–210 eng-weeks)
→ at 14.375 min the central loss drops to 9 × 14.375 / 45 = 2.875 eng-h/day *[Assumes: A-18]*
→ the daily saving is 9 − 2.875 = 6.125 eng-h
→ 6.125 × 5 / 40 recovers 0.766 eng-weeks per week
→ payback is 2 / 0.766 = 2.6 to 8 / 0.766 = 10.4 weeks
→ both savings are proportional to (45 − T), so their ratio is (45 − 14.375) / (45 − 18.75) = 30.625 / 26.25 = 1.167 at any level of wait loss
→ the smallest cost ratio is 42 / 8 = 5.25, so the microservice payback is at least 5.25 × 1.167 = 6.1 times longer
→ in-monolith pipeline work wins on payback at every point of both brackets

**Pre-check:** head GT-16?, C4 (MEDIUM), C5 (MEDIUM), C6 (MEDIUM) · ?-marked: GT-16? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-16? is an estimate. A one-week spike sharding the suite on CI would remove it. C4, C5 and C6 are MEDIUM. Break-even: the pipeline work still pays back faster than the best case for microservices (64 weeks) unless it costs more than 64 × 0.766 = 49 eng-weeks, about 6 times the upper estimate. That covers the A-13 risk that shared state must be isolated first. The A-18 price: if lost time did not scale with T, both savings would change by the same factor, so the 6.1× ratio and the endpoint stand. Rival: not applicable — the endpoint is itself a ruling-out of the rival option.

### Conclusion C8: Microservices swap restart coordination for version coordination and add new failure modes to the revenue path

GT-9 (process boundary failure modes) + GT-5? (four domains in one app) + GT-4? (coordinated restart)
→ today a checkout calls catalog, cart and fulfillment code inside one process *[Assumes: A-19]*
→ after a four-way split, the same checkout crosses up to 3 network boundaries, and each can fail independently
→ a change that spans domains then needs ordered, version-compatible deploys of several services instead of one restart *[Assumes: A-15]*
→ the split removes restart coordination but adds cross-service version coordination and partial-failure modes on the revenue path

**Pre-check:** head GT-9, GT-5?, GT-4? · ?-marked: GT-5?, GT-4? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-5? and GT-4? would be removed by reading the deploy runbook and the module layout. The A-19 price: if checkout touches fewer domains, there are fewer boundaries, but there is still at least one, so the endpoint stands. The A-15 price: if most changes do stay inside one domain, the multi-deploy cost shrinks, but the runtime failure modes from GT-9 remain. Rival: not applicable — the endpoint follows from a definition (GT-9), and the only open question is how large the effect is.

### Conclusion C9: Recommend option B — speed up the pipeline and raise deploy cadence inside the monolith

C1 (cadence not pipeline-capped) + C2 (batch wait 72.7% of lead time) + C3 (≤20-min target) + C4 (shards match the split) + C6 (105 eng-wk, 160-wk payback) + C7 (2.6–10.4-wk payback) + C8 (new failure modes)
→ weighted totals are B = 85 > D = 83 > A = 60 > C = 46, driven by lead-time reduction (×5) and engineering cost (×4)
→ recommend B now; D's module-boundary work adds to B rather than replacing it
→[2nd] (actor: engineers) each deploy carries 1–2 changes instead of 12 / 2 = 6, so a failed deploy points at fewer suspects
→[2nd] (actor: finance) CI compute rises from 45 to 8 × 5 + 35 + 5 = 80 runner-minutes per run *[Assumes: A-16]*
→[2nd] (actor: finance) that is 80 / 45 = 1.78× the compute per run
→[2nd] (actor: on-call) rolling restarts open a window where two app versions serve traffic, so migrations must be backward compatible
→[2nd] (actor: leadership) the microservices mandate is deferred on evidence rather than refuted, which needs explaining with the C5 measurement
→[3rd] (time: after a few quarters) suite growth pushes T back above 20 min unless the C3 budget is enforced as a CI check
→[3rd] (time: long run) module boundaries enforced inside the monolith lower the cost of any later extraction that C6's spike shows is justified

**Pre-check:** head C1 (MEDIUM), C2 (MEDIUM), C3 (MEDIUM), C4 (MEDIUM), C6 (MEDIUM), C7 (MEDIUM), C8 (MEDIUM) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short, because every chain cited is MEDIUM (C1, C2, C3, C4, C6, C7, C8). The scores rest on those chains' unverified inputs. The flip test changes weights, not inputs, so it does not lift this cap. Flip test: moving team ownership from 2 to 3 ties B and D at 86 (85 + 1 × 1 = 86 and 83 + 1 × 3 = 86); the smallest weight change that changes the winner is ownership going from 2 to 4, a distance of 2, which gives D 89 > B 87 (83 + 2 × 3 = 89 and 85 + 2 × 1 = 87). Because D is B plus a further step, that flip changes the second step and not the first. No single weight change makes C (microservices) or A (status quo) win; §5, "Microservices as the fix for deploy speed", records C being ruled out. A-16 qualifies only a second-order extension, not the endpoint. None of the second-order effects contradicts a Ground Truth, and the one that works against success criterion 4 (the mixed-version window) has a price: backward-compatible migrations.

### Conclusion C10: Waiting for the next batch outweighs pipeline time whenever deploys are spaced more than twice the pipeline time apart

GT-7 (mean wait I/2) + GT-6 (serial throughput W/T)
→ with deploy interval I and pipeline time T, a change's mean ready-to-production time is I / 2 + T
→ the wait term I / 2 exceeds the pipeline term T exactly when I > 2T
→ a serial pipeline admits intervals as short as T, so any interval above 2T is set by policy, not forced by the pipeline
→ whenever deploys are spaced more than twice the pipeline time apart, cadence rather than pipeline speed is the larger lever on lead time

**Pre-check:** head GT-7, GT-6 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — Inputs: GT-7 and GT-6 are definitions, read-at-source in their own §3 entries. Inference: every hop is algebra on those definitions, and the uniform-readiness premise is part of GT-7's statement, not an extra assumption. Rivals: the rival "pipeline speed is the larger lever" is ruled out by the inequality itself (GT-7) for every I > 2T. Applied to this team, I = 240 > 2 × 45 = 90 (C2).

### Conclusion C11: Any test-time gain from a service split is also available to the monolith as shards

GT-8 (T(k) = s + t/k + r) + GT-10 (same tests, same work)
→ a split into n services assigns the tests to n subsets that must each run without the others
→ those same n independent subsets are a valid assignment of the suite to n parallel workers
→ on the same hardware each subset does the same work in either setting, so the slowest shard takes as long as the slowest service's test run
→ any reduction in test-execution time a service split delivers, the monolith gets by running the same subsets as shards

**Pre-check:** head GT-8, GT-10 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — Inputs: GT-8 and GT-10 are definitions, read-at-source in their own §3 entries. Inference: deduction, because a partition usable by services is a partition usable by shards. The claim covers only the test-execution term. Setup and restart are handled separately in §5 ("Smaller per-service restarts as the decisive microservice advantage"). Rivals: "services test faster because each suite is smaller" is the rival this endpoint rules out, by GT-10.

### Conclusion C12: Splitting the app adds runtime failure modes to every call path the split crosses

GT-9 (process boundary failure modes)
→ a service split turns every call between modules placed in different services into a call between processes
→ each such call gains the failure modes GT-9 names: the callee can be down, slow, or at a different version
→ any split that cuts a call path on the revenue path adds runtime failure modes to that path

**Pre-check:** head GT-9 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — Inputs: GT-9 is a definition, read-at-source in its §3 entry. Inference: the first hop is the definition of a service split and the second applies GT-9. Rivals: "retries and circuit breakers remove the failure modes" is ruled out because they mitigate the failure modes GT-9 names but do not remove them. How large the effect is on this checkout is C8's question, not this chain's.

## 5. Abandoned Reasoning

### Dead End: Microservices as the fix for deploy speed

**What was tried:** Leadership's conclusion, taken as option C: split catalog, cart, checkout and fulfillment into four services so each one deploys independently and faster.

**Why abandoned:** It is the rival to C9, and three chains count against it. C4: each service's pipeline (18.75 min) is no faster than four shards and slower than eight (14.375 min). C7: its payback is at least 6.1 times longer than in-monolith pipeline work. C8: it adds partial-failure modes to the revenue path. In the weighted comparison it scored 46, last of four, and no single weight change makes it win (chain C9).

**What it ruled out:** Splitting into services as the *first* move for deploy speed. It does not rule out extracting a service later for a different reason (independent scaling, team autonomy), and only if A-15 is measured true.

### Dead End: Flaky reruns as a hidden capacity cap

**What was tried:** The rival to C1: test failures force reruns, and those reruns are what actually cap deploys at 2 a day.

**Why abandoned:** Even if every deploy needed two full runs, the load would be 2 × 2 × 45 = 180 min, or 180 / 480 = 37.5% of the window. That is still well under the capacity of 10.67 runs (GT-6, chain C1).

**What it ruled out:** Treating 2 a day as a mechanical limit. Flakiness may still be a cost, but it is not the cap.

### Dead End: Merges cluster before deploys, so the pipeline dominates lead time

**What was tried:** The rival to C2: if engineers merge just before each deploy, the post-merge wait is close to 0 and the 45 minutes is nearly all of the lead time.

**Why abandoned:** Bunching merges just moves the wait from after the merge to before it, as finished work held back for the next deploy. Measured from when a change is ready, the wait is still I / 2 (GT-7). It falls below 45 min only if readiness itself is concentrated in the last 90 minutes before each deploy (C2's price on A-17).

**What it ruled out:** Measuring lead time from the merge rather than from when the change is ready, which hides the cost of batching.

### Dead End: Merge-queue batching instead of a faster pipeline

**What was tried:** The rival to C3's target: batch 3 changes per run, giving 12 / 3 = 4 runs × 45 = 180 min = 37.5% utilisation. That is feasible without speeding up the pipeline at all.

**Why abandoned:** Each deploy still carries 3 changes and a 45-minute pipeline. That leaves failed deploys harder to pin on one change, which C9's second-order step relies on reducing (chain C3).

**What it ruled out:** Batching as a *substitute*. It stays usable as a complement during the transition.

### Dead End: Smaller per-service restarts as the decisive microservice advantage

**What was tried:** The rival to C4: services restart faster, so even if test time comes out equal, the split wins on r.

**Why abandoned:** Even with r = 0, a service pipeline takes 5 + 8.75 + 0 = 13.75 min. Eight monolith shards take 14.375 min (a 0.625-minute difference), and 16 shards take 5 + 35 / 16 + 5 = 12.1875 min, which beats it (GT-8, chain C4).

**What it ruled out:** Restart time as a reason to split.

### Dead End: Extract only one service

**What was tried:** The rival to C6: extract only checkout, about 0.25 × 350 = 87.5 KLOC, at a cost of 87.5 / 2 = 43.75 eng-weeks.

**Why abandoned:** Only changes to checkout would get the faster pipeline. The cost is still 43.75 / 8 = 5.5 times the upper estimate for in-monolith work, which speeds up every change (chain C6, chain C7).

**What it ruled out:** A partial split as a cheaper route to speed.

## 6. Conclusion

**Recommended approach:** Keep the monolith and go after lead time where it is actually spent. Run the suite in parallel on 8 shards (target ≤20 min, about 14.375 min), add changed-file test selection, and replace the coordinated restart with a rolling restart. Then move toward deploying each change on its own, enforcing a 20-minute pipeline budget in CI (chain C9).

**Key insight:** Most of a change's lead time is spent waiting for the next of two daily deploys: 120 of 165 minutes, or 72.7%, against 45 minutes in the pipeline. That holds whenever deploys are spaced more than twice the pipeline time apart. A service split cuts test time only by running fewer tests per deploy, and the same subsets run as shards give the monolith the same gain; eight shards do better, at 14.375 against 18.75 minutes (chain C2, chain C10, chain C4, chain C11).

**Pipeline duration matters only for per-change deploys:** 12 changes × 45 min = 540 min exceeds the 480-minute window, which is why the 20-minute target exists (chain C3).

**Microservices lose on cost:** about 105 eng-weeks (42–210) with a 160-week payback, at least 6.1 times slower to pay back than 2–8 eng-weeks of pipeline work, and they add partial-failure modes to checkout (chain C6, chain C7, chain C8, chain C12).

**Trade-offs acknowledged:** CI compute rises about 1.78× per run, rolling restarts require backward-compatible migrations, and independent team ownership is put off. If leadership rates ownership at 3 out of 5 the two options tie, and at 4 or above enforced module boundaries inside the monolith should follow as a second step (chain C9).

**What would change it:** 30 days of CI and merge history giving the real pipeline breakdown, the per-engineer wait and the share of changes that cross domains (A-15). If most changes turn out to stay inside one domain, the multi-deploy cost in C8 shrinks and extraction can be re-scored (chain C5, chain C8).

**Pre-check:** head C2 (MEDIUM), C3 (MEDIUM), C4 (MEDIUM), C5 (MEDIUM), C6 (MEDIUM), C7 (MEDIUM), C8 (MEDIUM), C9 (MEDIUM), C10 (HIGH), C11 (HIGH), C12 (HIGH) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM

**Confidence:** MEDIUM — the general results (C10, C11, C12) are HIGH because they follow from definitions alone. Every chain that puts numbers on this specific team (C2, C3, C4, C5, C6, C7, C8, C9) is rated MEDIUM, because each depends on user-reported or estimated inputs that no source backs. The recommendation points the same way at every bracket end that was tested: the microservice payback is at least 6.1 times longer at any common level of wait loss. Measurement would therefore mainly change the size of the gain, not which option wins (chain C7, chain C9).

## Appendix — process output

## Trade-off matrix (process output)

### Options

- **A** — Status quo: 45-minute full-suite pipeline, coordinated restart, 2 deploys a day.
- **B** — Speed up the pipeline and raise deploy cadence inside the monolith: 8 test shards, changed-file test selection, rolling restart, a 20-minute pipeline budget, then deploy per change.
- **C** — Microservices: split into catalog, cart, checkout and fulfillment services.
- **D** — Composite: B now, plus module boundaries with owners enforced inside the monolith. A service is extracted only if a measured trigger fires (A-15 true and a domain needs independent scaling).

Must-haves: none. The user stated none, and none follows from the ground truths, so A is scored rather than knocked out.

### Criteria & Weights

Weights were locked before any option was scored.

| Criterion (higher = better) | Weight | 1 means | 5 means |
|---|---|---|---|
| Lead-time reduction | 5 | pipeline stays at 45 min and cadence stays at 2/day | pipeline ≤15 min and per-change deploys feasible at ≤0.5 utilisation |
| Engineering cost (low cost scores high) | 4 | more than 100 eng-weeks | under 10 eng-weeks |
| Time to first benefit | 3 | more than 12 months, or never | under 2 weeks |
| Revenue-path operational safety | 4 | adds network boundaries and multi-service deploy ordering to checkout | no new runtime failure modes |
| Reversibility | 2 | one-way for over a year | can be undone in a day |
| Independent team ownership | 2 | all 12 engineers share one deploy unit with no boundaries | an independently deployable unit per domain |

### Scoring

| Option | Lead time ×5 | Cost ×4 | Time ×3 | Safety ×4 | Reversibility ×2 | Ownership ×2 | Total |
|---|---|---|---|---|---|---|---|
| A | 1 × 5 = 5 | 5 × 4 = 20 | 1 × 3 = 3 | 5 × 4 = 20 | 5 × 2 = 10 | 1 × 2 = 2 | **60** |
| B | 5 × 5 = 25 | 5 × 4 = 20 | 4 × 3 = 12 | 4 × 4 = 16 | 5 × 2 = 10 | 1 × 2 = 2 | **85** |
| C | 4 × 5 = 20 | 1 × 4 = 4 | 2 × 3 = 6 | 1 × 4 = 4 | 1 × 2 = 2 | 5 × 2 = 10 | **46** |
| D | 5 × 5 = 25 | 4 × 4 = 16 | 4 × 3 = 12 | 4 × 4 = 16 | 4 × 2 = 8 | 3 × 2 = 6 | **83** |

Where each score comes from. Lead time: C2, C3 and C4, resting on GT-1?, GT-2? and GT-12? (C scores 4 because its 18.75 min misses the ≤15 anchor). Cost: C6 and C7, resting on GT-15? and GT-16?; D adds roughly 5–10 eng-weeks of boundary work, which is a preference estimate. Time: GT-16? (B is 2–8 eng-weeks of work) and GT-15?. Safety: C8 (GT-9) and the rolling-restart version window (B and D score 4). Reversibility and ownership are preference judgements anchored as above, with no GT behind them. Totals recomputed: 5 + 20 + 3 + 20 + 10 + 2 = 60; 25 + 20 + 12 + 16 + 10 + 2 = 85; 20 + 4 + 6 + 4 + 2 + 10 = 46; 25 + 16 + 12 + 16 + 8 + 6 = 83.

### Recommendation

B wins with 85, ahead of D at 83, A at 60 and C at 46. Flip test, run by enumerating every single-weight change from 1 to 5:

- Ownership 2 → 3 ties B and D at 86.
- Ownership 2 → 4 flips the winner to D, 89 to 87 (a distance of 2).
- Cost 4 → 2 ties B and D at 75.
- Cost 4 → 1 flips to D, 71 to 70 (a distance of 3).
- No single weight change makes A or C win.

B against D is close. Because D contains B, the first step is the same either way. The flip test changes weights, not inputs, so it does not lift the MEDIUM cap that comes from the GT-N? inputs.

## Assumption Audit scan (process output)

| Chain | Step | Step Text (brief) | Assumption surfaced? | Added to Table? |
|---|---|---|---|---|
| C1 | 1 | serial capacity 10.67/day | A-14 one-at-a-time deploys | yes (A-14) |
| C1 | 2 | 2 × 45 = 90 min | no | n/a |
| C1 | 3 | 90 min is 18.75% | no | n/a |
| C1 | 4 | 81.25% unused | no | n/a |
| C1 | 5 | cadence is a batching choice | no | n/a |
| C2 | 1 | deploys 240 min apart | no | n/a |
| C2 | 2 | mean wait 120 min | A-17 readiness spread evenly | yes (A-17) |
| C2 | 3 | lead time 165 min | no | n/a |
| C2 | 4 | pipeline 27.3% | no | n/a |
| C2 | 5 | batch wait 72.7% | no | n/a |
| C2 | 6 | cadence is the larger lever | no | n/a |
| C2 | 7 | split leaves batching unchanged | no | n/a |
| C3 | 1 | 12 runs/day | no | n/a |
| C3 | 2 | 540 min needed | no | n/a |
| C3 | 3 | utilisation 1.125 | no | n/a |
| C3 | 4 | queue grows without limit | no | n/a |
| C3 | 5 | ≤40 min to be feasible | no | n/a |
| C3 | 6 | ≤20 min at 0.5 utilisation | A-12 utilisation convention | yes (A-12) |
| C3 | 7 | ≤20-min target removes the limit | no | n/a |
| C4 | 1 | T(k) = 5 + 35/k + 5 | A-13 suite can be sharded | yes (A-13) |
| C4 | 2 | k=4 → 18.75 | no | n/a |
| C4 | 3 | k=8 → 14.375 | no | n/a |
| C4 | 4 | floor 10 min | no | n/a |
| C4 | 5 | 4 services → 18.75 | A-11 tests proportional to code | yes (A-11) |
| C4 | 6 | split equals 4 shards | no | n/a |
| C4 | 7 | boundaries not required | no | n/a |
| C5 | 1 | 96 eng-h/day | A-10 8-hour window (already in table) | yes (A-10, existing row) |
| C5 | 2 | central 9 eng-h/day | no | n/a |
| C5 | 3 | 9.4% of capacity | no | n/a |
| C5 | 4 | low 1.5 eng-h/day | no | n/a |
| C5 | 5 | 1.6% of capacity | no | n/a |
| C5 | 6 | high 36 eng-h/day | no | n/a |
| C5 | 7 | 37.5% of capacity | no | n/a |
| C5 | 8 | cost unmeasured | no | n/a |
| C6 | 1 | 105 eng-weeks | no | n/a |
| C6 | 2 | bracket 42–210 | no | n/a |
| C6 | 3 | 552 eng-weeks/yr | no | n/a |
| C6 | 4 | 19.0% of a team-year | no | n/a |
| C6 | 5 | loss 3.75 eng-h/day | A-18 loss proportional to T | yes (A-18) |
| C6 | 6 | saving 5.25 | no | n/a |
| C6 | 7 | 0.656 eng-wk/wk | no | n/a |
| C6 | 8 | payback 160 (64–320) wk | no | n/a |
| C7 | 1 | loss 2.875 eng-h/day | A-18 (same row as C6) | yes (A-18, no duplicate) |
| C7 | 2 | saving 6.125 | no | n/a |
| C7 | 3 | 0.766 eng-wk/wk | no | n/a |
| C7 | 4 | payback 2.6–10.4 wk | no | n/a |
| C7 | 5 | saving ratio 1.167 | no | n/a |
| C7 | 6 | ≥6.1× longer | no | n/a |
| C7 | 7 | wins at every bracket point | no | n/a |
| C8 | 1 | checkout calls 3 domains in-process | A-19 checkout touches all three | yes (A-19) |
| C8 | 2 | up to 3 network boundaries | no | n/a |
| C8 | 3 | ordered multi-service deploys | A-15 cross-domain change share | yes (A-15, already from inversion) |
| C8 | 4 | version coordination plus failure modes | no | n/a |
| C9 | 1 | weighted totals | no | n/a |
| C9 | 2 | recommend B | no | n/a |
| C9 | 3 | [2nd] smaller batches | no | n/a |
| C9 | 4 | [2nd] CI compute 80 runner-min | A-16 runner-minutes model | yes (A-16) |
| C9 | 5 | [2nd] 1.78× per run | no | n/a |
| C9 | 6 | [2nd] mixed-version window | no | n/a |
| C9 | 7 | [2nd] mandate deferred | no | n/a |
| C9 | 8 | [3rd] suite growth | no | n/a |
| C9 | 9 | [3rd] boundaries cheapen extraction | no | n/a |
| C10 | 1 | lead = I/2 + T | no | n/a |
| C10 | 2 | wait > pipeline iff I > 2T | no | n/a |
| C10 | 3 | I > 2T is policy | no | n/a |
| C10 | 4 | cadence is the larger lever | no | n/a |
| C11 | 1 | split assigns n independent subsets | no | n/a |
| C11 | 2 | same subsets are valid shards | no | n/a |
| C11 | 3 | same work, same slowest time | no | n/a |
| C11 | 4 | monolith gets any split gain | no | n/a |
| C12 | 1 | split turns calls into inter-process calls | no | n/a |
| C12 | 2 | each gains GT-9 failure modes | no | n/a |
| C12 | 3 | revenue path gains failure modes | no | n/a |

## Adversarial pass (process output)

**Recompute:** Every figure was recomputed independently in a separate calculation, not copied from the chain text.

- C1: 480 / 45 = 10.67; 2 × 45 = 90; 90 / 480 = 0.1875.
- C2: 480 / 2 = 240; 240 / 2 = 120; 120 + 45 = 165; 45 / 165 = 0.2727; 120 / 165 = 0.7273.
- C3: 12 × 45 = 540; 540 / 480 = 1.125; 480 / 12 = 40; 0.5 × 480 / 12 = 20; 0.75 × 480 / 12 = 30.
- C4: 5 + 35/4 + 5 = 18.75; 5 + 35/8 + 5 = 14.375; 5 + 35 × 0.25 + 5 = 18.75; 5 + 17.5 + 5 = 27.5.
- C5: 12 × 8 = 96; 12 × 2 × 45 × 0.5 / 60 = 9.0; 9 / 96 = 0.09375; 2 × 45 / 60 = 1.5; 1.5 / 96 = 0.0156; 12 × 4 × 45 / 60 = 36; 36 / 96 = 0.375; 36 / 1.5 = 24.
- C6: 210 / 2 = 105; 210 / 5 = 42; 210 / 1 = 210; 12 × 46 = 552; 105 / 552 = 0.190; 42 / 552 = 0.076; 210 / 552 = 0.380; 9 × 18.75 / 45 = 3.75; 9 − 3.75 = 5.25; 5.25 × 5 / 40 = 0.65625; 105 / 0.65625 = 160; 42 / 0.65625 = 64; 210 / 0.65625 = 320.
- C7: 9 × 14.375 / 45 = 2.875; 9 − 2.875 = 6.125; 6.125 × 5 / 40 = 0.765625; 2 / 0.765625 = 2.61; 8 / 0.765625 = 10.45; 30.625 / 26.25 = 1.1667; 42 / 8 = 5.25; 5.25 × 1.1667 = 6.125; 64 × 0.765625 = 49.
- C9: 12 / 2 = 6; 8 × 5 + 35 + 5 = 80; 80 / 45 = 1.78. Trade-off totals 60, 85, 46 and 83 recomputed.
- §5: 2 × 2 × 45 = 180; 180 / 480 = 0.375; 4 × 45 = 180; 5 + 8.75 + 0 = 13.75; 5 + 35/16 + 5 = 12.1875; 0.25 × 350 = 87.5; 87.5 / 2 = 43.75; 43.75 / 8 = 5.47.

After the Fix step, the new figures were recomputed too: 1 − 0.1875 = 0.8125; 12 × 10 = 120; 9 / 120 = 0.075; 2 × 45 = 90 < 240 (C10 applied to C2).

All agree with the chain text to the stated rounding.

One error was found and corrected: the first draft of C9's flip test said ownership 2 → 3 gives D 89 > B 87. Recomputed, 2 → 3 gives 86 = 86 (a tie), and 89 > 87 needs ownership at 4. The C9 confidence line and §6 were corrected before scoring.

The direction check passes: every scaled-down figure (14.375, 18.75, 2.875, 3.75) lies below its base.

**Sensitivity:** The single input whose falsity would flip the conclusion is GT-16?, the cost of the in-monolith work, which is `?`-marked. B stops beating C's best-case payback only if that work costs more than 49 eng-weeks, about 6 times the 8-week upper estimate. A one-week sharding spike settles it, and until then the conclusion carries a MEDIUM caveat. Weakest link in each chain:

| Chain | Weakest link |
|---|---|
| C1 | GT-1? |
| C2 | A-17 |
| C3 | GT-13? |
| C4 | A-13 |
| C5 | GT-14? (a 24× range) |
| C6 | GT-15? (a 5× range) |
| C7 | GT-16? |
| C8 | A-15 |
| C9 | ownership and reversibility scores (preference judgements) |
| C10, C11, C12 | none outstanding; each rests on definitions alone, and their only contestable part is how they apply to this team, which is carried by C2, C4 and C8 |

**Rival:**

| Chain | Rival | Where it is handled |
|---|---|---|
| C9 (headline) | microservices first | ruled out in §5 "Microservices as the fix for deploy speed" |
| C1 | flaky reruns | ruled out in §5 "Flaky reruns as a hidden capacity cap" |
| C2 | clustered merges | ruled out in §5 "Merges cluster before deploys" |
| C3 | merge-queue batching | §5 "Merge-queue batching instead of a faster pipeline" |
| C4 | smaller per-service restarts | §5 "Smaller per-service restarts as the decisive microservice advantage" |
| C6 | single-service extraction | §5 "Extract only one service" |

- C5: rival not applicable — its endpoint is itself "unsettled".
- C7: rival not applicable — its endpoint is itself a ruling-out.
- C8: rival not applicable — the endpoint follows from the GT-9 definition.
- D, the near-tie composite, is not a rival to C9's endpoint, because it begins with B. Its later step is named on C9's confidence line.

**Premise:** It is six months from now and plan B has failed. The pipeline still takes over 30 minutes, deploys are still 2 a day, and leadership has restarted the microservices programme.

**Causes:**

1. (implementer) The suite shared database state, sharding produced flaky failures, and the team switched sharding off.
2. (implementer) Setup was really about 20 minutes (asset compile, database seed), not 5. Eight shards gave 20 + 4.375 + 5 = 29.375 min.
3. (implementer) Changed-file test selection skipped a test, and a checkout regression shipped. Trust collapsed and the full suite came back.
4. (on-call engineer) A rolling restart met a migration that was not backward compatible, checkout returned errors during the deploy, and coordinated restarts were reinstated.
5. (finance) The CI bill rose 1.78× per run, on top of more runs a day, and the budget cut the shards to 2.
6. (leadership) The microservices mandate went ahead in parallel and drew the engineers away from the pipeline work.
7. (product manager) QA sign-off policy kept releases in 2 batches a day even after the pipeline reached 14 minutes, so lead time barely moved.
8. (implementer) The suite grew 30% in six months with no budget enforced, and T crept back up.

Read adversarially, cause 7 cuts hardest against the conclusion. If a sign-off policy sets the cadence, the C2 lever is organisational and not technical, and pipeline work on its own buys only the 27.3% share.

**Clusters:**

- **K1, unmeasured pipeline composition** (causes 1, 2, 8): bears on GT-12?, GT-16?, C4, C7 and A-13. Triage: costly but survivable (break-even is 49 eng-weeks).
- **K2, the safety of deploying faster** (causes 3, 4): bears on GT-4?, A-4, the second-order mixed-version step in C9, and success criterion 4. Triage: fatal (a checkout outage during deploys would end the plan).
- **K3, organisational policy rather than the pipeline** (causes 5, 6, 7): bears on C2, C5 and C9. Triage: costly but survivable.

**Disposition:**

- **K1** — plan change: step 1 becomes measurement plus a one-week sharding spike, before anything else is committed. Tripwire: the spike's sharded run exceeds 20 min, or more than 2% of 50 sharded runs fail flakily. Owner: CI/platform lead, at the end of week 1.
- **K2** — plan change: roll out rolling restarts only after migrations follow expand/contract (backward compatible). Changed-file selection runs alongside a nightly full suite, and the full suite runs on any change touching checkout. Tripwire: a checkout 5xx rate above baseline during any deploy window. Owner: on-call engineer, checked on every deploy.
- **K3** — plan change: before the work starts, agree the cadence target, the CI compute budget (1.78× per run) and the pause on the microservices programme with leadership, using the C5 measurement. Tripwire: deploys still at 2 or fewer a day four weeks after the pipeline drops below 20 min. Owner: engineering lead, reviewed weekly.

**Falsification:** The conclusion is false if 30 days of CI and merge history show the pipeline rather than batching wait is most of the lead time, *and* the sharding spike cannot bring the pipeline under 40 min (the C3 feasibility bound) for less than about 49 eng-weeks (the C7 break-even).

## Techniques applied and not applied (process output)

Applied:

- inversion (Phase 2, against leadership's claim)
- five-whys reduce-to-primitives (Phase 3, GT-6 to GT-10)
- estimate (C5, C6, C7)
- theoretical-limit (Phase 4, C4: ideal floor s + r = 10 min; best demonstrated 45 min, GT-1?, the only run on record; conventional 45 min; gaps: conventional → best demonstrated is 0 min, best demonstrated → ideal floor is 35 min, all of it convention rather than a hard constraint)
- trade-off (C9)
- second-order (C9, both the actor and time lenses)
- pre-mortem (Phase 5)

Techniques not applied:

- fishbone — not applicable — inversion and the s/t/r pipeline breakdown already enumerated the assumption space, and it is not multi-causal enough to need cause categories
- theoretical-limit (Phase 1) — not applicable — the core question is a choice between interventions, not whether a current figure is a convention or a hard bound
- inversion (Phase 5) — not applicable — the conclusion is a plan, so the pre-mortem ran as the adversarial technique

## §6→§4 closure ledger (process output)

```text
- "Keep the monolith and go after lead time where it is actually spent …" → chain C9 ✓
- "Most of a change's lead time is spent waiting for the next of two daily deploys …" → chain C2, chain C10, chain C4, chain C11 ✓ (re-verified after Fix)
- "Pipeline duration matters only for per-change deploys …" → chain C3 ✓
- "Microservices lose on cost …" → chain C6, chain C7, chain C8, chain C12 ✓ (re-verified after Fix)
- "CI compute rises about 1.78× per run … module boundaries inside the monolith should follow as a second step" → chain C9 ✓
- "30 days of CI and merge history … extraction can be re-scored" → chain C5, chain C8 ✓ (re-verified after Fix; the unsupported scaling trigger was cut)
- "Pre-check: head C2 … C12 (HIGH) … Inputs ceiling: MEDIUM" → chains C2–C12 named in its head ✓
- "Confidence: MEDIUM — the general results (C10, C11, C12) are HIGH …" → chain C7, chain C9 (and names C2–C8, C10–C12) ✓
```

No claim was cut.

## Self-audit scan (process output)

| Chain | Chain Head (brief) | Form conforming? | Rule applied | Dependency clean? | Band | Act attempted? | Edges fired |
|---|---|---|---|---|---|---|---|
| C1 | GT-1? + GT-2? + GT-6 + GT-11? | unreached | n/a — mechanical positions (last head input, hops 1–2) conform; checked by hand at the unreached positions (head inputs 1–3, hops 3–5) | yes | MEDIUM | yes | Fix/Repeat (hop split) |
| C2 | GT-1? + GT-2? + GT-7 + GT-11? | unreached | n/a — same as C1; hops 3–7 checked by hand | yes | MEDIUM | yes | none |
| C3 | GT-1? + GT-3? + GT-13? + GT-6 + GT-11? | unreached | n/a — same; hops 3–7 checked by hand | yes | MEDIUM | yes | none |
| C4 | GT-4? + GT-8 + GT-10 + GT-12? | unreached | n/a — same; hops 3–7 checked by hand | yes | MEDIUM | yes | none |
| C5 | GT-3? + GT-1? + GT-14? + GT-11? | unreached | n/a — same; hops 3–8 checked by hand | yes | MEDIUM | yes | Fix/Repeat (hops split) |
| C6 | GT-5? + GT-15? + GT-17? + C4 + C5 | unreached | n/a — same; hops 3–8 checked by hand | yes (C4, C5 upstream) | MEDIUM | yes | Fix/Repeat (hop split) |
| C7 | GT-16? + C4 + C5 + C6 | unreached | n/a — same; hops 3–7 checked by hand | yes (C4, C5, C6 upstream) | MEDIUM | no | Fix/Repeat (hop split) |
| C8 | GT-9 + GT-5? + GT-4? | unreached | n/a — same; hops 3–4 checked by hand | yes | MEDIUM | yes | none |
| C9 | C1 + C2 + C3 + C4 + C6 + C7 + C8 | unreached | n/a — same; hops 3–9 ([2nd]/[3rd] extensions) checked by hand | yes (all upstream, no cycle) | MEDIUM | no | Fix/Repeat (re-rendered) |
| C10 | GT-7 + GT-6 | unreached | n/a — mechanical positions conform; first head input and hops 3–4 checked by hand | yes | HIGH | no (definitions, read in §3; no external source) | Fix/Repeat (added) |
| C11 | GT-8 + GT-10 | unreached | n/a — same; hops 3–4 checked by hand | yes | HIGH | no (definitions, read in §3; no external source) | Fix/Repeat (added) |
| C12 | GT-9 | unreached | n/a — mechanical positions (head, hops 1–2) conform; hop 3 is beyond the check's reach and was checked by hand | yes | HIGH | no (definition, read in §3; no external source) | Fix/Repeat (added) |

| §6 Span (brief) | Construct | Claim under R11? | R11 clause applied | Chain cited |
|---|---|---|---|---|
| Recommended approach: keep the monolith … | bold lead-in | yes | a bold lead-in whose colon closes the bold span (prescribed lead-in) | C9 |
| Key insight: 120 of 165 min is batching wait … | bold lead-in | yes | a bold lead-in whose colon closes the bold span (prescribed lead-in) | C2, C10, C4, C11 |
| Pipeline duration matters only for per-change deploys: … | bold lead-in | yes | a bold lead-in whose colon closes the bold span | C3 |
| Microservices lose on cost: … | bold lead-in | yes | a bold lead-in whose colon closes the bold span | C6, C7, C8, C12 |
| Trade-offs acknowledged: … | bold lead-in | yes | a bold lead-in whose colon closes the bold span (prescribed lead-in) | C9 |
| What would change it: … | bold lead-in | yes | a bold lead-in whose colon closes the bold span | C5, C8 |
| Pre-check: head C2 … C12 … | bold lead-in | yes | a bold lead-in whose colon closes the bold span; cited by the chains its head names | C2–C12 |
| Confidence: MEDIUM … | bold lead-in | yes | a bold lead-in whose colon closes the bold span (prescribed lead-in) | C7, C9 (names C2–C8, C10–C12) |

```text
Scan complete: 12 chain rows, one per section-4 chain block in order; 8 section-6 rows, one per construct in order — 8 claims under R11, 0 excluded. 0 chains malformed, 0 claims untraced.
```

## Self-Audit Gate (process output)

**Pass 1 (before re-score):** Criterion 1 Sound · Criterion 2 Rigorous · Criterion 3 Hand-wavy · Criterion 4 Sound · Criterion 5 Sound · Criterion 6 Sound · Gate cleared: yes · Hand-wavy cap cleared: yes

What pass 1 found and what the Fix changed:

- **C1:** the Essence Statement was two sentences. Rewritten as one.
- **C3:** the five unsuffixed definitional GTs (GT-6 to GT-10) fed only MEDIUM chains. Added C10, C11 and C12, HIGH chains that use those definitions alone.
- **C4:** compound hops in C1, C5, C6, C7 and C9 were each split into one inference per hop.
- **C5:** the C3 and C5 confidence lines did not give verification paths for GT-1?, GT-3? and GT-11?. A-10 (C5) and A-18 (C7) were annotated but not priced, and A-16 was not described as extension-only. All of these were added.
- **C6:** "independent scaling" in §6 was not established by any chain. It was cut.

**Criterion 1: Identify Essence**
Quoted span: "**Core problem:** Which constraint — the 45-minute pipeline, the 2-a-day deploy cadence, or the monolith's shape — actually limits how fast this team's changes reach production, and is splitting into microservices the cheapest, lowest-risk way to remove it, or neither necessary nor sufficient?"
Band: **Rigorous**
Justification: The essence is a single sentence that names the underlying question rather than leadership's proposed solution. Each of the four success criteria is a checkable property of the Conclusion: the dominant lead-time share is named, every option has a cost and an effect, the conditions that would change the answer are named, and the revenue-path risk has a price.

**Criterion 2: Challenge Assumptions**
Quoted span: "| C8 | 3 | ordered multi-service deploys | A-15 cross-domain change share | yes (A-15, already from inversion) |"
Band: **Rigorous**
Justification: All 19 rows use the four-type scheme, with the prescribed treatment and an em-dash verdict. Multiple rows are Challenge, and one is Discard (A-5). Unverified rows used in chains read "unverified — flagged". The Assumption Audit scan has one row per step for all 12 chains, in order.

**Criterion 3: Establish Ground Truths**
Quoted span: "enumerated GT-1?, GT-2?, GT-3?, GT-4?, GT-5?, GT-11?, GT-12?, GT-13?, GT-14?, GT-15?, GT-16?, GT-17? (12 of 17); the list carries `?` on exactly those twelve, and the unsuffixed GT-6, GT-7, GT-8, GT-9 and GT-10 each feed a HIGH chain (C10, C11, C12) with the read location named"
Band: **Rigorous**
Justification: The enumeration matches the list exactly and the count equals its length. Every GT carries a provenance label, and the Phase 3 failure records give the source and the reason for GT-1? to GT-5?. Every unsuffixed GT feeds a HIGH chain and names where it was read.

**Criterion 4: Reason Upward**
Quoted span: "| C11 | GT-8 + GT-10 | unreached | n/a — same; hops 3–4 checked by hand | yes | HIGH | no (definitions, read in §3; no external source) | Fix/Repeat (added) |"
Band: **Rigorous**
Justification: Every chain is in head-plus-arrow form, with parenthesized head inputs, and is dependency-clean. Where the mechanical check cannot reach a position, the cell reads `unreached` rather than `yes`, with a hand check recorded. Every hop's arithmetic recomputes, including the corrected flip test. §5 records six dead ends in the What-was-tried / Why-abandoned / What-it-ruled-out structure, and no analogy is used as evidence.

**Criterion 5: Validate**
Quoted span: "**Confidence:** MEDIUM — the general results (C10, C11, C12) are HIGH because they follow from definitions alone. Every chain that puts numbers on this specific team (C2, C3, C4, C5, C6, C7, C8, C9) is rated MEDIUM, because each depends on user-reported or estimated inputs that no source backs."
Band: **Rigorous**
Justification: Each band matches what its axes license. The definitional chains are HIGH; every chain with a `?` input is MEDIUM, with the Inputs axis named, a verification path for each `GT-N?`, and its `[Assumes]` premises priced. The Conclusion matches its weakest contributing chain. The adversarial pass record carries Recompute, Sensitivity, Rival, a past-tense Premise, an unfiltered cause list from five viewpoints, three clusters with ids, a plan change for each cluster, and Falsification.

**Criterion 6: Conclusion-to-Ground-Truth Traceability**
Quoted span: "| Key insight: 120 of 165 min is batching wait … | bold lead-in | yes | a bold lead-in whose colon closes the bold span (prescribed lead-in) | C2, C10, C4, C11 |"
Band: **Rigorous**
Justification: All 8 §6 constructs are claims, and each cites a §4 chain. The claim that was not established by any chain was cut in the Fix. The Key Insight (batching wait outweighs pipeline time, and shards match a service split) is a finding that reasoning from leadership's convention does not reach, not a restatement of the recommendation.

**Gate result:** cleared · passes: 2 · Fix/Repeat fired: yes

## Structured summary (process output)

```json
{
  "schema_version": 1,
  "run_mode": "full-composer",
  "assumptions": [
    {
      "id": "A-1",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-2",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-3",
      "type": "convention",
      "verdict": "Challenge"
    },
    {
      "id": "A-4",
      "type": "convention",
      "verdict": "Challenge"
    },
    {
      "id": "A-5",
      "type": "untested belief",
      "verdict": "Discard"
    },
    {
      "id": "A-6",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-7",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-8",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-9",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-10",
      "type": "current constraint",
      "verdict": "Accept"
    },
    {
      "id": "A-11",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-12",
      "type": "convention",
      "verdict": "Accept"
    },
    {
      "id": "A-13",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-14",
      "type": "convention",
      "verdict": "Accept"
    },
    {
      "id": "A-15",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-16",
      "type": "untested belief",
      "verdict": "Accept"
    },
    {
      "id": "A-17",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-18",
      "type": "untested belief",
      "verdict": "Accept"
    },
    {
      "id": "A-19",
      "type": "untested belief",
      "verdict": "Accept"
    }
  ],
  "ground_truths": [
    {
      "id": "GT-1",
      "read_at_source": false
    },
    {
      "id": "GT-2",
      "read_at_source": false
    },
    {
      "id": "GT-3",
      "read_at_source": false
    },
    {
      "id": "GT-4",
      "read_at_source": false
    },
    {
      "id": "GT-5",
      "read_at_source": false
    },
    {
      "id": "GT-6",
      "read_at_source": true
    },
    {
      "id": "GT-7",
      "read_at_source": true
    },
    {
      "id": "GT-8",
      "read_at_source": true
    },
    {
      "id": "GT-9",
      "read_at_source": true
    },
    {
      "id": "GT-10",
      "read_at_source": true
    },
    {
      "id": "GT-11",
      "read_at_source": false
    },
    {
      "id": "GT-12",
      "read_at_source": false
    },
    {
      "id": "GT-13",
      "read_at_source": false
    },
    {
      "id": "GT-14",
      "read_at_source": false
    },
    {
      "id": "GT-15",
      "read_at_source": false
    },
    {
      "id": "GT-16",
      "read_at_source": false
    },
    {
      "id": "GT-17",
      "read_at_source": false
    }
  ],
  "chains": [
    {
      "id": "C1",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-1?",
        "GT-2?",
        "GT-6",
        "GT-11?"
      ]
    },
    {
      "id": "C2",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-1?",
        "GT-2?",
        "GT-7",
        "GT-11?"
      ]
    },
    {
      "id": "C3",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-1?",
        "GT-3?",
        "GT-13?",
        "GT-6",
        "GT-11?"
      ]
    },
    {
      "id": "C4",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-4?",
        "GT-8",
        "GT-10",
        "GT-12?"
      ]
    },
    {
      "id": "C5",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-3?",
        "GT-1?",
        "GT-14?",
        "GT-11?"
      ]
    },
    {
      "id": "C6",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-5?",
        "GT-15?",
        "GT-17?",
        "C4",
        "C5"
      ]
    },
    {
      "id": "C7",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-16?",
        "C4",
        "C5",
        "C6"
      ]
    },
    {
      "id": "C8",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-9",
        "GT-5?",
        "GT-4?"
      ]
    },
    {
      "id": "C9",
      "confidence": "MEDIUM",
      "rests_on": [
        "C1",
        "C2",
        "C3",
        "C4",
        "C6",
        "C7",
        "C8"
      ]
    },
    {
      "id": "C10",
      "confidence": "HIGH",
      "rests_on": [
        "GT-7",
        "GT-6"
      ]
    },
    {
      "id": "C11",
      "confidence": "HIGH",
      "rests_on": [
        "GT-8",
        "GT-10"
      ]
    },
    {
      "id": "C12",
      "confidence": "HIGH",
      "rests_on": [
        "GT-9"
      ]
    }
  ],
  "dead_ends": [
    "Microservices as the fix for deploy speed",
    "Flaky reruns as a hidden capacity cap",
    "Merges cluster before deploys, so the pipeline dominates lead time",
    "Merge-queue batching instead of a faster pipeline",
    "Smaller per-service restarts as the decisive microservice advantage",
    "Extract only one service"
  ],
  "techniques": {
    "applied": [
      "inversion",
      "five-whys",
      "theoretical-limit",
      "estimate",
      "trade-off",
      "second-order",
      "pre-mortem"
    ],
    "not_applied": [
      {
        "technique": "fishbone",
        "phase": 2,
        "reason": "inversion and the s/t/r pipeline breakdown already enumerated the assumption space, and it is not multi-causal enough to need cause categories"
      },
      {
        "technique": "theoretical-limit",
        "phase": 1,
        "reason": "the core question is a choice between interventions, not whether a current figure is a convention or a hard bound"
      },
      {
        "technique": "inversion",
        "phase": 5,
        "reason": "the conclusion is a plan, so the pre-mortem ran as the adversarial technique"
      }
    ]
  },
  "gate": {
    "passes": [
      {
        "bands": [
          "Sound",
          "Rigorous",
          "Hand-wavy",
          "Sound",
          "Sound",
          "Sound"
        ],
        "gate_cleared": true,
        "hand_wavy_cap_cleared": true
      },
      {
        "bands": [
          "Rigorous",
          "Rigorous",
          "Rigorous",
          "Rigorous",
          "Rigorous",
          "Rigorous"
        ],
        "gate_cleared": true,
        "hand_wavy_cap_cleared": true
      }
    ],
    "fix_repeat_fired": true,
    "cleared": true
  },
  "re_entry": {
    "fired": true,
    "edges": [
      {
        "edge": "the Self-Audit Gate's Fix/Repeat loop",
        "trigger": "Criterion 3 scored Hand-wavy on the first pass, with Sound shortfalls on Criteria 1, 4, 5 and 6."
      }
    ]
  },
  "conclusion": {
    "recommendation": "Keep the monolith and go after lead time where it is actually spent. Run the suite in parallel on 8 shards (target ≤20 min, about 14.375 min), add changed-file test selection, and replace the coordinated restart with a rolling restart. Then move toward deploying each change on its own, enforcing a 20-minute pipeline budget in CI (chain C9).",
    "confidence": "MEDIUM"
  }
}
```
