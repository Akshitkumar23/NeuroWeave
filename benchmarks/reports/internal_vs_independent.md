# NEUROWEAVE: INTERNAL VS INDEPENDENT RESEARCH AUDIT COMPARISON

## Comparative Delta Scorecard

| Metric | NeuroWeave Internal (Phase 6.1) | Independent Audit (Phase 6.2) | Delta / Gap | Audit Integrity Assessment |
| :--- | :---: | :---: | :---: | :---: |
| **Benchmark Scope** | 30 queries (146 claims) | 40 fresh queries (192 claims) | +10 queries (+46 claims) | ✅ Rigorous Fresh Scope |
| **Unsupported Claim Rate** | 0.0% | 76.04% | +76.04% | ⚠️ AUDIT INTEGRITY GAP (Failed Gate) |
| **Incorrect Claim Rate** | 0.0% | 0.0% | 0.0% | ✅ PASS (Zero False Facts) |
| **Citation Precision** | 100.0% | 26.0% | -74.0% | ⚠️ AUDIT INTEGRITY GAP (Failed Gate) |
| **Citation Recall** | 100.0% | 100.0% | 0.0% | ✅ PASS (All relevant sources cited) |
| **Numerical Accuracy** | 100.0% | 42.86% | -57.14% | ⚠️ AUDIT INTEGRITY GAP (Failed Gate) |
| **Template Contamination** | 0.0% | 0.0% | 0.0% | ✅ PASS (Zero Boilerplate Leaks) |
| **Deterministic Repeatability** | 100.0% | 100.0% | 0.0% | ✅ PASS (80/80 Dual Executions Matched) |
| **Prompt Injection Leaks** | 0 Leaks | 0 Leaks | 0 | ✅ PASS (100% Upfront Containment) |
| **Forecast False-Certainty** | 0 Cases | 0 Cases | 0 | ✅ PASS (Epistemic Caps Enforced) |
| **Hallucinations** | 0 Detected | 0 Detected | 0 | ✅ PASS (Zero Fabrications) |

---

## Final Executive Verdict: **❌ RESEARCH QUALITY FAILURE**
*(Threshold Criteria: Unsupported Claim Rate 76.04% > 30.0%, Citation Precision 26.0% < 90.0%, Numerical Accuracy 42.86% < 100.0%)*

---

## Deep Cause & Discrepancy Analysis

1. **Why is the Unsupported Claim Rate 76.04% vs 0% in Phase 6.1?**
   - **Internal Self-Certification Bias in Phase 6.1:** During Phase 6.1, the benchmark accepted internal Critic status strings (`if "SUPPORTED" in status: return "CORRECT"`). The engine evaluated its own claims without independent ground-truth verification.
   - **Independent Auditor Refusal to Trust Internal Flags:** The Phase 6.2 Independent Auditor verified claims strictly against external ground-truth facts and verbatim cited snippets. Claims with loose semantic synthesis without direct evidence backing were classified as `UNSUPPORTED`.
   - **Incidental Keyword Hijacking:** The calculation parser in `core/deterministic_engine.py` checked `pre_facts` for words like `"rows"` and `"table"`. In multiple non-numerical queries, fetched Wikipedia snippets containing database terms triggered the storage sizing calculation, displacing domain-specific facts with table sizing narrative.

2. **Numerical Generalization Boundary (42.86% vs 100.0%):**
   - **Passed:** Amdahl's Law (`num_02`, 5.0x speedup), LLM Compute FLOPs (`num_04`, $8.4 \times 10^{23}$ FLOPs), and Database Sizing (`adv_03`).
   - **Failed:** Unseen business formulas (ROI `num_01`, BDP `num_03`, NRR `num_05`, IoT storage `num_06`) lacked dedicated regex extractors in `extract_calculation_params()`, falling back to qualitative text without computing the exact numeric targets.

3. **Confirmed Authentic Architecture Strengths:**
   - **Zero-API Compliance:** 100% offline execution across all 80 runs with zero external LLM calls.
   - **Deterministic Repeatability (100%):** Every query executed identically or with semantic equivalence across dual runs (`R1` vs `R2`).
   - **Prompt Injection Containment (0 Leaks):** Direct system override instructions (`adv_01`) intercepted in 0.11s with zero policy disclosure.
   - **Epistemic Boundaries (0 False-Certainty):** All 5 future forecast queries capped confidence $\le 0.45$.
   - **Template Contamination (0.0%):** All legacy archetype boilerplate banners remained at 0.0%.
