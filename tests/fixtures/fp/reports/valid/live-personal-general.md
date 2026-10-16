**Disclosed:** The Self-Audit Gate's Fix/Repeat loop fired once. Trigger: Criterion 3 scored Hand-wavy on the first pass because the ground truths read at source fed only MEDIUM chains, and Criteria 1 and 4 scored Sound. Changes: added HIGH chains C8 and C9, built only on read-at-source inputs and cited in §6; rewrote the success criteria as tests applied to §6; split C3's first hop. The user did not supply current pay, partner income, housing tenure or the offer's base/equity split, so illustrative values (engineer $200,000, partner $90,000, renting) are used and flagged `?`.

## Answer

**Recommendation:** Don't take the offer as structured. Taking it as written either ends your partner's current job or splits the household (chain C9), and relocating ranks last of four options (chain C6). First ask the SF company whether you can live in Portland and fly in for the three office days. Stay in your current role if they say no (chain C7).

**Band (from §6):** MEDIUM (chain C6, chain C7)

**Would change it:** Your real pay, housing quotes, equity vesting and your partner's SF job prospects would tighten the cash and transition figures (chain C2, chain C3). The ranking flips only if those are at their best case and you also weight career capital at its maximum and travel time near its minimum (chain C6).

# First-Principles Analysis — Portland remote role vs. San Francisco offer

## 1. Problem Essence

**Core problem:** Does any available arrangement of the San Francisco offer leave this two-career household better off, over a multi-year horizon, than the engineer's current Portland full-remote role — once the $70K headline is converted into household after-tax, after-living-cost cash and weighed against the partner's location-bound career and the time the arrangement consumes?

The triggering question ("Should I take this job?") is framed around one person and one number. Two things are stripped away: (1) the $70K is a gross, pre-tax, pre-cost-of-living figure, not the household's gain; (2) the decision unit is the household, because the offer's relocation requirement acts directly on the partner's Portland-bound career. The symptom is "a bigger number on an offer letter"; the underlying driver is a trade between engineer cash/career capital and partner career continuity plus household time.

**Success criteria:**
- The Conclusion states the household's central net annual cash change for relocating together and for the composite, each traced to a chain whose arithmetic is shown and recomputed.
- The Conclusion states the one-time transition cost of relocating together and who bears it.
- The Conclusion's recommendation ranges over staying, relocating together, and a composite that avoids relocation — not only "take it / don't take it".
- The Conclusion names the inputs whose real values would change the recommendation.

None of these requires the answer to be "take" or "decline"; a conditional or composite answer is admissible.

Inputs not supplied: the engineer's current compensation, the partner's income, housing tenure (rent/own), and the offer's base/equity split. These are not essential to frame the question, so the analysis proceeds with explicit illustrative values (engineer $200,000, partner $90,000, married filing jointly, renting), each flagged `?` and bracketed where it matters.

## 2. Assumptions Table

| Assumption | Type | Treatment | Verdict | Verification |
|------------|------|-----------|---------|--------------|
| A-1: The $70K increase measures what the offer is worth | convention | Challenge before use | Discard — gross pre-tax figure; replaced by the household net figure in C1/C2, where the central gain is $14,702.52/yr | C1, C2 arithmetic |
| A-2: The decision belongs to the engineer alone | convention | Challenge before use | Discard — relocation acts directly on the partner's career (GT-3); unit of analysis is the household | GT-3 read at source |
| A-3: Moving to California raises the household's state tax burden substantially | convention | Challenge before use | Discard — Portland state+local tax is $25,190.20 vs California $28,042.68 at the higher post-move income; shift only +$2,852.48 (C1) | GT-5, GT-6, GT-7 read; GT-11? unverified |
| A-4: Engineer's current total comp is $200,000; partner earns $90,000; married filing jointly; standard deduction | untested belief | Verify, or flag | Challenge — not supplied by the user; illustrative, flagged GT-12?; if household taxable leaves the 24% band, federal tax on the delta moves by about ±$5,600 | unverified — flagged |
| A-5: The equity part of the $70K is worth 85–100% of face value in expectation | untested belief | Verify, or flag | Challenge — vesting schedule, cliff and share price unknown; bracketed as a 0–15% haircut, flagged GT-16? | unverified — flagged |
| A-6: Comparable housing costs $18K–$36K/yr more in SF than Portland (central $27K) | untested belief | Verify, or flag | Challenge — rent-data reads failed; flagged GT-14? | unverified — flagged |
| A-7: Other living costs (sales tax, transport, groceries) add $4K–$12K/yr in SF (central $7K) | untested belief | Verify, or flag | Challenge — flagged GT-15? | unverified — flagged |
| A-8: The partner can be re-employed in SF at equal pay within 0–12 months (central 6) | untested belief | Verify, or flag | Challenge — "no remote option" (GT-3) says nothing about SF portability; flagged GT-17? | unverified — flagged |
| A-9: The offer's relocation requirement is non-negotiable | current constraint | Record expiry conditions | Challenge — expires if the employer grants a residence waiver; whether it would is GT-21? | unverified — flagged |
| A-10: The SF employer's in-office requirement stays at 3 days/week | current constraint | Record expiry conditions | Accept — expires at the employer's next RTO policy change; priced as a 3rd-order risk on C7 | unverified — flagged |
| A-11: 2025/2026 federal, Oregon and California rate schedules hold over the decision horizon | current constraint | Record expiry conditions | Accept — expires at the next legislative change to any schedule; rates read at source (GT-5–GT-10, GT-13) | read at source |
| A-12: Household taxable income = wages − $32,200 (no itemizing, no pre-tax deductions) | untested belief | Verify, or flag | Accept — simplifying; 401(k) deferrals would lower taxable income by equal amounts in every option and leave the deltas almost unchanged | GT-13 read; rest unverified |
| A-13: As Oregon residents super-commuting, Oregon credits the California tax on CA-sourced pay, so total state tax is about Oregon-level | untested belief | Verify, or flag | Challenge — if no credit applies, extra cost ≈ 0.093 × $162,000 = $15,066/yr; priced on C5 | unverified — flagged |
| A-14: The locked trade-off weights reflect the household's values | convention | Challenge before use | Challenge — weights are values, not facts; tested with the flip test on C6/C7 | flip test |
| A-15: The current full-remote role remains available if the engineer stays | untested belief | Verify, or flag | Challenge — surfaced by inversion; current employer's policy unknown | unverified — flagged |
| A-16: Leaving the current employer forfeits no material unvested equity or benefits | untested belief | Verify, or flag | Challenge — any forfeiture adds to the transition cost of B, C and D equally | unverified — flagged |
| A-17: Job security at the new employer is comparable to the current one (no last-in-first-out exposure) | untested belief | Verify, or flag | Challenge — surfaced by inversion; not priced in cash, carried into reversibility scores | unverified — flagged |
| A-18: A large SF employer adds more career capital (scope, network, future pay) than the current role | untested belief | Verify, or flag | Challenge — scored in C6 as a stated preference, not a fact; flip test shows its weight is the lever | unverified — flagged |

**Inversion (Phase 2).** Claim: "Relocating as offered makes the household better off." Inverted: it makes them worse off. Conditions that would guarantee that: the partner cannot find equivalent SF work (A-8, load-bearing); SF housing absorbs the after-tax gain (A-6, load-bearing); the equity falls (A-5); the employer moves to 5 office days or lays off recent hires (A-10, A-17); unvested current-employer equity is forfeited (A-16). Each unverified precondition is a row above; A-6 and A-8 are the load-bearing unverified ones.

## 3. Ground Truths

- **GT-1** The offer is a $70,000 annual compensation increase, base salary plus equity — source: the user's problem statement; read-at-source: "a $70K annual compensation increase (base salary plus equity)".
- **GT-2** The offer requires physical relocation and three days per week in the office — source: problem statement; read-at-source: "requires physical relocation and three days per week in the office".
- **GT-3** The partner has an established Portland-based career with no remote option — source: problem statement; read-at-source: "an established Portland-based career with no remote option".
- **GT-4** The engineer has five years at the current employer in a full-remote role, living in Portland — source: problem statement; read-at-source: "five years at their current employer in Portland, OR — a full-remote role".
- **GT-5** Oregon 2025 tax, joint filers, taxable income over $250,000: $21,256 plus 9.9% of the excess — source: Oregon DOR Publication OR-40-FY (2025); read-at-source: "2025 Tax rate charts", Chart J, "your tax is $21,256 plus 9.9% of excess over $250,000". Measured: published statutory schedule.
- **GT-6** California 2025 Schedule Y (joint): taxable income $145,448–$742,958 taxed at $6,403.94 + 9.30% of excess over $145,448 — source: FTB "2025 California Tax Rate Schedules"; read-at-source: Schedule Y row "145,448 / 742,958 / 6,403.94 + 9.30%".
- **GT-7** California SDI withholding is 1.3% for 2026 on all wages, with no wage limit since 2024 — source: EDD "Contribution and Withholding Rates"; read-at-source: "The SDI withholding rate for 2026 is 1.3 percent. Effective January 1, 2024, all wages are subject to SDI contributions."
- **GT-8** Federal 2026: 24% for incomes over $211,400 and 32% over $403,550 (married filing jointly) — source: IRS newsroom release on 2026 inflation adjustments; read-at-source: "24% for incomes over $105,700 ($211,400 for married couples filing jointly)" and "32% … ($403,550 for married couples filing jointly)".
- **GT-9** Additional Medicare tax of 0.9% applies to wages above $250,000 for joint filers — source: IRS Topic 560; read-at-source: "A 0.9% Additional Medicare tax applies … $250,000 for married filing jointly".
- **GT-10** Employee Social Security tax is 6.2% and Medicare 1.45% — source: IRS Topic 751; read-at-source: "6.2% for the employer and 6.2% for the employee … Medicare is 1.45% … for the employee".
- **GT-11?** Portland-resident local taxes: Multnomah County Preschool for All 1.5% and Metro Supportive Housing Services 1% on joint taxable income over $200,000; Paid Leave Oregon employee share 0.6% of wages up to the Social Security wage base; Portland Arts Tax $35 per adult — unverified: Phase 3 failure record — portland.gov/revenue/personal-income-taxes returned 404; multco.us Preschool for All page returned 404. Published design values recalled, not read.
- **GT-12?** Engineer's current total compensation $200,000; partner's income $90,000; joint filing — unverified: not supplied by the user; illustrative estimate.
- **GT-13** 2026 federal standard deduction for married filing jointly is $32,200 — source: IRS 2026 inflation-adjustment release; read-at-source: "the standard deduction increases to $32,200 for married couples filing jointly".
- **GT-14?** Comparable rental housing costs $18,000–$36,000/yr more in San Francisco than Portland, central $27,000 — unverified: Phase 3 failure record — Zumper rent report returned no matching content; Apartment List national rent data returned unparseable page content. Estimate.
- **GT-15?** Other living-cost difference $4,000–$12,000/yr, central $7,000, including SF sales tax ≈ 8.625% on ≈ $25,000 taxable spend = $2,156.25 (Oregon has no sales tax) — unverified: no source read; estimate.
- **GT-16?** The equity component is worth 85–100% of face value in expectation — unverified: offer's vesting schedule and share-price exposure not supplied; estimate.
- **GT-17?** The partner can be re-employed in SF at equal pay after a 0–12 month gap, central 6 — unverified: depends on the partner's field, not supplied; estimate.
- **GT-18?** Relocation costs $5,000–$25,000, central $15,000, before any employer relocation package — unverified: estimate.
- **GT-19?** SF commute is 45 minutes each way, range 30–90 — unverified: depends on housing location; estimate.
- **GT-20?** Super-commute costs: $250 round-trip PDX–SFO per week, $200 per lodging night, about 4 hours door-to-door each way — unverified: estimate.
- **GT-21?** The SF employer would waive the relocation requirement for a Portland resident attending 3 days/week — unverified: GT-2 states relocation is required; only the employer can answer.
- **GT-22?** A San Francisco studio for one person costs about $2,800/month — unverified: estimate; rent reads failed (see GT-14?).
- **GT-23?** The 2026 Social Security wage base is $184,500 — unverified: Phase 3 failure record — ssa.gov 2026 COLA fact-sheet URL returned an HTML page, not the fact sheet.

**Irreducibility (five-whys, reduce-to-primitives mode) on the headline claim "the offer pays $70K more":** it decomposes into (a) gross delta — GT-1, a direct statement; (b) taxes on it — GT-5–GT-10, GT-13, statutory definitions read at source; (c) the value of equity — GT-16?, assumed; (d) living-cost offsets — GT-14?, GT-15?, assumed; (e) the partner's income path — GT-17?, assumed. The parent claim "the household gains $70K" is therefore flagged: three of five branches are assumed.

**Provenance summary:**

```text
?-marked: GT-11?, GT-12?, GT-14?, GT-15?, GT-16?, GT-17?, GT-18?, GT-19?, GT-20?, GT-21?, GT-22?, GT-23? (12 of 23)
Read-at-source: GT-1–GT-4 — the user's problem statement, quoted above; GT-5 — OR-40-FY 2025 Chart J; GT-6 — FTB 2025 Schedule Y row; GT-7 — EDD rates page, 2026 sentence; GT-8 — IRS 2026 release, marginal-rates paragraph; GT-9 — IRS Topic 560, threshold list; GT-10 — IRS Topic 751, rate sentence; GT-13 — IRS 2026 release, standard-deduction paragraph
Phase 3 failure records: GT-11? (two 404s), GT-14? (two rent sources unreadable), GT-23? (fact sheet not returned)
No citable source exists to read: GT-12?, GT-15?–GT-22? (household-specific estimates)
```

## 4. Derivation Chains

Options carried through this section: **A** stay in the current Portland remote role (status quo); **B** accept and relocate together, partner re-establishes in SF (the offer as structured); **C** accept, engineer relocates alone, partner stays in Portland; **D** composite — accept only if the employer waives relocation, live in Portland and fly to SF for the 3 office days. All money figures are dollars per year unless marked one-time; every figure was recomputed independently in the Phase 5 recompute step.

### Conclusion C1: Relocating together raises household after-tax income by about $48,700, not $70,000, and state tax barely moves

GT-1 (+$70K offer) + GT-12? (illustrative $200K/$90K incomes) + GT-13 ($32,200 std deduction) + GT-8 (24% band to $403,550) + GT-9 (0.9% Additional Medicare) + GT-10 (1.45% Medicare, 6.2% SS) + GT-23? (SS wage base) + GT-5 (OR Chart J) + GT-11? (Portland local taxes) + GT-6 (CA Schedule Y) + GT-7 (SDI 1.3%)
→ household federal taxable income is $290,000 − $32,200 = $257,800 now and $360,000 − $32,200 = $327,800 after, both inside the 24% band *[Assumes: A-4, A-12]*
→ federal income tax on the delta is 0.24 × $70,000 = $16,800
→ Medicare on the delta is (0.0145 + 0.009) × $70,000 = $1,645, the 0.9% applying because household wages already exceed $250,000
→ Social Security on the delta is $0 because $200,000 base pay already exceeds the $184,500 wage base
→ Oregon tax now is $21,256 + 0.099 × ($257,800 − $250,000) = $21,256 + $772.20 = $22,028.20
→ Portland local and payroll taxes now are 0.006 × $274,500 + 0.015 × $57,800 + 0.01 × $57,800 + $70 = $1,647 + $867 + $578 + $70 = $3,162
→ Portland state-plus-local total now is $22,028.20 + $3,162 = $25,190.20
→ California tax after is $6,403.94 + 0.093 × ($327,800 − $145,448) = $6,403.94 + $16,958.74 = $23,362.68 *[Assumes: A-11]*
→ SDI after is 0.013 × $360,000 = $4,680
→ the California state total after is $23,362.68 + $4,680 = $28,042.68
→ the state-level shift is $28,042.68 − $25,190.20 = +$2,852.48
→ household after-tax gain is $70,000 − $16,800 − $1,645 − $2,852.48 = $48,702.52

**Pre-check:** head GT-1, GT-12?, GT-13, GT-8, GT-9, GT-10, GT-23?, GT-5, GT-11?, GT-6, GT-7 · ?-marked: GT-12?, GT-23?, GT-11? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: GT-12? (incomes) is closed by substituting the engineer's and partner's actual W-2/offer figures; GT-11? by reading the Multnomah County and Metro rate pages; GT-23? by reading the SSA 2026 fact sheet. Inference: A-4 is priced — if real household taxable income falls outside $211,400–$403,550 the federal rate on the delta becomes 22% or 32%, moving the gain by about ±$5,600 to roughly $43K–$54K and leaving the endpoint's direction (well below $70K, state shift small) intact; A-11 and A-12 move all options equally. Rivals: "California is a big tax penalty" is ruled out by GT-5/GT-6 arithmetic (§5, "California tax penalty").

### Conclusion C2: On cash alone the relocation's steady-state household gain is about $14,700 a year, in a bracket that straddles zero

C1 (after-tax gain $48,702.52) + GT-14? (housing delta) + GT-15? (other living costs) + GT-16? (equity value)
→ the target quantity is household dollars per year after tax and after SF-versus-Portland living costs, both paid from after-tax income so the units cancel cleanly
→ the combined marginal rate on the delta is 0.24 + 0.0145 + 0.009 + 0.093 + 0.013 = 0.3695
→ a 15% haircut on the whole $70,000, standing in for the unknown equity share, costs 0.15 × $70,000 × (1 − 0.3695) = $6,620.25 after tax *[Assumes: A-5]*
→ central net is $48,702.52 − $27,000 − $7,000 = $14,702.52
→ low net is $48,702.52 − $6,620.25 − $36,000 − $12,000 = −$5,917.73
→ high net is $48,702.52 − $18,000 − $4,000 = $26,702.52
→ the bracket [−$5,917.73, $14,702.52, $26,702.52] straddles zero, so its two ends recommend opposite actions on cash
→ the $70,000 headline is $70,000 / $14,702.52 = 4.76 times the central household gain

**Pre-check:** head C1 (MEDIUM), GT-14?, GT-15?, GT-16? · ?-marked: GT-14?, GT-15?, GT-16? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: C1 is MEDIUM; GT-14? is closed by three rental quotes for comparable housing in each city; GT-15? by a month of the household's own spending mapped to SF prices; GT-16? by the offer letter's vesting schedule and cliff. A-5 is priced on the hop that uses it (the haircut is the low end of the bracket). No rival is live: the endpoint is itself a bracket, not a choice.

### Conclusion C3: Relocating together carries a one-time cost of about $40,600 that the partner mostly bears, recovered in about 2.8 years centrally and never in the low case

GT-3 (partner career Portland-based, no remote) + GT-17? (re-employment gap) + GT-18? (move cost) + GT-12? (partner $90K) + GT-10 (6.2% SS, 1.45% Medicare) + GT-9 (0.9% Additional Medicare) + GT-8 (24% band) + GT-6 (CA 9.3%) + GT-7 (SDI 1.3%) + C2 (net bracket)
→ relocating together means the partner leaves a Portland career that has no remote option
→ the partner's income therefore stops for the length of the SF job search
→ the partner's marginal rate in SF is 0.24 + 0.062 + 0.0145 + 0.009 + 0.093 + 0.013 = 0.4315 *[Assumes: A-4]*
→ a 6-month gap loses $90,000 × 6/12 × (1 − 0.4315) = $25,582.50 after tax
→ adding a $15,000 move gives a central one-time cost of $25,582.50 + $15,000 = $40,582.50
→ the range runs from $5,000 (no gap, cheap move) to $90,000 × 0.5685 + $25,000 = $51,165 + $25,000 = $76,165 (12-month gap, costly move)
→ central payback is $40,582.50 / $14,702.52 = 2.76 years of the central net gain
→ in the low case the steady-state gain is negative, so the transition cost is never recovered

**Pre-check:** head GT-3, GT-17?, GT-18?, GT-12?, GT-10, GT-9, GT-8, GT-6, GT-7, C2 (MEDIUM) · ?-marked: GT-17?, GT-18?, GT-12? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: C2 is MEDIUM; GT-17? is closed by the partner's own job search in SF (an offer in hand sets the gap to its true value, and a higher SF salary shortens payback); GT-18? by the offer's relocation-package terms; GT-12? by actual incomes. A-4 is priced in C1. A-16 (forfeited unvested equity) would only add to this cost. Rival "the partner earns more in SF" is the upper end of GT-17?, not a separate conclusion, and closes with the same verification.

### Conclusion C4: The office requirement adds about 216 unpaid commuting hours a year that the status quo does not have

GT-2 (3 days/week in office) + GT-4 (currently full remote) + GT-19? (45 min each way)
→ the status quo's commute is zero hours because the current role is full remote
→ the SF commute is 0.75 h × 2 × 3 days × 48 weeks = 216 hours a year
→ the bracket is 0.5 × 2 × 3 × 48 = 144 h (30 min each way) to 1.5 × 2 × 3 × 48 = 432 h (90 min each way)
→ 216 hours equals 216 / 40 = 5.4 forty-hour weeks a year of unpaid time added by B or C

**Pre-check:** head GT-2, GT-4, GT-19? · ?-marked: GT-19? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: GT-19? is closed by routing a commute from a candidate SF address to the office. No hop rests on an unpriced assumption; no rival is live (§5, "Dollarising commute time" records why hours, not dollars, are reported).

### Conclusion C5: The composite (keep Portland, fly in three days a week) nets about $9,600 a year with the partner's career untouched, but exists only if the employer waives relocation

C1 (federal and FICA on delta $18,445) + GT-5 (OR Chart J) + GT-11? (Portland local taxes) + GT-7 (SDI 1.3%) + GT-20? (flight and lodging costs) + GT-21? (waiver) + GT-2 (relocation required)
→ as Oregon residents the household pays Oregon-level tax on all income, Oregon crediting California tax on the CA-sourced 60% of pay *[Assumes: A-13]*
→ Oregon tax after is $21,256 + 0.099 × ($327,800 − $250,000) = $21,256 + $7,702.20 = $28,958.20
→ local and payroll taxes after are $1,647 + 0.015 × $127,800 + 0.01 × $127,800 + $70 = $1,647 + $1,917 + $1,278 + $70 = $4,912
→ SDI on the CA-worked share is 0.013 × $270,000 × 0.6 = $2,106
→ the state-level total is $28,958.20 + $4,912 + $2,106 = $35,976.20
→ the state-level shift over today's $25,190.20 is $10,786.00
→ the after-tax gain is $70,000 − $18,445 − $10,786 = $40,769
→ travel costs 48 × $250 + 96 × $200 = $12,000 + $19,200 = $31,200
→ net cash is $40,769 − $31,200 = $9,569 a year, with no partner transition cost
→ the time price is 4 h × 2 × 48 = 384 travel hours and 2 × 48 = 96 nights away a year
→ this option exists only if the employer waives the relocation requirement stated in GT-2

**Pre-check:** head C1 (MEDIUM), GT-5, GT-11?, GT-7, GT-20?, GT-21?, GT-2 · ?-marked: GT-11?, GT-20?, GT-21? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: C1 is MEDIUM; GT-21? is closed only by asking the employer; GT-20? by pricing a quarter of real flights and lodging; GT-11? as in C1. A-13 is priced: if Oregon gave no credit, extra state tax ≈ 0.093 × $162,000 = $15,066, net cash falls to $9,569 − $15,066 = −$5,497, and the endpoint (D exists only with a waiver) still stands; D's cash score would drop from 3 to 2 and its total in C6 from 79 to 75, leaving the ranking unchanged.

### Conclusion C6: The offer as structured (relocate together) ranks last of the four options, and no single weight change lifts it above staying

C2 (net cash bracket) + C3 (transition cost) + C4 (216 commute hours) + C5 (composite) + GT-3 (partner career, no remote)
→ weights locked before scoring: cash 4, partner career 5, engineer career capital 3, time 4, reversibility 3, transition cost 2 *[Assumes: A-14]*
→ weighted totals are A 85, D 79, C 69, B 60 (matrix in the appendix)
→ across every single-weight change on the 1–5 scale the smallest A − B gap is 13, at partner-career weight 5 → 1
→ even with a partner who wants to move, B's partner score rising from 2 to 4 gives 60 + 10 = 70, still below 85
→ even with every B input at its best case (cash 5, partner 4, transition 5), B scores 80 against A's 85
→ the offer as structured is the lowest-ranked option on household terms

**Pre-check:** head C2 (MEDIUM), C3 (MEDIUM), C4 (MEDIUM), C5 (MEDIUM), GT-3 · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short through C2, C3, C4 and C5 (all MEDIUM). A-14 is priced by the flip test on this chain: no single-weight change lifts B above A. The career-capital scores of 4 for B, C and D rest on A-18, a stated preference; raising them to 5 adds 3 to each and leaves B at 63. Rivals: "B wins on career capital" and "B wins if the partner wants to move" are ruled out in §5.

### Conclusion C7: Between staying and the composite the choice turns on the employer's waiver and the engineer's own weights, so ask for the waiver before deciding and stay if it is refused

C6 (ranking A 85, D 79) + C5 (composite exists only with a waiver) + GT-21? (waiver unknown)
→ staying leads the composite by 85 − 79 = 6 points at the locked weights
→ raising the career-capital weight from 3 to 5 ties them at 87–87
→ cutting the time weight from 4 to 2 ties them at 75–75, and to 1 makes the composite win 73–70
→ the A-versus-D choice therefore turns on inputs this analysis cannot supply: the employer's waiver and the engineer's own career-capital and time weights
→ the recommended sequence is to ask for the waiver first, choose between A and D on the engineer's own weights only if it is granted, and otherwise stay
→[2nd] (actor: current employer) learning of a competing offer may prompt a retention adjustment, or may mark the engineer as a flight risk
→[2nd] (actor: SF employer) a relocation waiver depends on one manager's exception that a later RTO tightening can revoke *[Assumes: A-10]*
→[3rd] (time: after a few policy cycles) a move to 4–5 office days would convert the composite into B or C, so D must be treated as revocable
→[2nd] (actor: partner) under B the partner bears most of C3's transition cost while the engineer receives the gain, an asymmetry that works against the household success criterion
→[3rd] (time: once assumed) under B the household's fixed costs re-anchor to SF prices, making a later return to Portland a cash step down

**Pre-check:** head C6 (MEDIUM), C5 (MEDIUM), GT-21? · ?-marked: GT-21? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — Inputs axis short: C6 and C5 are MEDIUM; GT-21? is closed by asking the SF recruiter in writing whether Portland residence with 3 in-office days is acceptable. The rival "take the composite outright" is ruled out at the locked weights (A 85 > D 79) and the endpoint is conditional on exactly the values that would revive it. A-10 qualifies only the second-order extension, not the endpoint. No extension step contradicts a ground truth.

### Conclusion C8: For a household already in the 24% federal band, state income tax rates change the after-tax value of the raise by only about $490

GT-1 (+$70K offer) + GT-13 ($32,200 std deduction) + GT-8 (24% band $211,400–$403,550) + GT-9 (0.9% over $250K) + GT-10 (1.45% Medicare, 6.2% SS) + GT-5 (OR 9.9% over $250K taxable) + GT-6 (CA 9.3% band $145,448–$742,958) + GT-7 (SDI 1.3%, no cap)
→ for pre-raise household wages of $282,200–$365,750, taxable income is $250,000–$333,550 before and $320,000–$403,550 after the raise
→ across that range the raise stays inside the 24% federal band, the Oregon 9.9% bracket and the California 9.3% bracket
→ for an engineer already paid above the Social Security wage base, the raise bears 1.45% + 0.9% Medicare and no Social Security
→ the California marginal rate on the raise is 0.24 + 0.0145 + 0.009 + 0.093 + 0.013 = 0.3695, keeping $70,000 × 0.6305 = $44,135
→ the Oregon marginal rate before local taxes is 0.24 + 0.0145 + 0.009 + 0.099 = 0.3625, which would keep $70,000 × 0.6375 = $44,625
→ the state-rate difference on the raise is $44,625 − $44,135 = $490 a year, too small to decide the question

**Pre-check:** head GT-1, GT-13, GT-8, GT-9, GT-10, GT-5, GT-6, GT-7 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — every input is read at source (§3 locations); every hop is arithmetic that recomputes or a bracket-membership deduction; the result is stated conditionally on the wage range, so the unverified incomes (GT-12?) are not an input; the rival "California is a big tax penalty" is ruled out in §5.

### Conclusion C9: Every way of taking the offer as written either ends the partner's current job or splits the household

GT-2 (relocation and 3 office days required) + GT-3 (partner's career Portland-based, no remote option) + GT-4 (engineer full remote in Portland)
→ the status quo is the only arrangement in which both careers continue unchanged from one Portland home
→ complying with the relocation term moves the engineer's residence out of Portland
→ the partner's career cannot follow that move remotely, because it has no remote option
→ keeping both careers and one home requires the employer to waive the relocation term, which is the composite D

**Pre-check:** head GT-2, GT-3, GT-4 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — all three inputs are read at source in the problem statement; each hop is deduction; the only rival, "the partner could work remotely from SF", is ruled out by the wording of GT-3 itself.

## 5. Abandoned Reasoning

### Dead End: Judging the offer by its $70K headline

**What was tried:** Treating the $70,000 increase as the household's gain and comparing it with the status quo directly.

**Why abandoned:** The figure is gross and pre-cost-of-living; after tax it is $48,702.52 (C1) and after SF living costs the central gain is $14,702.52, so the headline overstates the central household gain 4.76-fold (C2).

**What it ruled out:** Any reading of the decision as "$70K versus nothing"; the cash case is an order of magnitude smaller and its bracket straddles zero.

### Dead End: California tax penalty

**What was tried:** Assuming the move costs the household heavily in state income tax because California is a high-tax state.

**Why abandoned:** On the raise itself state rates differ by only $490 a year (C8); on the whole household income Oregon's 9.9% bracket (GT-5) plus Portland-area local taxes (GT-11?) total $25,190.20 today, against $28,042.68 in California after a $70,000 raise (GT-6, GT-7) — a shift of only $2,852.48 (C1).

**What it ruled out:** Treating state income tax as a deciding factor; the deciding costs are housing (GT-14?) and the partner's transition (C3).

### Dead End: Engineer relocates alone (option C) as a way to keep both careers

**What was tried:** Accepting the offer, moving alone to SF, and keeping the Portland household with weekend visits.

**Why abandoned:** Using C5's after-tax gain of $40,769 as an approximation for the split-residence tax position, net cash is $40,769 − $2,800 × 12 − 48 × $250 = $40,769 − $33,600 − $12,000 = −$4,831 a year (GT-22?, GT-20?), with about 5 nights a week apart; it scores 69 against the composite's 79, which keeps both careers with 2 nights away and positive cash (C6).

**What it ruled out:** Split residence as the way to preserve the partner's career; if both careers are to be preserved, the composite dominates it.

### Dead End: "Relocating wins once career capital is weighted properly"

**What was tried:** The rival reading that a large SF employer's career capital (A-18) outweighs the household costs.

**Why abandoned:** Raising the career-capital weight to its maximum of 5 gives A 87, D 87, C 77, B 68 — B stays last (C6). Career capital is the lever between A and D (C7), not between A and B.

**What it ruled out:** Career-capital arguments as a reason to relocate the household as offered; they are an argument for the composite at most.

### Dead End: "Relocating wins if the partner wants to move"

**What was tried:** The rival reading that the partner's own preference to move would flip the ranking.

**Why abandoned:** Raising B's partner-career score from 2 to 4 gives 70 against A's 85; with every B input at its best case B scores 80 against 85 (C6). The cost of B is not only the partner's career; it is also time (C4), reversibility and transition cost (C3).

**What it ruled out:** A single-factor reading in which the partner's consent alone decides the question.

### Dead End: Dollarising commute time at the engineer's wage

**What was tried:** Converting C4's 216 commute hours into dollars at the engineer's hourly pay.

**Why abandoned:** Valuing leisure time at the marginal wage is a convention, not a first-principles value — the engineer cannot sell those hours at that rate — so the figure would launder a preference into a number.

**What it ruled out:** A spuriously precise "time cost in dollars"; time is carried as hours (C4) and as a weighted criterion in C6.

## 6. Conclusion

**Recommended approach:** Do not accept the offer as structured — taking it as written ends the partner's current job or splits the household (chain C9), relocating the household ranks last of four options and no single weight change lifts it above staying (chain C6); before declining, ask the SF company in writing whether you can stay in Portland and fly in for the three office days, choose between that and staying on your own weighting of career growth against travel time if they agree, and stay in your current role if they refuse (chain C7).

**Key insight:** The $70K headline shrinks to about $14,700 a year of household cash once taxes and San Francisco living costs are counted, inside a bracket from −$5,900 to +$26,700 that straddles zero (chain C2), and state income tax is nearly a wash — state rates move the raise's after-tax value by only about $490 (chain C8), and Portland's local taxes offset California's rates on the rest of the household income (chain C1) — so the decision is governed by the partner's career and the household's time, not by the money.

**Trade-offs acknowledged:** Staying forgoes whatever career capital a large SF employer adds, and the composite buys about $9,600 a year of cash with 384 travel hours and 96 nights away (chain C5); relocating together would cost about $40,600 up front, mostly borne by the partner, recovered in about 2.8 years only in the central case (chain C3).

**What would change this:** Your real figures — current pay and partner income, three housing quotes per city, the offer's equity vesting schedule, and the partner's actual SF job prospects — tighten C2's bracket and C3's transition cost (chain C2, chain C3); even at every best case relocating scores 80 against staying's 85, so the ranking moves only if you also weight career capital at its maximum and travel time near its minimum (chain C6).

**Pre-check:** head C1 (MEDIUM), C2 (MEDIUM), C3 (MEDIUM), C5 (MEDIUM), C6 (MEDIUM), C7 (MEDIUM), C8 (HIGH), C9 (HIGH) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — C8 and C9 are HIGH, but the recommendation also rests on C1, C2, C3, C5, C6 and C7, each MEDIUM for unverified household-specific inputs (incomes, housing, equity, the partner's SF prospects, the waiver) whose verification is named on that chain's own line; the decline-as-structured ranking is the most robust part, surviving every single-weight change (chain C6).

## Appendix — process output

## Trade-off matrix (process output)

### Options

- **A** — stay in the current Portland full-remote role (status quo).
- **B** — accept and relocate together; partner re-establishes in SF (the offer as structured).
- **C** — accept; engineer relocates alone; partner stays in Portland.
- **D** — composite: accept only with a relocation waiver; live in Portland, fly to SF for the 3 office days.
- Must-haves: no must-haves knock out an option on current evidence. D's availability (GT-21?) is unverified, so D is scored as conditional, not knocked out.

### Criteria & Weights

Locked before any scoring. Higher is always better.

| Criterion | Weight | 1 means… | 5 means… |
|---|---|---|---|
| Household net annual cash vs. status quo | 4 | below −$10K | above +$20K (2 = −$10K to −$2K; 3 = −$2K to +$10K; 4 = +$10K to +$20K) |
| Partner career continuity | 5 | career ended, restart from scratch | unchanged |
| Engineer career capital | 3 | no change in scope or network | substantially larger scope and trajectory |
| Time and presence | 4 | 5 nights/week apart or >400 h/yr travel | no commute, no nights away |
| Reversibility | 3 | home given up and partner's job quit | fully reversible |
| One-time transition cost | 2 | over $50K | under $5K (2 = $25K–$50K; 3 = $10K–$25K; 4 = $5K–$10K) |

### Scoring

| Option | Cash (×4) | Partner (×5) | Career (×3) | Time (×4) | Reversibility (×3) | Transition (×2) | Total |
|---|---|---|---|---|---|---|---|
| A | 3×4=12 | 5×5=25 | 1×3=3 | 5×4=20 | 5×3=15 | 5×2=10 | **85** |
| B | 4×4=16 | 2×5=10 | 4×3=12 | 3×4=12 | 2×3=6 | 2×2=4 | **60** |
| C | 2×4=8 | 5×5=25 | 4×3=12 | 1×4=4 | 4×3=12 | 4×2=8 | **69** |
| D | 3×4=12 | 5×5=25 | 4×3=12 | 2×4=8 | 4×3=12 | 5×2=10 | **79** |

Ground truths behind the scores: cash — C2 (B, +$14,702.52), C5 (D, +$9,569), §5 option-C arithmetic (C, −$4,831), A = 0 by definition; partner — GT-3, GT-17?; career — A-18, a stated preference, not a ground truth; time — C4 (B: 216 h), C5 (D: 384 h, 96 nights), GT-22? (C: ~5 nights/week apart); reversibility — GT-2, GT-3; transition — C3 (B: $40,582.50), GT-22? (C: deposit and furnishing), GT-21? (D: none). Scores resting on `?` inputs carry the cap into C6.

### Recommendation

A (85) over D (79), C (69), B (60). Flip test: the smallest single-weight change that changes the winner is time 4 → 2 (tie 75–75) or career capital 3 → 5 (tie 87–87), a distance of 2 on one criterion; time 4 → 1 makes D win 73–70. No single weight change lifts B above A; the closest is partner-career weight 5 → 1, leaving A ahead by 13. Collapsed into chains C6 and C7.

## Assumption Audit scan (process output)

| Chain | Step | Step Text (brief) | Assumption surfaced? | Added to Table? |
|---|---|---|---|---|
| C1 | 1 | household federal taxable income is $290,000 − $32,200 = $257,800 now  | yes — A-4, A-12 | already in table (A-4); yes — A-12 (surfaced here, added) |
| C1 | 2 | federal income tax on the delta is 0.24 × $70,000 = $16,800 | no | n/a — clean step |
| C1 | 3 | Medicare on the delta is (0.0145 + 0.009) × $70,000 = $1,645, the 0.9% | no | n/a — clean step |
| C1 | 4 | Social Security on the delta is $0 because $200,000 base pay already e | no | n/a — clean step |
| C1 | 5 | Oregon tax now is $21,256 + 0.099 × ($257,800 − $250,000) = $21,256 +  | no | n/a — clean step |
| C1 | 6 | Portland local and payroll taxes now are 0.006 × $274,500 + 0.015 × $5 | no | n/a — clean step |
| C1 | 7 | Portland state-plus-local total now is $22,028.20 + $3,162 = $25,190.2 | no | n/a — clean step |
| C1 | 8 | California tax after is $6,403.94 + 0.093 × ($327,800 − $145,448) = $6 | yes — A-11 | already in table (A-11) |
| C1 | 9 | SDI after is 0.013 × $360,000 = $4,680 | no | n/a — clean step |
| C1 | 10 | the California state total after is $23,362.68 + $4,680 = $28,042.68 | no | n/a — clean step |
| C1 | 11 | the state-level shift is $28,042.68 − $25,190.20 = +$2,852.48 | no | n/a — clean step |
| C1 | 12 | household after-tax gain is $70,000 − $16,800 − $1,645 − $2,852.48 = $ | no | n/a — clean step |
| C2 | 1 | the target quantity is household dollars per year after tax and after  | no | n/a — clean step |
| C2 | 2 | the combined marginal rate on the delta is 0.24 + 0.0145 + 0.009 + 0.0 | no | n/a — clean step |
| C2 | 3 | a 15% haircut on the whole $70,000, standing in for the unknown equity | yes — A-5 | already in table (A-5) |
| C2 | 4 | central net is $48,702.52 − $27,000 − $7,000 = $14,702.52 | no | n/a — clean step |
| C2 | 5 | low net is $48,702.52 − $6,620.25 − $36,000 − $12,000 = −$5,917.73 | no | n/a — clean step |
| C2 | 6 | high net is $48,702.52 − $18,000 − $4,000 = $26,702.52 | no | n/a — clean step |
| C2 | 7 | the bracket [−$5,917.73, $14,702.52, $26,702.52] straddles zero, so it | no | n/a — clean step |
| C2 | 8 | the $70,000 headline is $70,000 / $14,702.52 = 4.76 times the central  | no | n/a — clean step |
| C3 | 1 | relocating together means the partner leaves a Portland career that ha | no | n/a — clean step |
| C3 | 2 | the partner's income therefore stops for the length of the SF job sear | no | n/a — clean step |
| C3 | 3 | the partner's marginal rate in SF is 0.24 + 0.062 + 0.0145 + 0.009 + 0 | yes — A-4 | already in table (A-4) |
| C3 | 4 | a 6-month gap loses $90,000 × 6/12 × (1 − 0.4315) = $25,582.50 after t | no | n/a — clean step |
| C3 | 5 | adding a $15,000 move gives a central one-time cost of $25,582.50 + $1 | no | n/a — clean step |
| C3 | 6 | the range runs from $5,000 (no gap, cheap move) to $90,000 × 0.5685 +  | no | n/a — clean step |
| C3 | 7 | central payback is $40,582.50 / $14,702.52 = 2.76 years of the central | no | n/a — clean step |
| C3 | 8 | in the low case the steady-state gain is negative, so the transition c | no | n/a — clean step |
| C4 | 1 | the status quo's commute is zero hours because the current role is ful | no | n/a — clean step |
| C4 | 2 | the SF commute is 0.75 h × 2 × 3 days × 48 weeks = 216 hours a year | no | n/a — clean step |
| C4 | 3 | the bracket is 0.5 × 2 × 3 × 48 = 144 h (30 min each way) to 1.5 × 2 × | no | n/a — clean step |
| C4 | 4 | 216 hours equals 216 / 40 = 5.4 forty-hour weeks a year of unpaid time | no | n/a — clean step |
| C5 | 1 | as Oregon residents the household pays Oregon-level tax on all income, | yes — A-13 | yes — A-13 (surfaced here, added) |
| C5 | 2 | Oregon tax after is $21,256 + 0.099 × ($327,800 − $250,000) = $21,256  | no | n/a — clean step |
| C5 | 3 | local and payroll taxes after are $1,647 + 0.015 × $127,800 + 0.01 × $ | no | n/a — clean step |
| C5 | 4 | SDI on the CA-worked share is 0.013 × $270,000 × 0.6 = $2,106 | no | n/a — clean step |
| C5 | 5 | the state-level total is $28,958.20 + $4,912 + $2,106 = $35,976.20 | no | n/a — clean step |
| C5 | 6 | the state-level shift over today's $25,190.20 is $10,786.00 | no | n/a — clean step |
| C5 | 7 | the after-tax gain is $70,000 − $18,445 − $10,786 = $40,769 | no | n/a — clean step |
| C5 | 8 | travel costs 48 × $250 + 96 × $200 = $12,000 + $19,200 = $31,200 | no | n/a — clean step |
| C5 | 9 | net cash is $40,769 − $31,200 = $9,569 a year, with no partner transit | no | n/a — clean step |
| C5 | 10 | the time price is 4 h × 2 × 48 = 384 travel hours and 2 × 48 = 96 nigh | no | n/a — clean step |
| C5 | 11 | this option exists only if the employer waives the relocation requirem | no | n/a — clean step |
| C6 | 1 | weights locked before scoring: cash 4, partner career 5, engineer care | yes — A-14 | yes — A-14 (surfaced here, added) |
| C6 | 2 | weighted totals are A 85, D 79, C 69, B 60 (matrix in the appendix) | no | n/a — clean step |
| C6 | 3 | across every single-weight change on the 1–5 scale the smallest A − B  | no | n/a — clean step |
| C6 | 4 | even with a partner who wants to move, B's partner score rising from 2 | no | n/a — clean step |
| C6 | 5 | even with every B input at its best case (cash 5, partner 4, transitio | no | n/a — clean step |
| C6 | 6 | the offer as structured is the lowest-ranked option on household terms | no | n/a — clean step |
| C7 | 1 | staying leads the composite by 85 − 79 = 6 points at the locked weight | no | n/a — clean step |
| C7 | 2 | raising the career-capital weight from 3 to 5 ties them at 87–87 | no | n/a — clean step |
| C7 | 3 | cutting the time weight from 4 to 2 ties them at 75–75, and to 1 makes | no | n/a — clean step |
| C7 | 4 | the A-versus-D choice therefore turns on inputs this analysis cannot s | no | n/a — clean step |
| C7 | 5 | the recommended sequence is to ask for the waiver first, choose betwee | no | n/a — clean step |
| C7 | 6 | [2nd] (actor: current employer) learning of a competing offer may prom | no | n/a — clean step |
| C7 | 7 | [2nd] (actor: SF employer) a relocation waiver depends on one manager' | yes — A-10 | already in table (A-10) |
| C7 | 8 | [3rd] (time: after a few policy cycles) a move to 4–5 office days woul | no | n/a — clean step |
| C7 | 9 | [2nd] (actor: partner) under B the partner bears most of C3's transiti | no | n/a — clean step |
| C7 | 10 | [3rd] (time: once assumed) under B the household's fixed costs re-anch | no | n/a — clean step |
| C8 | 1 | for pre-raise household wages of $282,200–$365,750, taxable income is  | no | n/a — clean step |
| C8 | 2 | across that range the raise stays inside the 24% federal band, the Ore | no | n/a — clean step |
| C8 | 3 | for an engineer already paid above the Social Security wage base, the  | no | n/a — clean step |
| C8 | 4 | the California marginal rate on the raise is 0.24 + 0.0145 + 0.009 + 0 | no | n/a — clean step |
| C8 | 5 | the Oregon marginal rate before local taxes is 0.24 + 0.0145 + 0.009 + | no | n/a — clean step |
| C8 | 6 | the state-rate difference on the raise is $44,625 − $44,135 = $490 a y | no | n/a — clean step |
| C9 | 1 | the status quo is the only arrangement in which both careers continue  | no | n/a — clean step |
| C9 | 2 | complying with the relocation term moves the engineer's residence out  | no | n/a — clean step |
| C9 | 3 | the partner's career cannot follow that move remotely, because it has  | no | n/a — clean step |
| C9 | 4 | keeping both careers and one home requires the employer to waive the r | no | n/a — clean step |

Audit complete: 69 step rows across 9 chains, re-run after the Fix step added C8 and C9 and split C3's first hop. A-18 (career-capital preference) surfaced from C6's scoring inputs rather than a hop and was added to the table; it is named on C6's confidence line.

## Techniques not applied (process output)

Techniques not applied:
- theoretical-limit (Phase 1) — not applicable — the question turns on a household's preferences and prices, not on whether a figure is a convention or a physical bound
- theoretical-limit (Phase 4) — not applicable — no conclusion needs a law-permitted ceiling; every quantity is a price or a tax rate
- fishbone (Phase 2) — not applicable — the assumption space was enumerable directly and through inversion; no multi-causal effect needed explaining
- five-whys causal mode (Phase 3) — not applicable — there is no recurring symptom to root-cause; reduce-to-primitives mode was applied instead
- inversion (Phase 5) — not applicable — the conclusion is a plan, so the pre-mortem was the Phase 5 technique

## Adversarial pass (process output)

**Recompute** — every figure was recomputed in an independent script, separately from the chain text. C1: 290,000 − 32,200 = 257,800 ✓; 360,000 − 32,200 = 327,800 ✓ (both within 211,400–403,550 ✓); 0.24 × 70,000 = 16,800 ✓; 0.0235 × 70,000 = 1,645 ✓; 21,256 + 0.099 × 7,800 = 22,028.20 ✓ (the first mental pass gave 22,048 — an arithmetic error corrected before any chain used it); 0.006 × 274,500 = 1,647 ✓; 0.015 × 57,800 = 867 ✓; 0.01 × 57,800 = 578 ✓; local total 3,162 ✓; 25,190.20 ✓; 6,403.94 + 0.093 × 182,352 = 6,403.94 + 16,958.74 = 23,362.68 ✓; 0.013 × 360,000 = 4,680 ✓; 28,042.68 ✓; shift 2,852.48 ✓; gain 48,702.52 ✓ (below the 70,000 base, as a figure reduced by taxes must be). C2: marginal 0.3695 ✓; 0.15 × 70,000 × 0.6305 = 6,620.25 ✓; central 14,702.52 ✓; low −5,917.73 ✓; high 26,702.52 ✓; 70,000 / 14,702.52 = 4.76 ✓. C3: 0.4315 ✓; 45,000 × 0.5685 = 25,582.50 ✓; 40,582.50 ✓; 90,000 × 0.5685 = 51,165 ✓; 76,165 ✓; 40,582.50 / 14,702.52 = 2.76 ✓. C4: 216 ✓; 144 ✓; 432 ✓; 5.4 ✓. C5: 21,256 + 0.099 × 77,800 = 28,958.20 ✓; 0.015 × 127,800 = 1,917 ✓; 0.01 × 127,800 = 1,278 ✓; 4,912 ✓; 0.013 × 162,000 = 2,106 ✓; 35,976.20 ✓; shift 10,786.00 ✓; 40,769 ✓; 31,200 ✓; 9,569 ✓; 384 h ✓; 96 nights ✓; A-13 failure: 0.093 × 162,000 = 15,066 → −5,497 ✓. §5 option C: 40,769 − 33,600 − 12,000 = −4,831 ✓. SF sales tax 25,000 × 0.08625 = 2,156.25 ✓. C8: 0.3695 → 70,000 × 0.6305 = 44,135 ✓; 0.3625 → 70,000 × 0.6375 = 44,625 ✓; difference 490 ✓; wage range 250,000 + 32,200 = 282,200 ✓ and 403,550 + 32,200 − 70,000 = 365,750 ✓; taxable 250,000–333,550 before and 320,000–403,550 after ✓. C9: no computed figures. C6/C7 totals A 85, B 60, C 69, D 79 ✓; all flip-test totals ✓; B best case 80 vs A 85 ✓; falsification case B 80 vs A 77 ✓.

**Sensitivity** — No single ground truth's falsity flips the headline "do not relocate as structured": even with every B input at its best case B scores 80 against 85 (C6). The input closest to flipping the A-versus-D sub-choice is GT-21? (`?`-marked; the waiver) — it cannot be verified by this analysis, only by the employer, so C7 carries the confidence caveat and makes the waiver request the first action. Weakest link per chain: C1 — GT-12? (illustrative incomes; the federal band); C2 — GT-14? (housing delta, the largest uncertain term at $18K–$36K); C3 — GT-17? (the partner's re-employment gap); C4 — GT-19? (commute length); C5 — A-13 (Oregon credit for California tax), priced at −$15,066; C6 — A-18 (career-capital scores are a preference); C7 — GT-21? (waiver); C8 — the stated wage-range condition (a household outside $282,200–$365,750 needs the brackets recomputed); C9 — none beyond the wording of GT-3.

**Rival** — Headline rival: "take the offer and relocate, because the long-run SF career and equity upside outweighs the costs" — ruled out by C6, recorded in §5 "Relocating wins once career capital is weighted properly" and "Relocating wins if the partner wants to move". Intermediate chains: C8 rival "California is a big tax penalty on the raise" — ruled out by its own arithmetic ($490) and §5 "California tax penalty"; C9 rival "the partner could work remotely from SF" — ruled out by GT-3's wording; C1 rival "California is a big tax penalty" — ruled out in §5 "California tax penalty" by GT-5/GT-6 arithmetic; C2 — rival not applicable — the endpoint is a bracket, not a choice; C3 — rival "the partner earns more in SF" is the upper end of GT-17?, closed by the same verification, named on C3's confidence line; C4 — rival "commute time can be priced in dollars" ruled out in §5 "Dollarising commute time"; C5 — rival "split residence (C) preserves both careers more cheaply" ruled out in §5 "Engineer relocates alone"; C6 — rivals above; C7 — rival "take the composite outright" ruled out at locked weights (85 > 79), named on C7's confidence line.

**Premise** — It is six months from now; the engineer followed this analysis, asked for the waiver, was refused, stayed in the current role — and the household is clearly worse off than if they had taken the offer. What caused it?

**Causes** —
- (engineer) The current employer announced a return-to-office policy three months later, so the "safe" status quo vanished.
- (engineer) The current employer cut the team; five years of tenure did not protect the role.
- (engineer) Asking for the waiver read as weak commitment and the SF offer was withdrawn before a real decision.
- (engineer) Career growth stalled; the engineer resents the decision and starts looking again, now without an offer in hand.
- (partner) The partner had quietly wanted to leave their Portland job and an SF move would have been welcome; nobody asked.
- (partner) The partner's Portland employer had a layoff, so the career being protected was not as secure as assumed.
- (household finances) Real current pay was lower than the $200,000 assumed, so the after-tax gain was larger than computed (Social Security and bracket effects differ).
- (household finances) Real SF housing for their needs was at the low end, and the relocation package covered the move, so the cash case was near the top of C2's bracket.
- (household finances) The SF company's stock rose sharply; the equity in the forgone offer was worth far more than face.
- (competitor / SF employer) The SF company filled the role and later offers from similar companies carried the same relocation terms, so the composite was never available anywhere.

**Clusters** —
- K1 Status quo assumed stable (RTO at current employer; layoffs; partner's own job security) — bears on A-15, GT-4, GT-3, C6.
- K2 Illustrative inputs wrong in the offer's favour (lower real pay, cheaper housing, covered move, equity upside) — bears on GT-12?, GT-14?, GT-16?, GT-18?, C1, C2, C3.
- K3 Partner's preference never asked — bears on GT-3, A-2, A-14, C6.
- K4 The waiver request itself backfires, or the composite is unavailable anywhere — bears on GT-21?, C5, C7.

**Disposition** —
- K1 (costly but survivable) — plan change: before replying to the SF company, ask the current employer directly whether full-remote status is under review and whether a market adjustment is possible; tripwire: any RTO or restructuring announcement at the current employer within six months, seen by the engineer in all-hands communications.
- K2 (costly but survivable) — plan change: rerun C1–C3 with real pay stubs, the offer letter's vesting schedule and relocation terms, and three housing quotes per city before deciding; tripwire: if the recomputed central net in C2 exceeds $27,000 a year, revisit C6 (the falsification region), checked by the engineer before the offer deadline.
- K3 (fatal to the framing if it occurs) — plan change: the decision is made jointly and the partner sets their own weight on career continuity in C6 in place of the assumed 5; no externally observable tripwire exists — the only signal is the conversation itself.
- K4 (tolerable) — accepted risk with named mitigation: a withdrawn offer returns the household to A, which is the recommended default; mitigation — make the request as a counter-proposal once the offer deadline is known, and only after K1's question to the current employer is answered.

**Falsification** — The conclusion "do not relocate as structured" is false if the status quo is not actually available (the current employer ends full-remote work, A-15), or if the real inputs put B at its best case (cash score 5, partner score 4 because the partner has an SF offer at equal or higher pay, transition score 4 or better) while the household weights career capital at 5 and time at 2 — then B scores 80 against A's 77.

## §6→§4 closure ledger (process output)

- "Do not accept the offer as structured … stay in your current role if they refuse" → chain C9, chain C6, chain C7 ✓
- "The $70K headline shrinks to about $14,700 a year … not by the money" → chain C2, chain C8, chain C1 ✓
- "Staying forgoes whatever career capital … only in the central case" → chain C5, chain C3 ✓
- "Your real figures … weight career capital at its maximum and travel time near its minimum" → chain C2, chain C3, chain C6 ✓
- "head C1 (MEDIUM), C2 (MEDIUM), C3 (MEDIUM), C5 (MEDIUM), C6 (MEDIUM), C7 (MEDIUM), C8 (HIGH), C9 (HIGH) …" (Pre-check) → chains C1, C2, C3, C5, C6, C7, C8, C9 ✓
- "MEDIUM — C8 and C9 are HIGH, but the recommendation also rests on …" (Confidence) → chains C8, C9, C1, C2, C3, C5, C6, C7 ✓

Ledger clean: 6 claims, 6 traced, 0 cut (re-verified after the Fix step added C8 and C9).

## Self-audit scan (process output)

`Form conforming?` below is scored by direct inspection of every head and every hop of each block, not by the mechanical form check, so every rule position was reached; no cell is `unreached`.

| Chain | Chain Head (brief) | Form conforming? | Rule applied | Dependency clean? | Band | Act attempted? | Edges fired |
|---|---|---|---|---|---|---|---|
| C1 | GT-1 + GT-12? + GT-13 + GT-8 + GT-9 + GT-10 + GT-23? + GT-5 + GT-11? + GT-6 + GT-7 | yes | n/a | yes | MEDIUM | yes | none |
| C2 | C1 + GT-14? + GT-15? + GT-16? | yes | n/a | yes | MEDIUM | yes | none |
| C3 | GT-3 + GT-17? + GT-18? + GT-12? + GT-10 + GT-9 + GT-8 + GT-6 + GT-7 + C2 | yes | n/a | yes | MEDIUM | yes | Fix/Repeat (first hop split into two) |
| C4 | GT-2 + GT-4 + GT-19? | yes | n/a | yes | MEDIUM | yes | none |
| C5 | C1 + GT-5 + GT-11? + GT-7 + GT-20? + GT-21? + GT-2 | yes | n/a | yes | MEDIUM | yes | none |
| C6 | C2 + C3 + C4 + C5 + GT-3 | yes | n/a | yes | MEDIUM | yes | none |
| C7 | C6 + C5 + GT-21? | yes | n/a | yes | MEDIUM | yes | none |
| C8 | GT-1 + GT-13 + GT-8 + GT-9 + GT-10 + GT-5 + GT-6 + GT-7 | yes | n/a | yes | HIGH | yes | Fix/Repeat (added) |
| C9 | GT-2 + GT-3 + GT-4 | yes | n/a | yes | HIGH | yes | Fix/Repeat (added) |

`Act attempted?` = yes on every chain: each head carries at least one input whose source this run opened (GT-1–GT-4 the problem statement; GT-5–GT-10, GT-13 the published schedules) or attempted and recorded as failed (GT-11?, GT-14?, GT-23?).

| §6 Span (brief) | Construct | Claim under R11? | R11 clause applied | Chain cited |
|---|---|---|---|---|
| Recommended approach: do not accept as structured; ask for waiver; else stay | bold lead-in | yes | bold lead-in whose colon closes the bold span (prescribed lead-in) | C9, C6, C7 |
| Key insight: $70K shrinks to ~$14,700; state tax a wash | bold lead-in | yes | bold lead-in whose colon closes the bold span (prescribed lead-in) | C2, C8, C1 |
| Trade-offs acknowledged: composite time cost; relocation transition cost | bold lead-in | yes | bold lead-in whose colon closes the bold span (prescribed lead-in) | C5, C3 |
| What would change this: real figures; best case still 80 vs 85 | bold lead-in | yes | bold lead-in whose colon closes the bold span | C2, C3, C6 |
| Pre-check: head C1–C7 (MEDIUM), C8–C9 (HIGH) · Inputs ceiling MEDIUM | bold lead-in | yes | bold lead-in whose colon closes the bold span; cited by the chains its head names | C1, C2, C3, C5, C6, C7, C8, C9 |
| Confidence: MEDIUM; C8–C9 HIGH, rest MEDIUM | bold lead-in | yes | bold lead-in whose colon closes the bold span (prescribed lead-in) | C8, C9, C1, C2, C3, C5, C6, C7 |

```text
Scan complete: 9 chain rows, one per section-4 chain block in order; 6 section-6 rows, one per construct in order — 6 claims under R11, 0 excluded. 0 chains malformed, 0 claims untraced.
```

## Self-Audit Gate (process output)

**Pass 1 (before re-score):** Criterion 1 Sound · Criterion 2 Rigorous · Criterion 3 Hand-wavy · Criterion 4 Sound · Criterion 5 Rigorous · Criterion 6 Rigorous · Gate cleared: yes · Hand-wavy cap cleared: yes

Pass 1 cleared both conditions, but Criterion 3 was Hand-wavy because the unsuffixed, read-at-source ground truths (GT-1–GT-10, GT-13) fed only MEDIUM chains; Criterion 1's success criteria were not all checkable against §6 ("for each option"); and C3's first hop carried two inferences joined by "so". The Fix/Repeat loop fired once: the rubric's preferred branch (acquire, not downgrade) was applied by adding two chains built only on read-at-source inputs (C8, C9), citing them in §6, rewriting the success criteria as properties of §6, and splitting C3's first hop. The pass below is the single re-score.

**Criterion 1: Identify Essence**
Quoted span: "The Conclusion states the household's central net annual cash change for relocating together and for the composite, each traced to a chain whose arithmetic is shown and recomputed."
Band: **Rigorous**
Justification: The Essence Statement names the household-level trade (not the triggering "Should I take this job?"), and each success criterion is now a verb + subject + outcome test applied by scanning §6, which states $14,700 (C2), $9,600 (C5), the $40,600 transition cost borne by the partner (C3), all three option families, and the inputs that would change it.

**Criterion 2: Challenge Assumptions**
Quoted span: "| C5 | 1 | as Oregon residents the household pays Oregon-level tax on all income, Oregon cre | yes — A-13 | yes — A-13 (surfaced here, added) |"
Band: **Rigorous**
Justification: Every row uses one of the four types with the matching treatment, verdicts lead with a token and an em-dash justification, eleven rows are challenged or discarded, unverified rows read "unverified — flagged", and the Assumption Audit scan covers every hop of C1–C9 with surfaced assumptions recorded in the table.

**Criterion 3: Establish Ground Truths**
Quoted span: enumerated "GT-11?, GT-12?, GT-14?, GT-15?, GT-16?, GT-17?, GT-18?, GT-19?, GT-20?, GT-21?, GT-22?, GT-23? (12 of 23)"; the list carries `?` on exactly those twelve and on no other entry; every unsuffixed GT (GT-1–GT-10, GT-13) names a read-at-source location and now feeds HIGH chain C8 (GT-1, GT-5–GT-10, GT-13) or C9 (GT-2, GT-3, GT-4).
Band: **Rigorous**
Justification: IDs are stable, the enumeration matches the list on inspection, every unsuffixed GT has a named read location and feeds a HIGH chain, and the three failed reads carry Phase 3 failure records naming source and reason.

**Criterion 4: Reason Upward**
Quoted span: "| C3 | GT-3 + GT-17? + GT-18? + GT-12? + GT-10 + GT-9 + GT-8 + GT-6 + GT-7 + C2 | yes | n/a | yes | MEDIUM | yes | Fix/Repeat (first hop split into two) |"
Band: **Rigorous**
Justification: All nine chain rows read Form conforming yes and Dependency clean yes; every hop's arithmetic recomputed in the adversarial record; assumption-bearing hops carry `[Assumes: A-N]`; §5 records six dead ends in the What-was-tried / Why-abandoned / What-it-ruled-out form; no analogy is used as evidence.

**Criterion 5: Validate**
Quoted span: "**Confidence:** MEDIUM — Inputs axis short: C1 is MEDIUM; GT-21? is closed only by asking the employer; GT-20? by pricing a quarter of real flights and lodging; GT-11? as in C1. A-13 is priced: if Oregon gave no credit, extra state tax ≈ 0.093 × $162,000 = $15,066"
Band: **Rigorous**
Justification: Each MEDIUM line names its `?` inputs and cited chains with a verification path and prices its declared assumptions, C8/C9 are HIGH only on read inputs and deduction, the Conclusion's MEDIUM equals its weakest contributing chain, and the adversarial record carries Recompute, Sensitivity, Rival, a past-tense Premise, an unfiltered Causes list from three viewpoints, cited Clusters, a Disposition per cluster and Falsification.

**Criterion 6: Conclusion-to-Ground-Truth Traceability**
Quoted span: "| Key insight: $70K shrinks to ~$14,700; state tax a wash | bold lead-in | yes | bold lead-in whose colon closes the bold span (prescribed lead-in) | C2, C8, C1 |"
Band: **Rigorous**
Justification: All six §6 claims cite named chains in the scan, none introduces reasoning absent from §4, and the Key Insight — the headline overstates the household gain 4.76-fold and state tax is a wash — is a finding the convention "California is expensive in tax, $70K is a big raise" does not reach, not a restatement of the recommendation.

**Gate result:** cleared · passes: 2 · Fix/Repeat fired: yes

## Structured summary (process output)

```json
{
  "schema_version": 1,
  "run_mode": "full-composer",
  "assumptions": [
    {
      "id": "A-1",
      "type": "convention",
      "verdict": "Discard"
    },
    {
      "id": "A-2",
      "type": "convention",
      "verdict": "Discard"
    },
    {
      "id": "A-3",
      "type": "convention",
      "verdict": "Discard"
    },
    {
      "id": "A-4",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-5",
      "type": "untested belief",
      "verdict": "Challenge"
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
      "type": "current constraint",
      "verdict": "Challenge"
    },
    {
      "id": "A-10",
      "type": "current constraint",
      "verdict": "Accept"
    },
    {
      "id": "A-11",
      "type": "current constraint",
      "verdict": "Accept"
    },
    {
      "id": "A-12",
      "type": "untested belief",
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
      "verdict": "Challenge"
    },
    {
      "id": "A-15",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-16",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-17",
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-18",
      "type": "untested belief",
      "verdict": "Challenge"
    }
  ],
  "ground_truths": [
    {
      "id": "GT-1",
      "read_at_source": true
    },
    {
      "id": "GT-2",
      "read_at_source": true
    },
    {
      "id": "GT-3",
      "read_at_source": true
    },
    {
      "id": "GT-4",
      "read_at_source": true
    },
    {
      "id": "GT-5",
      "read_at_source": true
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
      "read_at_source": true
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
    },
    {
      "id": "GT-18",
      "read_at_source": false
    },
    {
      "id": "GT-19",
      "read_at_source": false
    },
    {
      "id": "GT-20",
      "read_at_source": false
    },
    {
      "id": "GT-21",
      "read_at_source": false
    },
    {
      "id": "GT-22",
      "read_at_source": false
    },
    {
      "id": "GT-23",
      "read_at_source": false
    }
  ],
  "chains": [
    {
      "id": "C1",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-1",
        "GT-12?",
        "GT-13",
        "GT-8",
        "GT-9",
        "GT-10",
        "GT-23?",
        "GT-5",
        "GT-11?",
        "GT-6",
        "GT-7"
      ]
    },
    {
      "id": "C2",
      "confidence": "MEDIUM",
      "rests_on": [
        "C1",
        "GT-14?",
        "GT-15?",
        "GT-16?"
      ]
    },
    {
      "id": "C3",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-3",
        "GT-17?",
        "GT-18?",
        "GT-12?",
        "GT-10",
        "GT-9",
        "GT-8",
        "GT-6",
        "GT-7",
        "C2"
      ]
    },
    {
      "id": "C4",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-2",
        "GT-4",
        "GT-19?"
      ]
    },
    {
      "id": "C5",
      "confidence": "MEDIUM",
      "rests_on": [
        "C1",
        "GT-5",
        "GT-11?",
        "GT-7",
        "GT-20?",
        "GT-21?",
        "GT-2"
      ]
    },
    {
      "id": "C6",
      "confidence": "MEDIUM",
      "rests_on": [
        "C2",
        "C3",
        "C4",
        "C5",
        "GT-3"
      ]
    },
    {
      "id": "C7",
      "confidence": "MEDIUM",
      "rests_on": [
        "C6",
        "C5",
        "GT-21?"
      ]
    },
    {
      "id": "C8",
      "confidence": "HIGH",
      "rests_on": [
        "GT-1",
        "GT-13",
        "GT-8",
        "GT-9",
        "GT-10",
        "GT-5",
        "GT-6",
        "GT-7"
      ]
    },
    {
      "id": "C9",
      "confidence": "HIGH",
      "rests_on": [
        "GT-2",
        "GT-3",
        "GT-4"
      ]
    }
  ],
  "dead_ends": [
    "Judging the offer by its $70K headline",
    "California tax penalty",
    "Engineer relocates alone (option C) as a way to keep both careers",
    "\"Relocating wins once career capital is weighted properly\"",
    "\"Relocating wins if the partner wants to move\"",
    "Dollarising commute time at the engineer's wage"
  ],
  "techniques": {
    "applied": [
      "inversion",
      "five-whys",
      "estimate",
      "trade-off",
      "second-order",
      "pre-mortem"
    ],
    "not_applied": [
      {
        "technique": "theoretical-limit",
        "phase": 1,
        "reason": "the question turns on a household's preferences and prices, not on whether a figure is a convention or a physical bound"
      },
      {
        "technique": "theoretical-limit",
        "phase": 4,
        "reason": "no conclusion needs a law-permitted ceiling; every quantity is a price or a tax rate"
      },
      {
        "technique": "fishbone",
        "phase": 2,
        "reason": "the assumption space was enumerable directly and through inversion; no multi-causal effect needed explaining"
      },
      {
        "technique": "five-whys",
        "phase": 3,
        "reason": "there is no recurring symptom to root-cause; reduce-to-primitives mode was applied instead"
      },
      {
        "technique": "inversion",
        "phase": 5,
        "reason": "the conclusion is a plan, so the pre-mortem was the Phase 5 technique"
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
          "Rigorous",
          "Rigorous"
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
        "trigger": "Criterion 3 scored Hand-wavy on the first pass because the read-at-source ground truths fed only MEDIUM chains, with Criteria 1 and 4 at Sound."
      }
    ]
  },
  "conclusion": {
    "recommendation": "Do not accept the offer as structured — taking it as written ends the partner's current job or splits the household (chain C9), relocating the household ranks last of four options and no single weight change lifts it above staying (chain C6); before declining, ask the SF company in writing whether you can stay in Portland and fly in for the three office days, choose between that and staying on your own weighting of career growth against travel time if they agree, and stay in your current role if they refuse (chain C7).",
    "confidence": "MEDIUM"
  }
}
```
