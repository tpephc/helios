# Helios Handoff — 2026-06-06 A-3 Complete

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
  - PEP 8 / PEP 257 / type hints on public functions
  - 變數名、函式名、class 名、log 訊息、docstring、註解：英文
- **檔案 header 慣例：**
  - scripts: `#!/usr/bin/env python3` + `# scripts/filename.py` + `"""Title — vX.Y.Z. Brief.`
  - modules: `# path/to/file.py` + docstring
  - 檔名不含版本號
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成 A-3 inferential analysis（R8 within RS_T3 vs RS_T3 unconditional）
及 lifecycle spec v0.1.3 更新。

| Artifact | 狀態 |
|---|---|
| `scripts/run_r8_phase1_a3.py` v0.1.0 | COMMITTED |
| `research/r8_phase1_lifecycle_spec.md` v0.1.3 | COMMITTED — LOCK APPROVED |
| `data/_storage/r8_phase1_a3/v0.1.0/` (3 files) | PRODUCTION RUN COMPLETE — not in git (`.gitignore`) |

---

## Commit 紀錄

```
d302241  feat(r8-phase1): complete A-3 inferential analysis + lifecycle spec v0.1.3
```

2 files changed, 1178 insertions(+), 4 deletions(-)

**注：** `data/_storage/` は `.gitignore` 範圍内。Parquet + manifest は server 上のみ保存。
Provenance は manifest の hash chain で追跡する。

---

## A-3 Production Artifacts（server only）

```
~/projects/helios/data/_storage/r8_phase1_a3/v0.1.0/
├── a3_primary_inference.parquet      (32 rows: 8 cells × 4 horizons)
├── a3_sensitivity_block_length.parquet  (48 rows: 3 PASS cells × 4 horizons × 4 L)
└── manifest.json
```

### Manifest 關鍵欄位

```json
{
  "bootstrap_method": "stationary",
  "resampling_unit": "trading_date",
  "joint_resample": true,
  "block_length_primary": 20,
  "block_length_sensitivity": [5, 10, 20, 40],
  "replications": 5000,
  "ci_method": "percentile",
  "p_value_method": "null_shifted_two_tailed",
  "n_eff_reference_unit": "treatment_date_pool",
  "seed": 42,
  "regime_stratified": true,
  "adr_version": "ADR-R8P1-001 v0.1.0",
  "p0b_panel_snapshot_hash": "b82897a0f45be66a067e2557715fbe38489b938a3a4fd3485cc9285e7b6f3235",
  "findings_status": "PROVISIONAL",
  "full_inference_cells": ["bear_nlu0", "bull_nlu0", "neutral_nlu0"]
}
```

---

## A-3 Key Findings（PROVISIONAL — AC-6 binding）

所有 findings = PROVISIONAL。IF-2（empty `stock_info`）、IF-3（empty `corporate_actions`）
仍 OPEN。未完成 P1-DATA clean-panel re-run 前，任何 findings 不得作為 validated 結論引用。

### Full inference cells

| Cell | Joint adequacy | Bootstrap runs |
|---|---|---|
| bull, nlu=0 | PASS | ✓ L={5,10,20,40} × 4 horizons |
| bear, nlu=0 | PASS | ✓ L={5,10,20,40} × 4 horizons |
| neutral, nlu=0 | PASS | ✓ L={5,10,20,40} × 4 horizons |

### Tier 1 — Robust findings

**Bull regime, nlu=0：**

| Horizon | δ_obs | 95% CI (L=20) | CI lower bound range across L | p (L=20) | n_eff |
|---|---|---|---|---|---|
| 10td | +1.35% | [+0.69%, +2.18%] | +0.61% to +0.72% | 0.0002 | 299 |
| 20td | +2.10% | [+0.94%, +3.45%] | +0.77% to +1.11% | 0.0008 | 258 |

Sensitivity verdict：**ROBUST**。四個 block length L={5,10,20,40} CI 全部不含 0，p ≤ 0.004。
不是 L=20 artifact。

Pattern：δ 隨 horizon 單調遞增（1td: −0.03% → 5td: +0.38% → 10td: +1.35% → 20td: +2.10%）
符合 trend-continuation 的經濟直覺，但 causal interpretation 超出 Phase 1 範圍。

**Interpretation boundary（lifecycle spec v0.1.3 verbatim）：**
> This finding is conditional on the RS_T3 proxy defined in LA-4. It should
> not be interpreted as evidence that R8 provides incremental information
> outside the high-RS universe.

### Tier 2 — Consistent direction, insufficient evidence

**Bull regime, nlu=0, 5td：**
δ_obs = +0.38%。四個 L 均正向，p 範圍 0.046–0.085。
不滿足 α=0.05 across sensitivity grid。
結論：consistent positive direction；insufficient evidence for promotion。

### Tier 3 — Suggestive, not promoted

**Bear regime, nlu=0, 20td：**
δ_obs = +1.46%，p 範圍 0.025–0.034（名義上顯著），但 percentile CI 在四個 L 均含 0
（lower bound −0.19% to −0.11%）。ADR 鎖定 CI method = percentile，CI 優先於 p-value。
n_eff non-monotone（5td:184 → 10td:80 → 20td:141），暗示少數 influential date clusters。
結論：suggestive positive trend；not promoted。

### No-signal cells

| Cell | 結論 |
|---|---|
| Bear, nlu=0, 1–10td | No signal（p > 0.23 across all L） |
| Neutral, nlu=0, all horizons | No signal；n_eff 47–60 at 20td（structural finding per ADR D7） |

### Adequacy-restricted cells（not in findings）

bull/nlu=1（DIRECTIONAL_ONLY）、crisis/nlu=0（DIRECTIONAL_ONLY）、
bear/nlu=1, crisis/nlu=1, neutral/nlu=1（INSUFFICIENT）。
Point estimates 存在於 artifact，不升級為 findings。

---

## Lifecycle Spec 狀態

`research/r8_phase1_lifecycle_spec.md` v0.1.3 — **LOCK APPROVED**

變更內容：新增 Phase 1 Findings section + Status progress table + Changelog。
原有所有 SPEC 條款（AC-1–AC-7、LA-1–LA-8、Interpretation Restrictions 等）逐字保留。
v0.1.3 不修改任何治理規則，只記錄 empirical findings。

---

## A-3 Implementation 技術決策記錄（下 session 不需重新討論）

| 決策 | 選擇 | 理由 |
|---|---|---|
| Bootstrap date pool | treatment dates only | P0-B invariant `dropped_no_baseline_1_dates=[]` 保證每個 treatment date 有 baseline；union 引入空 treatment 的 replications |
| n_eff denominator | treatment_n_dates | ADR D1 resampling unit = R8 event dates；difference statistic 的有效樣本參考 treatment side |
| p-value method | null_shifted_two_tailed | 避免 bootstrap distribution 已偏向 observed direction 時 p-value 被人為壓低 |
| CI precedence | percentile CI > p-value | ADR 鎖定 CI method = percentile；bear 20td 的 p<0.05 + CI含0 的不一致以 CI 為準 |
| Seed | 42 | 記入 manifest；同 seed bit-identical |

Script invariants：INV-1（每個 cell×horizon 恰好 1 row）、INV-2（FULL rows 無 NaN bootstrap 欄）、
INV-3（INSUFFICIENT rows delta_obs=NaN）、INV-4（FULL 只對應 PASS cells）、
INV-5（p-value ∈ [0,1]）、INV-6（n_bootstrap_used ≥ 100）、
INV-POOL-1（treatment dates 全在 date pool）、INV-POOL-2（baseline dates ⊆ treatment date pool）。

---

## Phase 1 整體進度

| Analysis | Status | Artifact path |
|---|---|---|
| P0-B Cell adequacy audit | COMPLETE | `data/_storage/r8_phase1_cell_adequacy/v0.1.1/` |
| A-3 R8∩RS_T3 vs RS_T3 unconditional | COMPLETE | `data/_storage/r8_phase1_a3/v0.1.0/` |
| **A-1 RS_T3 Hold benchmark** | **NOT STARTED** | — |
| **A-2 RS_T3 + Pullback benchmark** | **NOT STARTED** | — |

Phase 1 overall status：**IN PROGRESS**（AC-2 requires all three comparisons）

---

## Next Session First Task：A-1 RS_T3 Hold Benchmark

### 研究問題

A-3 已知：R8∩RS_T3 vs RS_T3 non-R8 的 delta。
但還不知道：RS_T3 本身的 absolute forward return 水準。
A-1 提供 context：RS_T3 Hold 的 forward return，讓我們能判斷：

```
A-3 的 +1.35% / +2.10%（treatment vs baseline）
是在一個 strong RS trend 上的小增量
還是在一個 flat baseline 上的主要 return driver？
```

這是 Phase 1 研究問題的核心脈絡。

### A-1 定義（per lifecycle spec + ADR-R8P1-002）

**Treatment：** 所有 RS_T3 stocks（包含 R8 events）在 D_R8 dates 的 T+1 open 進場。
**注意：** A-1 的 baseline 不是 Treatment_1 vs Baseline_1 的差分——它是 RS_T3 Hold 的
absolute forward return，用來了解 RS_T3 universe 在 R8 event dates 前後的 return profile。

**Locked constants（與 A-3 相同，直接沿用）：**

```python
FORWARD_RETURN_FORMULA = "adj_close[T+h] / adj_open[T+1] - 1"
HORIZONS_TD = [1, 5, 10, 20]          # trading days
REGIME_LABELS = ["bear", "bull", "crisis", "neutral"]  # verbatim from market_regime
DB_PATH = "data/_storage/helios.duckdb"
P0B_DIR = "data/_storage/r8_phase1_cell_adequacy/v0.1.1"
```

**需要確認的 ADR-R8P1-002 問題：**
- A-1 是否也用 block-bootstrap（同 ADR-R8P1-001）？
- 還是 A-1 只報 descriptive statistics（mean / median / distribution）？
- ADR-R8P1-002 對 A-1 的 inference scope 有何規定？

開始前請讀：
```bash
cat ~/projects/helios/research/adr/ADR-R8P1-002-baseline-benchmark-construction.md
```

### A-1 的 cell adequacy

A-1 用 `d2_global_adequacy.parquet`（d2 global，不是 d2a treatment-side）。
P0-B 已有，直接讀取，不需重跑。

---

## Backlog 現狀

### 本 session 新增

無新增 backlog items。

### 沿用（2026-06-06 P0-B handoff）

| ID | 描述 | 優先度 |
|---|---|---|
| P1-DATA IF-2 | empty `stock_info` | P1 — OPEN |
| P1-DATA IF-3 | empty `corporate_actions`, DQ-CA-001 | P1 — OPEN |
| P1-DATA-FOLLOWUP | retire/rewrite `scripts/ingest_security_lifecycle.py` | P1 — OPEN |
| TWSE Holiday Calendar | — | P1 — OPEN |
| P1-OBS | Intraday Monitor Self-Alert | P1 — OPEN |
| P2-OBS | Healthcheck Single Run Gap | P2 — OPEN |
| P3-OPS | Session Write Lock Policy | P3 — OPEN |
| BACKLOG-IF1-GUARD | repo-wide pytest guard: no direct `daily_price_adj` outside allowlist | P2 — OPEN |
| BACKLOG-P0B-P2-1 | `market_regime` 日期連續性自動檢查 | P2 — OPEN |
| BACKLOG-P0B-P2-2 | r8_event_builder manifest threshold fingerprint 比對 | P2 — OPEN |
| BACKLOG-P0B-001 | Reconcile `r8_event_manifest_hash` 是否升為 v0.1.2 必填 | P2 — OPEN |

### Deferred（不變）

- v0.1.17 ARCHITECTURE.md refresh
- timestamp semantics backlog #14
- Kairos Phase B bearish / TX futures directional signal
- Kairos backlog items #27 / #28 / #29
- r8_forward_returns engine 統一
- `eligible_universe.py` defensive duplication 清理
- `eligible_date_predicate()` 改名為 `panel_start_date_predicate()`

---

## Status Invariant（不變）

所有 Phase 1 findings 仍為 **PROVISIONAL**，per `r8_phase1_lifecycle_spec.md` v0.1.3 AC-6。
IF-2, IF-3 未 closed → AC-6 unconditional binding。
A-3 completion 不解除此 label。

---

*End of handoff_2026_06_06_a3_complete.md*
