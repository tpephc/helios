# Helios Handoff — 2026-06-07 R8 Phase 2B Closeout

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：

1. Phase 1 findings promotion（PROVISIONAL → CONFIRMED）
2. Phase 2 Roadmap v0.3.0 LOCKED
3. Phase 2A SPEC v0.3.0 LOCKED + runner v0.1.3 + artifacts + validation report
4. Phase 2B SPEC v0.1.2 LOCKED + runner v0.1.2 + artifacts + feasibility memo

---

## 今日 Commits

```
792dceb  docs(research): add Phase 2B feasibility memo v1.0.0
2d9f9c5  feat(research): implement Phase 2B execution bridge v0.1.2
e7da03d  docs(research): add Phase 2B execution bridge SPEC v0.1.1
b6917e9  docs(research): add Phase 2 roadmap v0.3.0 and Phase 2A SPEC v0.3.0
539cb41  docs(research): promote Phase 1 findings PROVISIONAL → CONFIRMED
a1a3959  docs(research): add Phase 2A validation report v1.0.0
a04cbc9  feat(research): implement Phase 2A stability runner v0.1.3
```

---

## 治理狀態

```
P1 backlog:           EMPTY
Phase 1:              CLOSED / CONFIRMED / ARCHIVED
Phase 2A:             CLOSED / STABLE
Phase 2B:             CLOSED / FEASIBLE
Research blockers:    0
Data blockers:        0
```

---

## R8 研究鏈結論

| Phase | 研究問題 | 結論 |
|---|---|---|
| Phase 1 | Does the R8 bull-regime uplift exist? | **CONFIRMED** (+1.35% / +2.10% at 10td/20td) |
| Phase 2A | Is the uplift temporally stable? | **STABLE** (27/27 rolling windows positive; G1–G4 PASS) |
| Phase 2B | Does execution cost destroy the uplift? | **FEASIBLE** (12/12 scenario×slippage combinations net positive) |

核心 Phase 2B 數字：

| Scenario | S1 Net | S3 Net |
|---|---|---|
| Full Sample | +1.64% | +1.36% |
| Low-Uplift (Seg 2+3) | +0.82% | +0.55% |
| High-Uplift (Seg 1+4) | +2.51% | +2.21% |

**Key Phase 2B findings:**

1. Commission（Taiwan 交易稅 0.585% round-trip）= 75% of total cost drag at S1；slippage 只佔 25%
2. Overflow sensitivity < 5 bps（First-10 ≈ Random-10）；cluster capacity 非 binding constraint
3. Mean deployed NAV = **33.4%**（10% single-position cap binding on 303/306 Low-Uplift dates）
4. FEASIBLE verdict 是在平均只部署 33% NAV 的條件下成立

---

## Phase 2A Key Numbers（供 Phase 3 參考）

| Metric | Value |
|---|---|
| Full-sample Δ_A3 20td | +1.92% |
| Rolling windows positive | 27/27 (fraction 1.00) |
| Rolling window median | +1.12% |
| G5 top-2 concentration | 89.9% (Seg 1 + 4) |
| Top-1 removal CI 20td | [+0.74%, +2.96%] |
| Collective removal (top-5) | +1.55% |

---

## 關鍵 Artifact 路徑

```
data/_storage/r8_phase2a/v0.1.0/
    segments/p2a1_segment_results.parquet    # 4 segments, adequacy, CI
    rolling/p2a2_rolling_results.parquet     # 27 rolling windows
    influence/p2a3_removal_results.parquet   # top-5 individual + collective
    concentration/p2a4_concentration.json   # G5 top-1/2 shares
    manifest.json

data/_storage/r8_phase2b/v0.1.0/
    p2b_primary_results.parquet    # 24 rows (3 scenario × 4 slippage × 2 overflow)
    p2b_overflow_diagnostics.parquet
    p2b_verdict.json               # FEASIBLE
    p2b_primary_results.csv        # human-readable
    manifest.json
```

**Phase 3 note:** Per-date portfolio return series は Phase 2B runner の
`port_df["portfolio_gross_return"]` に存在するが artifact には保存されていない。
Phase 3 の risk metrics 計算には Phase 2B runner を再実行するか、
`simulate_portfolio()` を直接呼び出す必要がある。

---

## Phase 3 の研究課題

Phase 3 = **Risk Validation**（alpha discovery ではない）

Phase 2B が回答したのは「cost が uplift を消すか」。
Phase 3 が回答すべきは「risk-adjusted で viable か」。

| 研究課題 | 内容 | Phase 2B artifact から計算可能？ |
|---|---|---|
| Drawdown characteristics | Max drawdown, avg drawdown, recovery time | ○ (per-date series 再現可能) |
| Risk-adjusted performance | Sharpe, Calmar, Sortino | ○ |
| Correlation structure | R8 portfolio vs TAIEX, VIX, regime | △ (要 market data join) |
| Capacity at scale | Price-impact beyond fixed slippage | ✗ (新モデル必要) |
| Capital efficiency | 10% cap 緩和の影響 | △ (Appendix A の Phase 3 question) |

**Phase 3 SPEC の前置決定事項（下個 session で確認）：**

- D1: Risk metric の評価 horizon（per-date? monthly? annualised?）
- D2: Benchmark 定義（TAIEX total return? RS_T3 baseline?）
- D3: Drawdown 計算の base（per-trade NAV? 累積 portfolio?）
- D4: 33% mean deployment → capital efficiency analysis を Phase 3 に含めるか

---

## 次の Session の起點

```bash
cat ~/projects/helios/research/r8_phase2b_feasibility_memo.md    # FEASIBLE verdict + Appendix A
cat ~/projects/helios/research/r8_phase2a_validation_report.md   # STABLE verdict
cat ~/projects/helios/research/r8_phase2b_spec.md               # v0.1.2 LOCKED
git log --oneline -8
```

---

## Status Invariant

```
Phase 1:     CLOSED / CONFIRMED / ARCHIVED
Phase 2A:    CLOSED / STABLE
Phase 2B:    CLOSED / FEASIBLE
Phase 3:     NOT STARTED (awaiting Phase 3 SPEC)
```

---

*End of handoff_2026_06_07_phase2b_closeout.md*
