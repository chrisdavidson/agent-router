**Disclosed:** The prompt does not say whether "5 MWh" is heat or electricity. This analysis reads it as 5 MWh of usable *thermal* capacity (A-1). The electric-basis conversion is in §5.

## Answer

**Recommendation:** Use about $100/kWh_th of usable capacity ($99.94; $499,691 installed) as the central capital cost for a 5 MWh_th two-tank solar-salt store, carried with its bracket of $48–252/kWh_th (chain C5). Levelised over 10,950 daily cycles at 92.0% daily heat retention, capital comes to 0.99 ¢/kWh_th undiscounted, or 2.40 ¢/kWh_th at 7% real (chain C8, chain C7).

**Band (from §6):** MEDIUM (chain C5, chain C8)

**Would change it:** A vendor quote for the same scope, covering the equipment and fabricated-steel prices (GT-9?, GT-6?) (chain C5).

## 1. Problem Essence

**Core problem:** What does it cost, per kWh of usable stored heat, to build and install a 5 MWh_th two-tank molten-salt store, when the cost is rebuilt from what the store physically needs (mass of salt, steel, insulation, a fixed set of equipment), and what does that capital cost come to per kWh of heat delivered over the store's cycle life?

**Success criteria:**

1. The salt requirement comes from physics (energy = mass × specific heat × temperature swing), and every unit cancels in the working.
2. Each cost item is a quantity multiplied by a unit price. The arithmetic is shown, and every figure is recomputed by a separate path.
3. The result gives a central value plus a lower and upper bound, for installed capital cost ($/kWh_th) and for levelised capital cost per kWh delivered (¢/kWh_th).
4. The levelised figure states its basis (with or without discounting, the discount rate, what it excludes) and includes the store's own heat losses.
5. The analysis states what limits the cost at this size, and compares the estimate with the lowest cost the physics allows.

**Framing note:** the prompt does not say whether "5 MWh" is heat or electricity. This analysis reads it as 5 MWh of *usable thermal* capacity, because a thermal store holds heat (A-1). The electric reading is handled in §5.

## 2. Assumptions Table

Each assumption has a label (A-N) at the start of its text. The chains' `[Assumes: A-N]` marks and the Assumption Audit refer to these labels.

| Assumption | Type | Treatment | Verdict | Verification |
|------------|------|-----------|---------|--------------|
| A-1: "5 MWh" means usable thermal energy stored (MWh_th) | untested belief | Verify, or flag as unverified | Challenge — the prompt does not say heat or electricity. Thermal is used because a TES stores heat (GT-3). The electric reading is converted in §5 | unverified — flagged; disclosed at the top of the file |
| A-2: The storage medium is "solar salt" (60% NaNO3, 40% KNO3) | convention | Challenge before use | Accept — this is the salt whose properties were read at source (GT-1). Chloride or ternary salts would change both the temperature swing and the price | GT-1 |
| A-3: The design is two tanks, one hot and one cold, with the salt pumped between them | convention | Challenge before use | Accept — this is the reference design. A single thermocline tank could remove about half the tank steel, but that design is not estimated here | unverified — flagged |
| A-4: The salt operates between 288 °C (cold) and 566 °C (hot) | current constraint | Record expiry | Accept — holds until salts with a higher stability limit or a lower freezing point are adopted; until then it is set by the salt's chemistry | GT-2 |
| A-5: Stored sensible heat = m·cp·ΔT | physical law | Accept as ground-truth candidate | Accept — this relation is the definition of specific heat capacity | GT-3 |
| A-6: cp stays at 1.53 J/(g·K) across 288–566 °C | untested belief | Verify, or flag as unverified | Accept — cp changes only slightly with temperature. The effect of a ±3% change is worked out in C1 | unverified — flagged (effect quantified in C1) |
| A-7: 85% of the salt inventory is usable (range 80–92%); the rest is a "heel" left in the tank so the pumps stay submerged | untested belief | Verify, or flag as unverified | Challenge — no source was opened | GT-14? |
| A-8: Each tank's height equals its diameter (H = D), with 10% freeboard, and the cold tank is built the same size as the hot tank | convention | Challenge before use | Accept — the cold tank could have about 9% less volume because cold salt is denser (1,906.8 vs 1,730.0 kg/m³). Building it the same size is conservative | design choice |
| A-9: Tank wall thickness is set by fabrication minimums (6–12 mm), not by the pressure of the salt | convention | Challenge before use | Accept — C4 shows the salt's pressure alone needs only about 1.3 mm. The minimums stay because of welding, handling and buckling | GT-8? |
| A-10: Unit prices for salt, fabricated steel, pumps, piping, controls, insulation and foundations | untested belief | Verify, or flag as unverified | Challenge — no priced source was opened | GT-5?, GT-6?, GT-9?, GT-10? — unverified — flagged |
| A-11: Indirect costs (EPC margin, engineering, commissioning, contingency) multiply the direct cost by 1.35 (range 1.25–1.50) | convention | Challenge before use | Challenge — the multiplier is not sourced | GT-11? — unverified — flagged |
| A-12: Scope excludes the charging heater, the discharge heat exchanger and any power block | convention | Challenge before use | Accept — these are priced per kW of power, not per kWh of storage, so they are left out and the exclusion is stated | stated basis |
| A-13: Life is 30 years at 365 full cycles a year (low case: 20 years at 300 cycles a year) | untested belief | Verify, or flag as unverified | Challenge — no source was opened | GT-13? — unverified — flagged |
| A-14: Heat is lost continuously with both tanks at full temperature and 25 °C ambient; a 1.5× factor covers foundations, nozzles and piping | untested belief | Verify, or flag as unverified | Challenge — engineering estimate | unverified — flagged |
| A-15: Levelisation covers capital only, uses a 7% real discount rate, excludes O&M and charging energy, and is in 2026 USD | convention | Challenge before use | Accept — the cost is reported both undiscounted and discounted, so the reader can see what the discount rate changes | GT-16? |
| A-16: Salt density follows ρ = 2090 − 0.636·T(°C) kg/m³ | untested belief | Verify, or flag as unverified | Challenge — the source could not be opened (see the Phase 3 failure record) | GT-4? — unverified — flagged |
| A-17: Every cycle delivers the full 5 MWh_th (surfaced in the Assumption Audit) | untested belief | Verify, or flag as unverified | Challenge — the effect is covered by C8's low case, which has 55% of the central lifetime throughput | unverified — flagged |
| A-18: Charging energy costs more than about 2.4 ¢/kWh_th (surfaced in the Assumption Audit) | untested belief | Verify, or flag as unverified | Challenge — this affects only C8's third-order extension | unverified — flagged |
| A-19: Roof framing, nozzles and internals add 1.3× to the shell steel (surfaced in the Assumption Audit) | untested belief | Verify, or flag as unverified | Challenge — engineering allowance | unverified — flagged |
| A-20: Two pumps and 50 m of heat-traced piping are enough for 2.94 kg/s at a 4-hour discharge (surfaced in the Assumption Audit) | untested belief | Verify, or flag as unverified | Challenge — equipment count is estimated, not specified | unverified — flagged |

**Inversion pass (Phase 2):** the claim tested was "the estimate falls inside its bracket". Turning it around, the estimate would certainly be wrong if any of the following held: the stored quantity is electric, not thermal; the unit prices are off by more than the bracket; the scope of a real quote includes the charge and discharge equipment; or the store cycles far less than daily. The preconditions this exposes are already rows above: A-1 (load-bearing), A-10 (load-bearing), A-12 (load-bearing) and A-13 (load-bearing for the levelised figure only). All four are unverified, so they are the sharpest findings, and each is carried as a flagged assumption.

## 3. Ground Truths

- **GT-1** Solar salt (60:40 NaNO3/KNO3) has a heat capacity of 1.53 J/(g·K) and is liquid between 260 and 550 °C. Source: Wikipedia, "Molten salt". Read at source, quoted: "60:40 mixture of sodium nitrate and potassium nitrate is a liquid between 260 and 550 °C … and a heat capacity of 1.53 J/(g·K)." (A published property value.)
- **GT-2** In deployed plants the salt is "kept liquid at 288 °C … in an insulated 'cold' storage tank" and heated "to 566 °C". Source: Wikipedia, "Thermal energy storage", molten-salt section. Read at source, quoted wording as given. (Operating practice. This figure is above GT-1's stated 550 °C upper liquid limit; that conflict is resolved in §5.)
- **GT-3** Stored sensible heat is Q = m·cp·ΔT, and 1 kWh = 1,000 W × 3,600 s = 3.6×10⁶ J. Source: the definition of specific heat capacity and the SI definitions of the watt and joule. Definitional: the relation is worked out on the line above, so no external source is needed.
- **GT-4?** Salt density is ρ = 2090 − 0.636·T(°C) kg/m³. Cited to: Zavoico, *Solar Power Tower Design Basis Document*, SAND2001-2100. Unverified. **Phase 3 failure record:** osti.gov/biblio/786629 could not be reached (connection reset, ECONNRESET).
- **GT-5?** Delivered bulk salt costs $0.9/kg (range $0.5–1.5/kg). Unverified estimate. No source located. Not read — turn budget.
- **GT-6?** A fabricated tank costs, per kg of steel, $18/kg in 347H stainless (range $12–30) and $7/kg in carbon steel (range $4–12). Unverified estimate. No source located.
- **GT-7?** Steel density is 7,900 kg/m³. This is a handbook value; the handbook was not opened. Not read — turn budget.
- **GT-8?** The minimum practical shell or floor thickness for a tank about 3.4 m across is 6–12 mm (API 650 sets 5 mm for D < 15 m). Cited to: API 650. Not opened. Not read — turn budget.
- **GT-9?** Equipment prices: a molten-salt pump costs $40k (range $25–100k); heat-traced, insulated salt piping costs $800/m (range $400–1,500); instrumentation and controls cost $50k (range $25–100k). Unverified estimates. No source located.
- **GT-10?** Installed insulation (0.3 m mineral wool plus cladding) costs $150/m² (range $100–300). An insulated hot-tank foundation costs $1,500/m² (range $800–3,000). Unverified estimates. No source located.
- **GT-11?** The indirect-cost multiplier is 1.35 (range 1.25–1.50). Unverified estimate.
- **GT-12?** Mineral wool conducts heat at k = 0.075 W/(m·K) (range 0.06–0.09) at a mean temperature of about 300 °C. This is a handbook-type value; no source was opened. Not read — turn budget.
- **GT-13?** Design life is 30 years at 365 cycles a year (low case: 20 years at 300 cycles a year). Unverified estimate.
- **GT-14?** The usable fraction of the inventory is 0.85 (range 0.80–0.92). Unverified estimate.
- **GT-15?** The allowable stress for 347H stainless at 566 °C is about 80 MPa. Cited to: ASME Section II-D. Not opened. Not read — turn budget.
- **GT-16?** The discount rate is 7% real. This is a financing convention, not a fact.

**Reduce-to-primitives check (applied to the specific-energy claim in C1):** "Salt stores 0.118 kWh/kg" breaks down into cp (GT-1, a measurement), ΔT (GT-2, operating practice) and the energy-unit definition (GT-3). Every branch ends at a measurement or a definition, so C1's inputs are irreducible.

**Provenance summary:**

```text
?-marked: GT-4?, GT-5?, GT-6?, GT-7?, GT-8?, GT-9?, GT-10?, GT-11?, GT-12?, GT-13?, GT-14?, GT-15?, GT-16? (13 of 16)
Read-at-source: GT-1 — Wikipedia "Molten salt", 60:40 sentence quoted; GT-2 — Wikipedia "Thermal energy storage", molten-salt paragraph quoted; GT-3 — definitional
Phase 3 failure records: GT-4? (OSTI, ECONNRESET); NREL ATB CSP page (DNS ENOTFOUND) — benchmark for the §5 rival, not a ground truth
Not read — turn budget: GT-5?, GT-7?, GT-8?, GT-12?, GT-15?
```

## 4. Derivation Chains

Each chain is written in arrow-led lines, one step per line. Every computed figure was recomputed by an independent awk script (see the Adversarial pass record). In bracket figures, "low" means the cheapest case and "high" the most expensive.

### Conclusion C1: Solar salt cycled from 288 to 566 °C stores 0.11815 kWh_th per kg, so it needs 8.4638 kg per kWh_th

GT-1 (cp 1.53 J/g·K) + GT-2 (288 °C cold, 566 °C hot) + GT-3 (Q = m·cp·ΔT; 1 kWh = 3.6×10⁶ J)
→ the usable temperature swing is 566 − 288 = 278 K
→ heat stored per kg is 1,530 J/(kg·K) × 278 K = 425,340 J/kg *[Assumes: A-6 — cp constant over 288–566 °C]*
→ dividing by 3.6×10⁶ J/kWh gives 0.118150 kWh_th per kg
→ the salt needed is 1 / 0.118150 = 8.4638 kg per kWh_th stored

**Pre-check:** head GT-1, GT-2, GT-3 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH — GT-1 and GT-2 were read at source, GT-3 is definitional, and the arithmetic recomputes. A-6 is accounted for: if cp drifted ±3%, the figure would move only to 8.217–8.725 kg/kWh_th (8.4638/1.03 and 8.4638/0.97). Every bracket downstream absorbs that, so the endpoint stands to within ±3%. The strongest rival, capping the hot side at 550 °C, is §5 "Hot-side cap at 550 °C" and is ruled out by GT-2.

### Conclusion C2: The salt inventory of 49,787 kg costs $44,808, or $8.96/kWh_th (bracket $4.60–15.87)

C1 (8.4638 kg/kWh_th) + GT-14? (usable fraction 0.85) + GT-5? (salt $0.9/kg)
→ active salt for 5,000 kWh_th is 5,000 × 8.4638 = 42,319 kg
→ total inventory, including the heel that cannot be pumped out, is 42,319 / 0.85 = 49,787 kg
→ the salt costs 49,787 kg × $0.9/kg = $44,808
→ per unit of capacity that is $44,808 / 5,000 kWh = $8.96/kWh_th
→ the bracket is $4.60 (42,319/0.92 × $0.5 = $23,000) to $15.87 (42,319/0.80 × $1.5 = $79,348)

**Pre-check:** head C1 (HIGH), GT-14?, GT-5? · ?-marked: GT-14?, GT-5? · lowest cited: HIGH · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. GT-5? (salt price) would be closed by a delivered-price quote for bulk 60:40 nitrate salt. GT-14? (usable fraction) would be closed by the pump-submergence depth given in a vendor's tank design. Inference holds by arithmetic. Rival not applicable — once its inputs are fixed this is a product of three numbers.

### Conclusion C3: Two tanks of 31.66 m³ each cost $113,786, or $22.76/kWh_th (bracket $10.36–59.71)

C2 (49,787 kg inventory) + GT-4? (ρ = 2090 − 0.636·T) + GT-7? (steel 7,900 kg/m³) + GT-8? (shell 8 mm) + GT-6? (fabricated $/kg)
→ hot-salt density at 566 °C is 2090 − 0.636 × 566 = 1,730.0 kg/m³
→ each tank holds the full inventory plus 10% freeboard, 1.1 × 49,787 / 1,730.0 = 31.66 m³ *[Assumes: A-8 — H = D, cold tank identical]*
→ with H = D the diameter is (4 × 31.66 / π)^(1/3) = 3.429 m
→ shell plus roof plus floor area is 1.5 × π × 3.429² = 55.40 m² per tank
→ steel per tank is 55.40 m² × 0.008 m × 7,900 kg/m³ × 1.3 = 4,551 kg *[Assumes: A-19 — 1.3× for roof framing, nozzles, internals]*
→ the hot tank in 347H stainless costs 4,551 kg × $18/kg = $81,926
→ the cold tank in carbon steel costs 4,551 kg × $7/kg = $31,860
→ the two tanks total $113,786, or $113,786 / 5,000 = $22.76/kWh_th
→ the bracket is $10.36 (6 mm at $12 and $4/kg) to $59.71 (12 mm at $30 and $12/kg)

**Pre-check:** head C2 (MEDIUM), GT-4?, GT-7?, GT-8?, GT-6? · ?-marked: GT-4?, GT-7?, GT-8?, GT-6? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — the Inputs axis is short: C2 is MEDIUM, and GT-6? (fabricated $/kg) is the dominant unverified input, closed by a fabricator quote for a 3.4 m stainless tank. GT-4? would be closed by reading SAND2001-2100; GT-7? and GT-8? by opening a steel handbook and API 650. A-8 is accounted for: a cold tank sized to cold-salt density would hold 1,730.0/1,906.8 = 0.907 of the hot tank's volume; its surface area scales as volume^(2/3), giving 0.907^(2/3) = 0.937, so the steel and cold-tank cost fall by 6.3% ($2,001), well inside the bracket. A-19 is covered by the bracket's thickness range. Rival: §5 "Hydrostatic-thickness tanks", ruled out by C4 and GT-8?.

### Conclusion C4: The lowest cost physics allows is about $3.84/kWh_th (salt alone), and the salt's pressure needs only 1.30 mm of shell

GT-1 (liquid from 260 °C) + GT-2 (566 °C hot) + GT-3 (Q = m·cp·ΔT) + GT-5? (salt floor $0.5/kg) + GT-4? (density) + GT-15? (347H ~80 MPa) + GT-8? (6–12 mm minimum)
→ lower cost is better, so the bound sought is a floor, not a ceiling
→ the widest swing the sources read here allow is 566 − 260 = 306 K
→ at that swing, with no heel, the salt needed is 3.6×10⁶ / (1,530 × 306) = 7.689 kg/kWh_th
→ the floor for the salt alone is 7.689 kg × $0.5/kg = $3.84/kWh_th
→ salt pressure at a depth of 3.5 m is 1,730 × 9.81 × 3.5 = 59.4 kPa
→ the wall thickness that pressure needs (hoop stress) is 59,400 Pa × 1.75 m / 80×10⁶ Pa = 1.30 mm
→ the 6–12 mm shell used in C3 is therefore set by fabrication minimums, not by the salt's pressure

**Pre-check:** head GT-1, GT-2, GT-3, GT-5?, GT-4?, GT-15?, GT-8? · ?-marked: GT-5?, GT-4?, GT-15?, GT-8? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short: GT-5? (lowest salt price), GT-4? (density), GT-15? (allowable stress, closed by reading ASME II-D) and GT-8? (closed by reading API 650). Even if the allowable stress were half the figure used, the wall would need 2.6 mm, still below every fabrication minimum, so the endpoint stands. The middle tier of the cost range, the best cost actually achieved by built systems, is **not established**: its source, the NREL ATB page, could not be reached (Phase 3 failure record). Rival not applicable — this chain states a bound, not a choice.

### Conclusion C5: Installed capital cost is $499,691, or $99.94/kWh_th (bracket $48.15–251.83)

C2 (salt $44,808) + C3 (tanks $113,786; D = 3.429 m) + GT-10? (insulation, foundation) + GT-9? (pumps, piping, controls) + GT-11? (indirects ×1.35)
→ insulated wall and roof area is 1.25 × π × 3.429² = 46.16 m² per tank
→ insulation for both tanks costs 2 × 46.16 m² × $150/m² = $13,849
→ foundation footprint is π × 3.429² / 4 = 9.233 m² per tank
→ foundations for both tanks cost 2 × 9.233 m² × $1,500/m² = $27,699
→ at a 4-hour discharge the salt flow is 1.25×10⁶ W / 425,340 J/kg = 2.94 kg/s
→ equipment that does not grow with capacity is 2 × $40,000 pumps + 50 m × $800/m piping + $50,000 controls = $170,000 *[Assumes: A-20 — two pumps and 50 m of piping suffice]*
→ direct cost totals 44,808 + 113,786 + 13,849 + 27,699 + 170,000 = $370,142
→ installed cost including indirects is $370,142 × 1.35 = $499,691
→ per unit of capacity that is $499,691 / 5,000 kWh_th = $99.94/kWh_th
→ the bracket is $48.15 (all low-cost inputs, total $240,727) to $251.83 (all high-cost inputs, total $1,259,155)

**Pre-check:** head C2 (MEDIUM), C3 (MEDIUM), GT-10?, GT-9?, GT-11? · ?-marked: GT-10?, GT-9?, GT-11? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. C2 and C3 are MEDIUM. GT-9? (equipment prices, the largest single block at 45.9% of direct cost) would be closed by a quote for a small vertical molten-salt pump plus heat-traced piping. GT-10? and GT-11? would be closed by an EPC estimate for the same scope. A-20 is accounted for by GT-9?'s range: the high case already allows $200,000 for pumps. The rival estimate, $20–30/kWh_th scaled down from utility-scale plants, is §5 "Scaling from utility-scale CSP storage" and is ruled out by C6.

### Conclusion C6: At 5 MWh_th, the salt is 12.1% of direct cost, and installed cost is 26× the lowest the physics allows

C5 (capex $99.94/kWh_th; direct $370,142) + C2 (salt $44,808) + C4 (floor $3.84/kWh_th)
→ the salt is $44,808 / $370,142 = 12.1% of direct cost
→ equipment that does not grow with capacity is $170,000 / $370,142 = 45.9% of direct cost
→ installed cost is $99.94 / $3.8447 = 26.0× the salt-only floor
→ at this size the $/kWh is set by how many pieces of equipment are needed and by fabrication minimums, not by how much heat the salt can hold

**Pre-check:** head C5 (MEDIUM), C2 (MEDIUM), C4 (MEDIUM) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — capped by C5, C2 and C4, which are all MEDIUM. The endpoint holds even at C5's lowest-cost bracket: the low case's salt is $23,000 of $192,581 direct cost (11.9%), and its fixed equipment is $95,000 (49.3%). The rival reading, that the salt sets the cost, is the §5 utility-scale entry, ruled out here.

### Conclusion C7: The store retains 92.0% of its heat per day on a one-cycle-per-day duty (bracket 90.0–93.9%)

C3 (area 55.40 m² per tank) + GT-12? (k = 0.075 W/m·K) + GT-2 (566 / 288 °C)
→ 0.3 m of insulation gives a heat-loss coefficient U = 0.075 / 0.3 = 0.25 W/(m²·K) *[Assumes: A-14 — continuous loss, 25 °C ambient, ×1.5 for penetrations]*
→ loss from the two tanks is 0.25 × 55.40 × ((566 − 25) + (288 − 25)) = 0.25 × 55.40 × 804 = 11,135 W
→ adding 1.5× for foundations, nozzles and piping gives 16,702 W in total
→ the daily loss is 16,702 W × 24 h = 400.9 kWh_th
→ daily retention is 1 − 400.9 / 5,000 = 0.9198
→ the bracket is 0.8998 (k = 0.09) to 0.9392 (k = 0.06)

**Pre-check:** head C3 (MEDIUM), GT-12?, GT-2 · ?-marked: GT-12? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short: C3 is MEDIUM, and GT-12? would be closed by an insulation datasheet value for k at 300 °C. A-14 is accounted for: assuming continuous loss at full temperature overstates the loss, so the true retention is at or above this figure and the endpoint holds as a lower estimate. Rival not applicable — the figure comes from geometry and conduction, with no competing reading of the same inputs.

### Conclusion C8: Levelised capital cost is 0.99 ¢/kWh_th delivered undiscounted, or 2.40 ¢/kWh_th at 7% real (brackets 0.47–4.66 ¢ and 1.13–8.81 ¢)

C5 ($99.94/kWh_th; $499,691) + C7 (retention 0.9198) + GT-13? (30 yr × 365 cycles) + GT-16? (7% real)
→ lifetime full cycles are 30 × 365 = 10,950 *[Assumes: A-17 — every cycle delivers the full 5 MWh_th]*
→ undiscounted, each kWh of capacity delivers 10,950 × 0.9198 = 10,071.8 kWh_th over the store's life
→ simple amortised capital is $99.94 / 10,071.8 = $0.00992/kWh_th, about 0.99 ¢
→ the capital recovery factor at 7% real over 30 years is 0.07 × 1.07³⁰ / (1.07³⁰ − 1) = 0.5329 / 6.6123 = 0.08059
→ the annual capital charge is $499,691 × 0.08059 = $40,270
→ annual heat delivered is 5,000 × 0.9198 × 365 = 1,678,635 kWh_th
→ discounted levelised capital is $40,270 / 1,678,635 = $0.0240/kWh_th, about 2.40 ¢
→ the expensive end of the bracket uses 20 years × 300 cycles = 6,000 cycles with a recovery factor of 0.09439
→ the brackets are 0.47–4.66 ¢ simple and 1.13–8.81 ¢ discounted
→[2nd] (actor lens, financier) a lender prices the 2.40 ¢ discounted figure, not the 0.99 ¢ simple one, so screening uses 2.40 ¢
→[2nd] (time lens, a few cycles) each idle day loses 400.9 kWh_th, 8.0% of capacity, so the store suits duties that cycle daily
→[3rd] (time lens, long run) with capital at about 2.4 ¢/kWh_th, the cost of charging energy becomes the larger cost per kWh delivered *[Assumes: A-18 — charging energy costs more than about 2.4 ¢/kWh]*

**Pre-check:** head C5 (MEDIUM), C7 (MEDIUM), GT-13?, GT-16? · ?-marked: GT-13?, GT-16? · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — only the Inputs axis is short. C5 and C7 are MEDIUM. GT-13? (life and cycling) would be closed by the operating profile of the intended duty. GT-16? is a financing choice, closed by the owner's actual cost of capital; both bases are reported, so a reader can pick either. A-17 is accounted for: the expensive bracket assumes 55% of the central lifetime throughput (6,000/10,950 = 0.548), and the result stays below 9 ¢. A-18 applies only to the third-order extension, not to the endpoint. Rival not applicable — the two figures are the same cost on two stated bases, not competing conclusions.

## 5. Abandoned Reasoning

### Dead End: Scaling from utility-scale CSP storage

**What was tried:** Taking the $/kWh_th cost of storage at utility-scale concentrating-solar (CSP) plants, often reported in the $20–30/kWh_th range, and applying it to a 5 MWh_th store. That figure was never read: the source checked for it, the NREL ATB CSP page, could not be reached (Phase 3 failure record, DNS ENOTFOUND).

**Why abandoned:** It reasons by analogy, and its figure is unverified. More decisively, C6 shows that at 5 MWh_th the salt is only 12.1% of direct cost, while equipment that does not grow with capacity is 45.9%. A per-kWh figure from a store hundreds of times larger spreads those fixed items over far more kWh, so it cannot be carried across.

**What it ruled out:** A central estimate near $20–30/kWh_th for this size, which is the strongest rival to C5. Ruled out by C6.

### Dead End: Hot-side cap at 550 °C

**What was tried:** Using the 550 °C upper liquid limit from GT-1 as the hot-tank temperature. The swing would then be 550 − 288 = 262 K, and the salt needed 3.6×10⁶ / (1,530 × 262) = 8.981 kg/kWh_th, which is 8.981 / 8.4638 = 1.061, or 6.1% more salt.

**Why abandoned:** GT-2, read at source, records 566 °C as the hot temperature used in deployed plants. GT-1's 550 °C is a statement of the salt's liquid range, not of how hot plants run it.

**What it ruled out:** A 6.1% larger salt inventory in C1 and C2. Ruled out by GT-2.

### Dead End: Hydrostatic-thickness tanks

**What was tried:** Sizing the tank walls to the 1.30 mm the salt's pressure requires (C4) instead of 8 mm. Tank steel and tank cost would then fall to 1.30/8 = 16.3% of the C3 figure: $113,786 × 0.1625 = $18,490.

**Why abandoned:** Tanks of this size are not built thinner than fabrication minimums (GT-8?), because of welding, handling, wind and buckling. The pressure bound is real but does not decide the thickness.

**What it ruled out:** A tank cost near $3.7/kWh_th. The strongest rival to C3 is ruled out by C4 and GT-8?.

### Dead End: Electric-basis reading of "5 MWh"

**What was tried:** Reading the 5 MWh as electricity out. Assuming 30% heat-to-power efficiency (unverified), the capital cost expressed per kWh_e of output would be $99.94 / 0.30 = $333.1/kWh_e. The levelised capital would be 2.40 ¢ / 0.30 = 8.0 ¢/kWh_e, before any power-block cost. A store giving 5 MWh_e would need 5 / 0.30 = 16.67 MWh_th, a larger system this analysis did not estimate.

**Why abandoned as the primary basis:** A thermal store's stored quantity is heat (GT-3, A-1). The electric reading adds an unverified conversion efficiency and power-block scope that are outside the storage system as stated (A-12).

**What it ruled out:** Reporting electric-basis figures as the headline. The conversion above is left here for a reader who meant electricity.

## 6. Conclusion

**Recommended approach:** Use about $100/kWh_th of usable capacity ($99.94; $499,691 installed) as the central capital cost for a 5 MWh_th two-tank solar-salt store, and carry its bracket of $48–252/kWh_th with it (chain C5).

**Levelised cost per kWh delivered:** Spread over 10,950 daily cycles at 92.0% daily heat retention, capital comes to 0.99 ¢/kWh_th undiscounted, or 2.40 ¢/kWh_th at 7% real (bracket 1.13–8.81 ¢) (chain C8, chain C7).

**Key insight:** At this size the salt is only 12.1% of direct cost, and installed cost is 26× the salt-only floor the physics allows, so the cost is set by equipment count and fabrication minimums rather than by how much heat the salt can hold (chain C6, chain C4).

**Trade-offs acknowledged:** The figures leave out the charging heater, the discharge heat exchanger, O&M and charging energy, and they assume daily full cycling. Each idle day loses 8.0% of capacity, and over the long run the cost of charging energy, not the hardware, becomes the larger cost per kWh delivered (chain C8).

**Pre-check:** head C4 (MEDIUM), C5 (MEDIUM), C6 (MEDIUM), C7 (MEDIUM), C8 (MEDIUM) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — chains C4, C5, C6, C7 and C8 are each MEDIUM, and each confidence line names its own unverified inputs and how to close them. The biggest of these are the equipment and fabricated-steel prices (GT-9?, GT-6?) under C5, which a vendor quote for the same scope would close. No unverified input is used directly here without going through a chain.

## Appendix — process output

## Assumption Audit scan (process output)

| Chain | Step | Step Text (brief) | Assumption surfaced? | Added to Table? |
|---|---|---|---|---|
| C1 | 1 | ΔT = 278 K | no | n/a |
| C1 | 2 | 425,340 J/kg | A-6 (already in table) | already present |
| C1 | 3 | 0.118150 kWh/kg | no | n/a |
| C1 | 4 | 8.4638 kg/kWh | no | n/a |
| C2 | 1 | 42,319 kg active | no | n/a |
| C2 | 2 | 49,787 kg total | A-7 (already) | already present |
| C2 | 3 | $44,808 | no | n/a |
| C2 | 4 | $8.96/kWh | no | n/a |
| C2 | 5 | bracket | no | n/a |
| C3 | 1 | ρ 1,730.0 | A-16 (already) | already present |
| C3 | 2 | 31.66 m³ | A-8 (already) | already present |
| C3 | 3 | D 3.429 m | no | n/a |
| C3 | 4 | 55.40 m² | no | n/a |
| C3 | 5 | 4,551 kg steel | A-19 — 1.3× steel allowance | yes, added as A-19 |
| C3 | 6 | hot tank $81,926 | no | n/a |
| C3 | 7 | cold tank $31,860 | no | n/a |
| C3 | 8 | $113,786 | no | n/a |
| C3 | 9 | bracket | no | n/a |
| C4 | 1 | floor direction | no | n/a |
| C4 | 2 | ΔT 306 K | no | n/a |
| C4 | 3 | 7.689 kg/kWh | no | n/a |
| C4 | 4 | $3.84/kWh | no | n/a |
| C4 | 5 | 59.4 kPa | no | n/a |
| C4 | 6 | 1.30 mm | no | n/a |
| C4 | 7 | fabrication minimums govern | A-9 (already) | already present |
| C5 | 1 | insulated area 46.16 m² | no | n/a |
| C5 | 2 | insulation $13,849 | no | n/a |
| C5 | 3 | footprint 9.233 m² | no | n/a |
| C5 | 4 | foundation $27,699 | no | n/a |
| C5 | 5 | 2.94 kg/s | no | n/a |
| C5 | 6 | fixed equipment $170,000 | A-20 — 2 pumps, 50 m piping suffice | yes, added as A-20 |
| C5 | 7 | direct $370,142 | no | n/a |
| C5 | 8 | ×1.35 = $499,691 | A-11 (already) | already present |
| C5 | 9 | $99.94/kWh | no | n/a |
| C5 | 10 | bracket | no | n/a |
| C6 | 1 | salt 12.1% | no | n/a |
| C6 | 2 | fixed 45.9% | no | n/a |
| C6 | 3 | 26.0× floor | no | n/a |
| C6 | 4 | equipment count governs | no | n/a |
| C7 | 1 | U 0.25 | A-14 (already) | already present |
| C7 | 2 | 11,135 W | no | n/a |
| C7 | 3 | 16,702 W | no | n/a |
| C7 | 4 | 400.9 kWh/day | no | n/a |
| C7 | 5 | η 0.9198 | no | n/a |
| C7 | 6 | bracket | no | n/a |
| C8 | 1 | 10,950 cycles | A-17 — full 5 MWh each cycle | yes, added as A-17 |
| C8 | 2 | 10,071.8 kWh/kWh | no | n/a |
| C8 | 3 | 0.99 ¢ | no | n/a |
| C8 | 4 | CRF 0.08059 | A-15 (already) | already present |
| C8 | 5 | $40,270/yr | no | n/a |
| C8 | 6 | 1,678,635 kWh/yr | no | n/a |
| C8 | 7 | 2.40 ¢ | no | n/a |
| C8 | 8 | expensive-end cycles 6,000, CRF 0.09439 | A-13 (already) | already present |
| C8 | 9 | brackets | no | n/a |
| C8 | [2nd] a | financier uses 2.40 ¢ | no | n/a |
| C8 | [2nd] b | idle-day loss 8.0% | no | n/a |
| C8 | [3rd] | charging energy dominates | A-18 — charging energy above ~2.4 ¢/kWh | yes, added as A-18 |

Second-order pass (C8): actor lens (financier, owner/operator) and time lens (a few cycles, long run) were both walked. No effect contradicts a ground truth. Checked against the success criteria, no effect defeats the purpose of the estimate. The idle-loss effect narrows which duties the store suits; it does not change the estimate.

## Techniques not applied (process output)

- fishbone — not applicable — the uncertainty is a cost total that can be broken into components, not a set of causes spread across categories
- trade-off — not applicable — the question is an estimate, not a choice between surviving options
- pre-mortem — not applicable — the conclusion is a claim (an estimate), not a plan; the Phase 5 adversarial pass therefore uses inversion
- theoretical-limit — not applicable — at Phase 1 the essence does not depend on whether a current figure is a convention or a hard bound; the bound is derived in Phase 4 instead (C4)

## Adversarial pass (process output)

**Recompute:** Every figure was recomputed by an awk script written separately from the Python scenario model. Each line gives the chain value, then the recomputed value.
- C1: 425,340 J/kg (425,340); 8.4638 kg/kWh (8.4638).
- C2: 42,319 kg (42,319); 49,787 kg (49,787); $44,808 (44,808); bracket 4.60 / 15.87 (4.60 / 15.87).
- C3: ρ 1,730.0 (1,730.0); V 31.66 m³ (31.656); D 3.429 m (3.4286); A 55.40 m² (55.397); steel 4,551 kg (4,551); $81,926 / $31,860 (81,926 / 31,860); cold-tank saving $2,001 (2,001).
- C4: 7.689 kg/kWh (7.689); $3.84 (3.8447); 1.30 mm (1.30).
- C5: insulation $13,849 (13,849); foundation $27,699 (27,699); flow 2.94 kg/s (2.939); direct $370,142 (370,142); total $499,691 (499,691); $99.94/kWh (99.94); bracket 48.15 / 251.83 (48.15 / 251.83).
- C6: 12.1% (0.121); 45.9% (0.459); 26.0× (25.99); low case 11.9% / 49.3% (0.1194 / 0.4933).
- C7: 16,702 W (16,702); η 0.9198 (0.9198); bracket 0.8998 / 0.9392 (0.8998 / 0.9392).
- C8: CRF 0.08059 (0.080586); simple 0.99 ¢ (0.0099 $); discounted 2.40 ¢ (0.0240 $); throughput ratio 0.548 (0.548).
- §5: 8.981 kg/kWh (8.981).

Chain-form note: before the gate was scored, three hops (two in C5, one in C8) that each carried two inferences were split into one-inference hops, and the audit rows above were re-run for them. No figure changed.

Direction checks: the ×1.35 indirect multiplier raises $370,142 to $499,691, so it lands above its base as it should. Each ÷η step raises the cost per kWh delivered. No figure lands on the wrong side of its operation.

**Sensitivity:** For the headline magnitude, the single input whose falsity matters most is GT-9? (equipment prices), and it is `?`-marked. If the pumps, piping and controls together cost only $20,000, capital would be (200,142 + 20,000) × 1.35 = $297,192 = $59.44/kWh_th. That is still inside the C5 bracket, and the salt share would rise only to 44,808/220,142 = 20.4%, so the key insight (C6) does not flip. This input is not verified now and keeps its confidence caveat on C5. Weakest link in each chain:
- C1: A-6 (cp constant).
- C2: GT-5? (salt price).
- C3: GT-6? (fabricated $/kg).
- C4: the middle tier of its cost range (best cost achieved by built systems) is not established.
- C5: GT-9?.
- C6: inherited from C5.
- C7: A-14 (continuous loss).
- C8: GT-13? (cycling profile).

**Rival:** For the headline (C5), the rival is the utility-scale-derived $20–30/kWh_th, recorded in §5 "Scaling from utility-scale CSP storage". For C1, the 550 °C cap is in §5. For C3, the hydrostatic-thickness tank is in §5. For C2, C7 and C8, the rival is not applicable, with the reason stated on each chain's confidence line. C4 states a bound, so rival not applicable. For C6, the rival is the utility-scale entry, ruled out there.

**Premise:** The estimate is already false: the true installed cost of a 5 MWh_th two-tank solar-salt store lies outside $48–252/kWh_th, or its levelised capital lies outside 1.13–8.81 ¢/kWh_th.

**Causes:** written from three viewpoints before grouping, and not filtered.
- EPC vendor: the quote included the charging heater, the heat exchanger and an electric preheat system, priced into $/kWh. Small salt pumps were not available, so oversized industrial units were bought. Engineering hours did not shrink with the plant. A packaged product spread design costs over many units and came in below the bracket. Stainless prices spiked.
- Owner/operator: "5 MWh" meant electricity out, so the system was 3× larger. The heel was larger than 20% because of pump-submergence rules. The salt froze in a line, and the repair cost was folded into capital. Heat loss doubled because the insulation was thinner than 0.3 m.
- Financier: the store cycled 150 times a year, not 365. Its life was 15 years because of hot-tank corrosion. The cost of capital was 10%, not 7%.

**Clusters:**
1. Scope and definition mismatch (A-1, A-12; bears on C5 and C8). The quote prices different equipment or a different energy basis.
2. Fixed-equipment and fabrication pricing (GT-9?, GT-6?, GT-11?; bears on C3 and C5). Real prices for small equipment or tanks fall outside the bracket, whether packaged units come in cheaper or oversized units come in dearer.
3. Utilisation and durability (GT-13?, GT-16?, A-17; bears on C8). Fewer cycles, shorter life or costlier capital push the levelised figure up.
4. Thermal performance (GT-12?, A-14; bears on C7). Losses run larger than modelled.

**Disposition:**
1. Plan change made: the scope and the thermal basis are stated in §1, §2 and §6, and the electric conversion is given in §5. Accepted risk; mitigation is to compare any quote on the same scope.
2. Accepted risk; mitigation is that the bracket spans 5.2× (48.15 to 251.83), and the C5 confidence line names the vendor quote that would close it.
3. Accepted risk; mitigation is that both simple and discounted figures are reported, and the expensive bracket already assumes 55% of the throughput. Tripwire: a planned duty below 300 cycles a year, or a cost of capital above 7%, means recomputing C8.
4. Accepted risk; mitigation is that the modelled loss assumes continuous full-temperature loss, which errs pessimistic, plus a 1.5× allowance, and the bracket spans 0.8998–0.9392.

**Falsification:** The conclusion is false if a quote for a turnkey 5 MWh_th two-tank solar-salt store with the same scope (tanks, salt, insulation, foundations, pumps, piping and controls; no heater, heat exchanger or power block) lands outside $48–252/kWh_th. The key insight is false if, in such a quote, the salt is more than about a quarter of direct cost.

## §6→§4 closure ledger (process output)

- "Use about $100/kWh_th of usable capacity … carry its bracket of $48–252/kWh_th" → chain C5 ✓
- "capital comes to 0.99 ¢/kWh_th undiscounted, or 2.40 ¢/kWh_th at 7% real" → chain C8 ✓ (retention from chain C7 ✓)
- "the salt is only 12.1% of direct cost, and installed cost is 26× the salt-only floor" → chain C6 ✓ (floor from chain C4 ✓)
- "The figures leave out the charging heater … the cost of charging energy … becomes the larger cost" → chain C8 ✓
- "**Pre-check:** head C4 (MEDIUM) … Inputs ceiling: MEDIUM" → chains C4, C5, C6, C7, C8 ✓
- "**Confidence:** MEDIUM — chains C4, C5, C6, C7 and C8 are each MEDIUM" → chains C4–C8 ✓

No claim was cut.

## Self-audit scan (process output)

| Chain | Chain Head (brief) | Form conforming? | Rule applied | Dependency clean? | Band | Act attempted? | Edges fired |
|---|---|---|---|---|---|---|---|
| C1 | GT-1 + GT-2 + GT-3 | yes | n/a | yes | HIGH | yes | none |
| C2 | C1 + GT-14? + GT-5? | yes | n/a | yes | MEDIUM | no | none |
| C3 | C2 + GT-4? + GT-7? + GT-8? + GT-6? | yes | n/a | yes | MEDIUM | yes | none |
| C4 | GT-1 + GT-2 + GT-3 + GT-5? + GT-4? + GT-15? + GT-8? | yes | n/a | yes | MEDIUM | yes | none |
| C5 | C2 + C3 + GT-10? + GT-9? + GT-11? | yes | n/a | yes | MEDIUM | no | none |
| C6 | C5 + C2 + C4 | yes | n/a | yes | MEDIUM | no | none |
| C7 | C3 + GT-12? + GT-2 | yes | n/a | yes | MEDIUM | yes | none |
| C8 | C5 + C7 + GT-13? + GT-16? | yes | n/a | yes | MEDIUM | no | none |

| §6 Span (brief) | Construct | Claim under R11? | R11 clause applied | Chain cited |
|---|---|---|---|---|
| Recommended approach: ~$100/kWh_th, bracket $48–252 | bold lead-in | yes | bold lead-in whose colon closes the bold span | C5 |
| Levelised cost: 0.99 ¢ / 2.40 ¢ | bold lead-in | yes | bold lead-in whose colon closes the bold span | C8, C7 |
| Key insight: salt 12.1%, 26× floor | bold lead-in | yes | bold lead-in whose colon closes the bold span | C6, C4 |
| Trade-offs acknowledged: exclusions, daily cycling | bold lead-in | yes | bold lead-in whose colon closes the bold span | C8 |
| Pre-check: head C4–C8 | bold lead-in | yes | bold lead-in whose colon closes the bold span | C4, C5, C6, C7, C8 |
| Confidence: MEDIUM | bold lead-in | yes | bold lead-in whose colon closes the bold span | C4, C5, C6, C7, C8 |

```text
Scan complete: 8 chain rows, one per section-4 chain block in order; 6 section-6 rows, one per construct in order — 6 claims under R11, 0 excluded. 0 chains malformed, 0 claims untraced.
```

## Self-Audit Gate (process output)

**Criterion 1: Identify Essence**
Quoted span: "1. The salt requirement comes from physics (energy = mass × specific heat × temperature swing), and every unit cancels in the working."
Band: **Sound**
Justification: The Essence Statement names the real question in a single sentence and criteria 3–5 test properties of the Conclusion section. Criteria 1 and 2, though, test the derivation process rather than a property a reviewer can check by scanning §6, so not every criterion meets the verb + subject + Conclusion-outcome test.

**Criterion 2: Challenge Assumptions**
Quoted span: "| C3 | 5 | 4,551 kg steel | A-19 — 1.3× steel allowance | yes, added as A-19 |" (Assumption Audit scan)
Band: **Rigorous**
Justification: All 20 rows use the four-type scheme, with verdicts written as token plus em-dash and several of them Challenge. Unverified rows used in chains read "unverified — flagged". The audit has one row per step for all eight chains, including the split hops, and surfaced four new assumptions (A-17 to A-20), each recorded in the table.

**Criterion 3: Establish Ground Truths**
Quoted span: comparison — the enumeration lists GT-4? through GT-16? (13 of 16), and the Ground Truths list carries `?` on exactly those 13. The unsuffixed GT-1 and GT-2 name quoted read-at-source passages, and GT-3 is definitional.
Band: **Rigorous**
Justification: The enumeration matches the list. Every unsuffixed ground truth feeds the HIGH chain C1 with a named read location, and the unreachable sources (OSTI, NREL ATB) carry Phase 3 failure records. The standards and handbook values not opened (GT-7?, GT-8?, GT-12?, GT-15?) keep their `?` and are disclosed as not read.

**Criterion 4: Reason Upward**
Quoted span: "| C5 | C2 + C3 + GT-10? + GT-9? + GT-11? | yes | n/a | yes | MEDIUM | no | none |" (self-audit scan), and from §5: "**Why abandoned:** It reasons by analogy, and its figure is unverified."
Band: **Rigorous**
Justification: All eight chains conform, with clean dependencies and at least one intermediate step each. Every hop's arithmetic recomputes in the independent awk pass. Assumptions are declared inline, and the one analogy (utility-scale cost) appears only in §5 as an abandoned rival, never as evidence.

**Criterion 5: Validate**
Quoted span: "**Confidence:** MEDIUM — only the Inputs axis is short. C2 and C3 are MEDIUM. GT-9? (equipment prices, the largest single block at 45.9% of direct cost) would be closed by a quote for a small vertical molten-salt pump plus heat-traced piping."
Band: **Rigorous**
Justification: Every MEDIUM line names its own `?` inputs and cited chains, with a verification path for each. C1 is HIGH, with read inputs, its A-6 assumption accounted for and its rival ruled out. The Conclusion's MEDIUM equals its weakest chain. The adversarial record carries every part: recompute, sensitivity, rival, past-tense premise, a cause list from three viewpoints, clusters with ids, a disposition per cluster, and a falsification condition.

**Criterion 6: Conclusion-to-Ground-Truth Traceability**
Quoted span: "| Key insight: salt 12.1%, 26× floor | bold lead-in | yes | bold lead-in whose colon closes the bold span | C6, C4 |" (self-audit scan)
Band: **Rigorous**
Justification: All six §6 claims cite named chains, and none introduces reasoning absent from §4. The Key Insight (cost set by equipment count, not by the salt) is a non-obvious finding that scaling from utility-scale plants would miss, not a restatement of the $100/kWh_th recommendation.

**Gate result:** cleared · passes: 1 · Fix/Repeat fired: no

## Structured summary (process output)

```json
{
  "schema_version": 1,
  "run_mode": "full-composer",
  "assumptions": [
    {"id": "A-1", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-2", "type": "convention", "verdict": "Accept"},
    {"id": "A-3", "type": "convention", "verdict": "Accept"},
    {"id": "A-4", "type": "current constraint", "verdict": "Accept"},
    {"id": "A-5", "type": "physical law", "verdict": "Accept"},
    {"id": "A-6", "type": "untested belief", "verdict": "Accept"},
    {"id": "A-7", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-8", "type": "convention", "verdict": "Accept"},
    {"id": "A-9", "type": "convention", "verdict": "Accept"},
    {"id": "A-10", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-11", "type": "convention", "verdict": "Challenge"},
    {"id": "A-12", "type": "convention", "verdict": "Accept"},
    {"id": "A-13", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-14", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-15", "type": "convention", "verdict": "Accept"},
    {"id": "A-16", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-17", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-18", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-19", "type": "untested belief", "verdict": "Challenge"},
    {"id": "A-20", "type": "untested belief", "verdict": "Challenge"}
  ],
  "ground_truths": [
    {"id": "GT-1", "read_at_source": true},
    {"id": "GT-2", "read_at_source": true},
    {"id": "GT-3", "read_at_source": true},
    {"id": "GT-4", "read_at_source": false},
    {"id": "GT-5", "read_at_source": false},
    {"id": "GT-6", "read_at_source": false},
    {"id": "GT-7", "read_at_source": false},
    {"id": "GT-8", "read_at_source": false},
    {"id": "GT-9", "read_at_source": false},
    {"id": "GT-10", "read_at_source": false},
    {"id": "GT-11", "read_at_source": false},
    {"id": "GT-12", "read_at_source": false},
    {"id": "GT-13", "read_at_source": false},
    {"id": "GT-14", "read_at_source": false},
    {"id": "GT-15", "read_at_source": false},
    {"id": "GT-16", "read_at_source": false}
  ],
  "chains": [
    {"id": "C1", "confidence": "HIGH", "rests_on": ["GT-1", "GT-2", "GT-3"]},
    {"id": "C2", "confidence": "MEDIUM", "rests_on": ["C1", "GT-14?", "GT-5?"]},
    {"id": "C3", "confidence": "MEDIUM", "rests_on": ["C2", "GT-4?", "GT-7?", "GT-8?", "GT-6?"]},
    {"id": "C4", "confidence": "MEDIUM", "rests_on": ["GT-1", "GT-2", "GT-3", "GT-5?", "GT-4?", "GT-15?", "GT-8?"]},
    {"id": "C5", "confidence": "MEDIUM", "rests_on": ["C2", "C3", "GT-10?", "GT-9?", "GT-11?"]},
    {"id": "C6", "confidence": "MEDIUM", "rests_on": ["C5", "C2", "C4"]},
    {"id": "C7", "confidence": "MEDIUM", "rests_on": ["C3", "GT-12?", "GT-2"]},
    {"id": "C8", "confidence": "MEDIUM", "rests_on": ["C5", "C7", "GT-13?", "GT-16?"]}
  ],
  "dead_ends": [
    "Scaling from utility-scale CSP storage",
    "Hot-side cap at 550 °C",
    "Hydrostatic-thickness tanks",
    "Electric-basis reading of \"5 MWh\""
  ],
  "techniques": {
    "applied": ["inversion", "five-whys", "estimate", "theoretical-limit", "second-order"],
    "not_applied": [
      {"technique": "fishbone", "phase": 2, "reason": "the uncertainty is a cost total that can be broken into components, not a set of causes spread across categories"},
      {"technique": "trade-off", "phase": 4, "reason": "the question is an estimate, not a choice between surviving options"},
      {"technique": "pre-mortem", "phase": 5, "reason": "the conclusion is a claim (an estimate), not a plan; the Phase 5 adversarial pass therefore uses inversion"},
      {"technique": "theoretical-limit", "phase": 1, "reason": "at Phase 1 the essence does not depend on whether a current figure is a convention or a hard bound; the bound is derived in Phase 4 instead (C4)"}
    ]
  },
  "gate": {
    "passes": [
      {"bands": ["Sound", "Rigorous", "Rigorous", "Rigorous", "Rigorous", "Rigorous"], "gate_cleared": true, "hand_wavy_cap_cleared": true}
    ],
    "fix_repeat_fired": false,
    "cleared": true
  },
  "re_entry": {"fired": false, "edges": []},
  "conclusion": {
    "recommendation": "Use about $100/kWh_th of usable capacity ($99.94; $499,691 installed) as the central capital cost for a 5 MWh_th two-tank solar-salt store, and carry its bracket of $48–252/kWh_th with it (chain C5).",
    "confidence": "MEDIUM"
  }
}
```
