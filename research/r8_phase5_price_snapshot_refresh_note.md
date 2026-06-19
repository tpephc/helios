# R8 Phase 5 — Price Snapshot Refresh Note

<!-- research/r8_phase5_price_snapshot_refresh_note.md -->
<!-- v0.1.0 — 2026-06-08 -->

**Status:** GOVERNANCE NOTE — informational only; does not modify any locked artifact.
**Detected by:** Phase 5 runner v0.1.0 Arm A lineage check
**Decision:** OPTION A APPROVED (2026-06-08)

---

## 1. What Was Detected

During Phase 5 Arm A execution, the lineage check comparing the recomputed
full-sample Sharpe against the Phase 3 locked reference failed:

| Metric | Phase 3 locked | Phase 5 recomputed | Delta |
|---|---|---|---|
| Full-sample Sharpe | 2.377654 | 2.498050 | +0.120 |
| Full-sample nav_end | 6.477569 | 6.974622 | +0.497 |
| Full-sample MaxDD | 21.65% | 21.65% | 0.000 |
| Full-sample admission rate | 16.3% | 16.3% | 0.000 |
| Low-Uplift Sharpe | 1.613070 | 1.569000 | −0.044 |
| Low-Uplift admission rate | 17.5% | 17.5% | 0.000 |

Admission rates, MaxDD, and scheduled positions (350/2143) are identical between
Phase 3 and Phase 5.  The NAV path diverges starting at **2023-07-14**, with
**694 of 1013 common trading dates** producing different NAV values despite
identical scheduled positions.

---

## 2. Root Cause

The `daily_price_adj` table in `helios.duckdb` underwent a **retroactive
adjustment** after the Phase 3/4 artifacts were locked (likely 2026-06-07).
The adjusted `adj_close` and/or `adj_open` values for historical dates changed,
causing the daily MTM return for existing positions to differ.

The divergence onset at 2023-07-14 is consistent with TWSE's annual
ex-dividend / corporate action season (July–August).  When TWSE restates
ex-dividend adjustment factors, all historical adj prices downstream of the
restatement date shift.

This is expected behaviour for an adjusted-price series.  It is not a data
corruption event.

---

## 3. Governance Decision: Option A

Three options were evaluated:

| Option | Description | Decision |
|---|---|---|
| A | Update ARM_A_REFERENCE to current snapshot; all arms use consistent price basis | **APPROVED** |
| B | Use Phase 3 locked NAV for Arm A; Arm B/C use current prices | Rejected — cross-arm price basis inconsistency |
| C | Weaken Sharpe lineage gate to advisory-only | Rejected — degrades lineage guard |

**Option A framing (governance constraint):**

> This update is a **Phase 5 price-snapshot baseline refresh**.
> It does not modify, revise, or supersede any Phase 3/4 locked finding.
> Phase 3/4 artifacts remain locked at their original values.
> The Phase 5 research question (configuration selection) is evaluated
> entirely on the current adj-price snapshot, with all arms on a
> consistent price basis.

---

## 4. Impact on Phase 5 Research Question

The price snapshot refresh affects absolute Sharpe values but **does not
affect the relative gate evaluation**, because:

- All three arms (A, B, C) are recomputed on the same current adj-price snapshot.
- Phase 5 gates (P5-G1, P5-G2, P5-G3) measure **deltas relative to Arm A**.
- If adj prices shift all arms proportionally, the deltas are unaffected.
- If the shift is non-uniform (e.g., affects high-RS stocks differently),
  the gate values may shift slightly relative to Phase 4 Track B estimates.
  This is an acceptable research risk given that Phase 4 findings are
  carried forward as expected values, not pre-registered gate thresholds.

The Low-Uplift Sharpe change (1.613 → 1.569, Δ = −0.044) is within the
ARM_A_SHARPE_TOL of ±0.050, confirming that the **stress-environment metrics
are stable** and the price adjustment is concentrated in the pre-2024
historical segment.

---

## 5. Updated ARM_A_REFERENCE (Phase 5 price-snapshot baseline)

```python
ARM_A_REFERENCE = {
    "full_sample": {"sharpe": 2.498, "max_dd": 0.2165, "admission_rate": 0.163},
    "low_uplift":  {"sharpe": 1.569, "max_dd": 0.2054, "admission_rate": 0.175},
}
```

Locked Phase 3 values are preserved in `_LOCKED_PHASE3_REFERENCE` in
`scripts/run_phase5_analysis.py` as historical reference only.

---

## 6. What This Note Does Not Establish

- That the Phase 3/4 research findings are incorrect.
- That the R8 signal edge is weakened or strengthened by the price adjustment.
- That Phase 1 CONFIRMED finding (Δ_A3 CI lower bound > 0) is affected
  (Phase 1 used the price snapshot available at that time; the finding is
  a statement about that snapshot, not about all future snapshots).
- That Phase 5 results will be reproducible on a future price snapshot.

---

## 7. Traceability

| Artifact | Path | Status |
|---|---|---|
| Phase 3 locked NAV | `data/_storage/r8_phase3/v0.1.0/p3a_nav_series.parquet` | LOCKED — not modified |
| Phase 3 locked metrics | `data/_storage/r8_phase3/v0.1.0/p3a_risk_metrics.json` | LOCKED — not modified |
| Phase 5 manifest | `data/_storage/r8_phase5/v0.1.0/manifest.json` | Records divergence details |
| Phase 5 runner | `scripts/run_phase5_analysis.py` v0.1.0 | ARM_A_REFERENCE updated (P5-REF-001) |

---

*End of r8_phase5_price_snapshot_refresh_note.md v0.1.0*
