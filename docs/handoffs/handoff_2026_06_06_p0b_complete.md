# Helios Handoff — 2026-06-06 P0-B Complete

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

本 session 完成 P0-B v0.1.1 cell adequacy audit script 實作與 production run。

| Artifact | 狀態 |
|---|---|
| `scripts/audit_r8_phase1_cell_adequacy.py` v0.1.0 | COMMITTED |
| `data/_storage/r8_phase1_cell_adequacy/v0.1.1/` (4 parquets + manifest) | PRODUCTION RUN COMPLETE |

---

## Commit 紀錄

```
feat(r8-phase1): emit P0-B v0.1.1 cell adequacy audit artifacts

Implements r8_phase1_cell_adequacy_spec.md v0.1.1 per
ADR-R8P1-001 v0.1.0 + ADR-R8P1-002 v0.1.0.

Production run 2026-06-06:
  r8_events=7669, treatment_1=5330, baseline_1=63363
  All invariants passed, reproduced within-process.

The P0-B audit panel is intentionally narrower than the standalone
R8 event-builder panel because it requires simultaneous coverage in
listed_market_daily_price_adj, bullish_features, and market_regime.
Therefore downstream A-1/A-2/A-3 must use the emitted P0-B treatment
and baseline universe counts, not the handoff-cited 8012 raw event count.

P0-B v0.1.1: LOCK IMPLEMENTED
Production artifacts: PASS
A-1/A-2/A-3 prerequisite: SATISFIED
Known advisory: r8_event_manifest path missing, non-blocking under AAC-4
```

---

## Production Schema（本 session 首次驗證）

下 session 不需再跑 DESCRIBE，直接使用：

### Source tables / view

| Table / View | PK | 用途 |
|---|---|---|
| `listed_market_daily_price_adj` | `stock_id, date` | `adj_open`, `adj_close`, `raw_close` |
| `bullish_features` | `stock_id, date` | `beta_adj_rs_20d`, `dist_above_ma20_atr`, `computed_at` |
| `market_regime` | `date` | `regime` (values: `bear/bull/crisis/neutral`) |

### Derived quantities（已驗證來源）

| 量 | 公式 | 來源 |
|---|---|---|
| `r8_flag` | `adj_close/prev_adj_close − 1 >= 0.05 AND adj_close > adj_open AND prev_adj_close > 0` | `r8_event_builder.py` line 85–95 |
| `near_limit_up` | `adj_close/prev_adj_close − 1 >= 0.095` | line 88 |
| `RS_T3` | `beta_adj_rs_20d > QUANTILE_CONT(beta_adj_rs_20d, 2/3) OVER (PARTITION BY date)` | line 57 |
| `regime[d−1]` | `LAG(market_regime.regime) OVER (ORDER BY date)` | ADR-R8P1-002 D4 |

### Regime labels（verbatim）

```python
['bear', 'bull', 'crisis', 'neutral']
```

---

## P0-B Production Run 結果（A-1/A-2/A-3 的直接前提）

### Panel size

| Universe | Count | 說明 |
|---|---|---|
| `r8_events` | 7,669 | Handoff 引用 8,012 的差異見下注 |
| `treatment_1` (R8 ∩ RS_T3) | 5,330 | A-3 treatment |
| `baseline_1` | 63,363 | A-1 / A-3 baseline |
| `baseline_2` (pullback filtered) | 8,846 | A-2 baseline |
| `excluded_null_near_limit_up` | 0 | 全部有 prev_adj_close |
| `dropped_no_baseline_1_dates` | 0 | D_R8 每個日期都有 baseline |

**注：** 7,669 vs 8,012 差異原因：P0-B panel 要求 `listed_market_daily_price_adj` ∩ `bullish_features` ∩ `market_regime` 三表同時覆蓋。A-1/A-2/A-3 必須以 P0-B 的 5,330 / 63,363 / 8,846 為基準，不得引用 8,012。

### D-2A treatment-side 分類

| regime | near_limit_up | n_events | n_unique_dates | classification |
|---|---|---|---|---|
| bear | 0 | 495 | 174 | **PASS** |
| bear | 1 | 150 | 96 | DIRECTIONAL_ONLY |
| bull | 0 | 2,279 | 615 | **PASS** |
| bull | 1 | 1,228 | 457 | **PASS** |
| crisis | 0 | 393 | 61 | DIRECTIONAL_ONLY |
| crisis | 1 | 264 | 54 | DIRECTIONAL_ONLY |
| neutral | 0 | 403 | 126 | **PASS** |
| neutral | 1 | 118 | 68 | DIRECTIONAL_ONLY |

### D-2B Baseline_1 baseline-side 分類

| regime | near_limit_up | n_observations | n_unique_dates | classification |
|---|---|---|---|---|
| bear | 0 | 12,166 | 203 | **PASS** |
| bear | 1 | 6 | 6 | **INSUFFICIENT** |
| bull | 0 | 39,147 | 656 | **PASS** |
| bull | 1 | 82 | 64 | DIRECTIONAL_ONLY |
| crisis | 0 | 3,748 | 67 | DIRECTIONAL_ONLY |
| crisis | 1 | 56 | 16 | **INSUFFICIENT** |
| neutral | 0 | 8,156 | 142 | **PASS** |
| neutral | 1 | 2 | 2 | **INSUFFICIENT** |

### Joint adequacy（weaker-of-two，由 A-3 downstream 計算）

| cell | D-2A | D-2B B1 | Joint |
|---|---|---|---|
| bull, nlu=0 | PASS | PASS | **PASS** |
| bear, nlu=0 | PASS | PASS | **PASS** |
| neutral, nlu=0 | PASS | PASS | **PASS** |
| bull, nlu=1 | PASS | DIRECTIONAL_ONLY | **DIRECTIONAL_ONLY** |
| bear, nlu=1 | DIRECTIONAL_ONLY | INSUFFICIENT | **INSUFFICIENT** |
| crisis, nlu=0 | DIRECTIONAL_ONLY | DIRECTIONAL_ONLY | **DIRECTIONAL_ONLY** |
| crisis, nlu=1 | DIRECTIONAL_ONLY | INSUFFICIENT | **INSUFFICIENT** |
| neutral, nlu=1 | DIRECTIONAL_ONLY | INSUFFICIENT | **INSUFFICIENT** |

**A-3 full-inference cells（PASS × PASS）：bull/bear/neutral nlu=0 — 三個 cell。**
所有 nlu=1 cell 和 crisis regime 均受 DIRECTIONAL_ONLY 或 INSUFFICIENT 約束，推斷結論需附 caveat。

---

## Output 路徑

```
~/projects/helios/data/_storage/r8_phase1_cell_adequacy/v0.1.1/
├── d1_r8_x_rs_tertile.parquet
├── d2_global_adequacy.parquet
├── d2a_a3_support.parquet
├── d2b_baseline_adequacy.parquet
└── manifest.json
```

Manifest 關鍵欄位：
- `audit_spec_version: "v0.1.1"`
- `adr_001_version: "v0.1.0"`, `adr_002_version: "v0.1.0"`
- `panel_snapshot_hash`: DuckDB file SHA-256（記錄於 manifest）
- `regime_labels: ["bear", "bull", "crisis", "neutral"]`
- `resolved_columns.rs_metric: "beta_adj_rs_20d"`
- `reproducibility.scope: "within_process_only"`

---

## Dependency Graph 更新

```
r8_phase1_lifecycle_spec.md v0.1.2
                 │
        ┌────────┴────────┐
        ▼                 ▼
ADR-R8P1-001 v0.1.0   ADR-R8P1-002 v0.1.0
        └────────┬────────┘
                 ▼
    r8_phase1_cell_adequacy_spec.md v0.1.1
                 │
                 ▼
    scripts/audit_r8_phase1_cell_adequacy.py  ← COMMITTED
                 │
                 ▼
    data/_storage/r8_phase1_cell_adequacy/v0.1.1/  ← PRODUCED
                 │
                 ▼
    A-3 inferential analysis  ← NEXT TASK
    (uses D-2A + D-2B + ADR-R8P1-001 bootstrap)
```

---

## Next Session First Task

```
A-3: R8 within RS_T3 vs RS_T3 unconditional
     = forward return comparison of Treatment_1 vs Baseline_1
     using ADR-R8P1-001 block-bootstrap inference

前置條件：
  ✅ ADR-R8P1-001 v0.1.0 (bootstrap method)
  ✅ ADR-R8P1-002 v0.1.0 (universe definitions)
  ✅ P0-B D-2A + D-2B (joint adequacy classification)
  ✅ Production panel snapshot (helios.duckdb)
```

開始前注意：
1. A-3 計算的是 **difference statistic**（Treatment_1 mean return − Baseline_1 mean return），需 ADR-R8P1-001 D5 的 **joint resample**（同一 date sample 同時套用兩側）
2. **Joint adequacy**：每個 cell 取 D-2A 與 D-2B 的 weaker-of-two（此 script 不 persist；由 A-3 output 負責計算並記錄）
3. **Horizons**：per `r8_phase1_lifecycle_spec.md`，以 trading days 計（1, 5, 10, 20td）
4. **Forward return formula**：`adj_close[T+h] / adj_open[T+1] − 1`（per lifecycle spec v0.1.2 lock）
5. **PROVISIONAL label** 不解除（AC-6：IF-2, IF-3 仍 OPEN）
6. `regime_stratified: true`，stratified within regime，不是 pooled-then-stratify

---

## Backlog 現狀

### 本 session 新增

| ID | 描述 | 優先度 |
|---|---|---|
| BACKLOG-P0B-P2-1 | `market_regime` 日期連續性自動檢查（`audit_r8_phase1_cell_adequacy.py` 加 max-gap guard） | P2 |
| BACKLOG-P0B-P2-2 | r8_event_builder manifest threshold fingerprint 比對（需上游配合） | P2 |
| BACKLOG-P0B-001 | Reconcile handoff §Manifest Required Fields vs P0-B AAC-4（`r8_event_manifest_hash` 是否升為 v0.1.2 必填） | P2 |

### 沿用（2026-06-06 早盤 handoff）

- P1-DATA IF-2 (empty `stock_info`) — OPEN
- P1-DATA IF-3 (empty `corporate_actions`, DQ-CA-001) — OPEN
- P1-DATA-FOLLOWUP: retire/rewrite `scripts/ingest_security_lifecycle.py` — OPEN
- TWSE Holiday Calendar (P1) — OPEN
- P1-OBS: Intraday Monitor Self-Alert — OPEN
- P2-OBS: Healthcheck Single Run Gap — OPEN
- P3-OPS: Session Write Lock Policy — OPEN
- BACKLOG-IF1-GUARD: repo-wide pytest guard for no-direct-daily_price_adj outside allowlist — OPEN

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

所有 Phase 1 findings 仍為 **PROVISIONAL**，per `r8_phase1_lifecycle_spec.md` AC-6。
IF-2, IF-3 未 closed → AC-6 unconditional binding。
P0-B completion 不解除此 label。

---

*End of handoff_2026_06_06_p0b_complete.md*
