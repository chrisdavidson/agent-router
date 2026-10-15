<!-- GENERATED — DO NOT EDIT. Source: shared/examples/product-business.md. Regenerate via: scripts/sync-content.py --write. -->

# Worked Example: Product and Business

A complete first-principles analysis of a product and business pricing question, following the standardized output format. The Phase 2 Classified Assumptions Table is the deepest section of analysis — seven assumptions examined, two discarded outright — and the abandoned reasoning path demonstrates the Phase 4 no-analogies guidance applied to a competitor-parity argument. Authored in Phase 5.

---

## 1. Problem Essence

**Core problem:** Does this B2B SaaS product's own economics support adding a free tier, or is the case for one resting entirely on unverified beliefs and competitor analogy?

**Success criteria:**
- A verifiable data gap (the product's free-to-paid conversion rate) is either measured or a concrete plan to measure it is recommended.
- The competitor-parity argument ("all our competitors have a free tier") is tested against the Phase 4 no-analogies guidance (SKILL.md, Phase 4 Operation), with a clear verdict on whether it can anchor a decision.
- The recommendation is grounded in what is actually known about this product's acquisition model, cost structure, and ICP behavior — not in industry convention.
- A skeptic can evaluate whether a free tier is the right move for this specific product at this specific ARR stage, using only the reasoning and ground truths in this document.

---

## 2. Assumptions Table

| Assumption | Type | Treatment | Verdict | Verification |
|------------|------|-----------|---------|--------------|
| A free tier drives top-of-funnel growth | untested belief | Verify, or flag as unverified. Free-tier growth depends on whether the ICP self-serves — not a universal law. | Challenge — unverified for B2B outbound-led SaaS; true only for some self-serve products | unverified — flagged; true for some products (consumer tools, developer utilities), not for B2B outbound-led SaaS |
| Free users convert to paid at a meaningful rate | untested belief | Verify, or flag as unverified. Conversion rate is the economic hinge of the entire decision. | Challenge — no conversion data exists for this product/ICP segment (confirmed absent in GT-4?) | unverified — flagged; no conversion data exists for this product in this ICP segment (confirmed absent in GT-4?) |
| Competitors' free-tier economics are profitable | untested belief | Verify against published data, or flag. Competitor ARR, cost structure, and conversion rates are not observable without disclosure. | Challenge — no public data on competitors' free-tier unit economics | unverified; no public data on competitors' free-tier unit economics is available |
| All our competitors have a free tier, so we need one | convention | Explicitly challenge before use. Ask whether the convention holds in this context or merely carries industry inertia. Without a named GT about competitor conversion economics, competitor behavior cannot anchor a derivation chain. | Discard — analogy-as-evidence; competitor adoption is not evidence of viability for this product/ICP/stage | Analogy-as-evidence move. Competitor adoption of a pricing model is not evidence that the same model is economically viable for this product in this ICP segment at this ARR stage. Discard as a stand-alone justification. |
| Adding a free tier has no opportunity cost | untested belief | Verify. Free tiers require engineering capacity (feature gating, infrastructure separation), support resources, and pricing-page complexity. | Discard — false; feature-gating engineering, support load and pricing-surface overhead are real documented costs | False. Engineering bandwidth to build and maintain feature gating, incremental support load for non-paying users, and deal-desk overhead from a more complex pricing surface are documented operational costs. |
| The current ICP (B2B teams, ~$10K/year contracts) responds to free-tier self-service | untested belief | Verify. B2B enterprise buyers are often procurement-driven, not self-serve. The assumption that free tiers attract ICP-aligned users (rather than non-ICP individual users) has not been tested. | Challenge — $10K/year contract implies procurement-driven buying, not self-serve sign-up | unverified; the product's $10K/year average contract suggests a buying process driven by champions and procurement, not individual self-sign-up |
| Free-tier acquisition cost is lower than current outbound acquisition cost | untested belief | Verify against actual cost data. Free tiers carry infrastructure, support, and conversion costs that may exceed the CAC savings from reduced outbound. | Challenge — no blended cost-per-acquisition comparison calculated | unverified; no blended cost-per-acquisition comparison has been calculated |
| A free tier will not cannibalise existing paid accounts or renewals | untested belief | Verify, or flag as unverified. All current ARR comes from teams paying about $10K/year; some of them could live on a free tier of up to 5 users, or use it as leverage to downgrade or negotiate at renewal. Challenge whether the free tier leaves the paid base intact. | Challenge — no data on how many existing accounts fit the free-tier limits or would use it at renewal | unverified; flagged — the pilot must exclude existing customer domains and prospects in active deals so it cannot cannibalise the paid base, and the residual risk is recorded in the trade-offs |

---

## 3. Ground Truths

- **GT-1** Current ARR is $2.4M from 240 paying teams at approximately $10,000 per team per year. — source: internal financial report (company's own ARR dashboard)
- **GT-2** The product's current acquisition model is primarily outbound sales and referrals; no self-serve inbound channel exists. — source: known channel mix (sales team records)
- **GT-3** Free-tier infrastructure and support must be budgeted separately from the paid-tier cost structure; they cannot be absorbed as zero marginal cost into the current operating model. — source: accounting principle; confirmed by finance team (infrastructure and support costs scale with active users, not paying users)
- **GT-4?** The free-to-paid conversion rate for this product in this ICP segment is unknown and has not been measured; no historical pilot or freemium experiment has been run. — source: verified gap (product and sales teams confirm no conversion data exists)

```text
?-marked: GT-4? (1 of 4)
Read-at-source: GT-1 — internal financial report (company's own ARR dashboard)
Read-at-source: GT-2 — known channel mix (sales team records)
Read-at-source: GT-3 — accounting principle, confirmed by the finance team
```

---

## 4. Derivation Chains

### Conclusion C1: The competitor-parity argument cannot justify adding a free tier

GT-3 (free-tier costs are real and must be separately budgeted) + GT-4? (conversion rate unknown and unverified)
→ Any projection of free-tier profitability or payback period requires a conversion rate assumption, and that assumption cannot be filled from competitor behavior without knowing competitors' cost structure and ICP overlap
→ The competitor-parity argument ("they have a free tier, so we need one") is an analogy-as-evidence move that collapses without a named GT about competitor conversion economics — it cannot anchor a derivation chain

**Pre-check:** head GT-3, GT-4? · ?-marked: GT-4? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — the chain's head cites GT-4?, an unverified ground truth, so under the D-07 rule (a chain citing a `GT-N?` on its head ends MEDIUM or LOW, never HIGH) it cannot be rated HIGH. The structural claim this chain reaches — that the competitor-parity argument cannot anchor a derivation chain — does not itself depend on the conversion rate's *value*, but the chain as written consumes GT-4? and is banded accordingly. This would rise once the time-boxed pilot C2 recommends produces the missing conversion data.

---

### Conclusion C2: The free-tier decision is empirical, not a convention to follow; a time-boxed pilot is the minimum required action before any adoption decision

GT-1 (240 teams at $10K/year average contract; outbound acquisition model) + GT-4? (conversion rate unknown and unverified)
→ At $10K/year average contract, whether a conversion rate of 1–2% on a free-tier cohort justifies the investment depends on the per-free-user cost, which has not been measured; at near-zero conversion the free tier generates support and infrastructure cost with no revenue offset — the outcome is highly sensitive to a variable that has never been measured for this product
→ Deciding to add or reject a free tier without conversion data is a decision under ignorance, not a decision under uncertainty; the minimum responsible action is to run a time-boxed pilot designed to generate the missing data before committing to a permanent pricing change

**Pre-check:** head GT-1, GT-4? · ?-marked: GT-4? · lowest cited: none · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — GT-4? is unverified, and this chain's head cites it directly, so per the D-07 rule the chain is capped below HIGH regardless of how strong the reasoning built on top of it is. The recommendation to run a time-boxed pilot is itself the mechanism that would resolve GT-4?'s open status and let this chain be re-rated once the pilot's data lands.

---

### Conclusion C3: The pilot threshold for adoption must be pre-specified before the pilot begins, not inferred from results afterward

GT-2 (outbound-led acquisition; no existing self-serve channel) + GT-3 (free-tier costs are real and separately budgeted)
→ The break-even conversion rate has the form (blended monthly cost per free user × 12) / (average annual contract value per converting account): both sides must be stated on the same annual basis — dividing a monthly cost directly by an annual contract value, as an earlier form of this analysis did, understates the required threshold by a factor of 12. GT-1 supplies the average annual contract value (~$10K/year) for the denominator, but no named ground truth supplies the blended monthly cost per free user for the numerator — GT-3 establishes only that this cost is real and must be separately budgeted, not its magnitude. A second, separate gap: the numerator is a cost per free USER while the denominator is a contract value per converting ACCOUNT, so the formula is not dimensionally complete until the average number of free users per converting account is also named. The threshold is therefore not yet calculable from the named ground truths; it requires two additional measured inputs — the blended monthly cost per free user, and the average free-users-per-converting-account ratio — that the pilot itself must produce
→ Pre-specifying the threshold formula before the pilot — and committing to compute the actual break-even number as soon as the pilot yields the per-free-user cost — gives the pilot a falsifiable success criterion and prevents post-hoc rationalization of a result that falls below the economic break-even

**Pre-check:** head GT-2, GT-3 · ?-marked: none · lowest cited: none · Inputs ceiling: HIGH
**Confidence:** HIGH

---

## 5. Abandoned Reasoning

### Dead End: Competitors have free tiers, therefore we need one

**What was tried:** Use the observation that all major competitors offer a free tier as direct evidence that this product must add one to remain competitive. The reasoning chain was: "industry-wide adoption of free tiers indicates it is a necessary competitive feature; we lack it; therefore we are at a competitive disadvantage."

**Why abandoned:** This is an analogy-as-evidence move. The Phase 4 instruction not to use analogies as direct evidence (SKILL.md, Phase 4 Operation) requires any reference to how others solved a similar problem to be grounded in a verified ground truth about their situation. The competitors' free-tier economics — their conversion rates, their ICP fit, their cost structure, and whether their free tiers are net-positive for growth — are not observable without published data. Without a named GT anchoring those facts, competitor behavior is an untested belief elevated to the role of direct evidence, which the methodology does not permit. The assumption "all our competitors have a free tier, so we need one" was classified in Phase 2 as a convention with Verdict: Discard precisely because it commits this error. A derivation chain built on it collapses the moment the analogy is probed: competitors may be at a different ARR stage, serve a different ICP sub-segment, or run a free tier that is loss-leading with a known payback horizon — none of which is established as a GT for this analysis.

**What it ruled out:** Competitor parity as a sufficient justification for restructuring the pricing model. This dead end establishes that the free-tier question must be evaluated on this product's own economics — GT-1, GT-2, GT-3, and the gap in GT-4? — not by reference to what others have chosen to do.

---

## 6. Conclusion

**Recommended approach:** (chains C2 and C3) Run a time-boxed 90-day pilot with a limited cohort of free-tier users (up to 5 users, limited projects) to generate the conversion data currently absent in GT-4?. Exclude existing customer domains and prospects in active deals from the pilot cohort, so the pilot cannot cannibalise paid accounts or renewals. Before the pilot launches, pre-specify the break-even threshold *formula* — annualised blended monthly cost per free user (× 12) divided by average annual contract value per converting account gives the minimum conversion needed to cover costs; dividing a monthly cost directly by an annual contract value understates the threshold by a factor of 12, so both sides must be annualised. GT-1 supplies the average annual contract value, but the blended monthly cost per free user is not supplied by any named ground truth (GT-3 establishes only that this cost is real); a second gap is that the numerator is per free user while the denominator is per converting account, so the average number of free users per converting account is a second required input. Both figures are required inputs the pilot must measure. Commit in advance to compute the actual threshold number as soon as that per-free-user cost is known. If the pilot clears the threshold, adopt the free tier with full cost budgeting per GT-3. If it does not, reject the free tier and document the result so the question does not re-open without new evidence.

**Key insight:** (chain C1) "Competitors do it" is not a valid reason to restructure a B2B pricing model at $2.4M ARR. The free-tier question is an empirical question about this product's conversion economics, not a convention the product team is obligated to follow. An outbound-led SaaS product with $10K/year average contracts and no existing self-serve channel is structurally different from the consumer tools and developer utilities where free-tier models are commonly used. The methodology forced this distinction by requiring competitor behavior to be grounded in a named GT about competitor economics — and no such GT exists or can be constructed from available data.

**Trade-offs acknowledged:** (chains C2 and C3) The pilot has real costs that must be budgeted before approval: engineering time to build feature gating and usage limits, infrastructure for non-paying users, and support overhead during the 90-day window. The pilot produces conversion data only for the cohort it runs on; if that cohort is not representative of the broader ICP, the data may not generalize to a full launch. There is also a pricing-page complexity cost during and after the pilot regardless of outcome. Excluding existing customer domains removes the pilot's own cannibalisation risk but not the residual one: if a free tier is adopted, some existing paid accounts could still downgrade to it or use it to negotiate at renewal, and the pilot is designed to leave that effect unmeasured.

**Pre-check:** head C1 (MEDIUM), C2 (MEDIUM), C3 (HIGH) · ?-marked: none · lowest cited: MEDIUM · Inputs ceiling: MEDIUM
**Confidence:** MEDIUM — the Recommended approach above explicitly cites "(chains C2 and C3)"; C2 is capped at MEDIUM under the D-07 rule because its head cites GT-4?, an unverified ground truth, and this section's own confidence inherits that cap rather than averaging it away. C3 itself remains HIGH and is unaffected by GT-4?, but the section-level rating is bound by the lower of the chains it names. This would rise once the pilot resolves GT-4?'s open status.

---

## Appendix — process output

## Structured summary (process output)

```json
{
  "schema_version": 1,
  "run_mode": null,
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
      "type": "untested belief",
      "verdict": "Challenge"
    },
    {
      "id": "A-4",
      "type": "convention",
      "verdict": "Discard"
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
      "read_at_source": false
    }
  ],
  "chains": [
    {
      "id": "C1",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-3",
        "GT-4?"
      ]
    },
    {
      "id": "C2",
      "confidence": "MEDIUM",
      "rests_on": [
        "GT-1",
        "GT-4?"
      ]
    },
    {
      "id": "C3",
      "confidence": "HIGH",
      "rests_on": [
        "GT-2",
        "GT-3"
      ]
    }
  ],
  "dead_ends": [
    "Competitors have free tiers, therefore we need one"
  ],
  "techniques": null,
  "gate": null,
  "re_entry": null,
  "conclusion": {
    "recommendation": "(chains C2 and C3) Run a time-boxed 90-day pilot with a limited cohort of free-tier users (up to 5 users, limited projects) to generate the conversion data currently absent in GT-4?. Exclude existing customer domains and prospects in active deals from the pilot cohort, so the pilot cannot cannibalise paid accounts or renewals. Before the pilot launches, pre-specify the break-even threshold *formula* — annualised blended monthly cost per free user (× 12) divided by average annual contract value per converting account gives the minimum conversion needed to cover costs; dividing a monthly cost directly by an annual contract value understates the threshold by a factor of 12, so both sides must be annualised. GT-1 supplies the average annual contract value, but the blended monthly cost per free user is not supplied by any named ground truth (GT-3 establishes only that this cost is real); a second gap is that the numerator is per free user while the denominator is per converting account, so the average number of free users per converting account is a second required input. Both figures are required inputs the pilot must measure. Commit in advance to compute the actual threshold number as soon as that per-free-user cost is known. If the pilot clears the threshold, adopt the free tier with full cost budgeting per GT-3. If it does not, reject the free tier and document the result so the question does not re-open without new evidence.",
    "confidence": "MEDIUM",
    "rests_on": [
      "C1",
      "C2",
      "C3"
    ]
  }
}
```
