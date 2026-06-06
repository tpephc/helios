# Helios Handoff — 2026-06-06 Phase 1 Complete

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

本 session 完成 Phase 1 全部三個 benchmark analysis（A-1 / A-2 / A-3），
產出 lifecycle spec v0.1.4 與 interim findings v0.1.0，AC-2 正式 satisfied。

| Artifact | 狀態 |
|---|---|
| `scripts/run_r8_phase1_a1.py` v0.1.0 | COMMITTED |
| `scripts/run_r8_phase1_a2.py` v0.1.0 | COMMITTED |
| `research/r8_phase1_lifecycle_spec.md` v0.1.4 | COMMITTED — LOCK APPROVED |
| `research/r8_phase1_interim_findings.md` v0.1.0 | COMMITTED — LOCK APPROVED |
| `data/_storage/r8_phase1_a1/v0.1.0/` (3 files) | PRODUCTION RUN COMPLETE — not in git |
| `data/_storage/r8_phase1_a2/v0.1.0/` (2 files) | PRODUCTION RUN COMPLETE — not in git |

---

## Commit 紀錄

```
303a531  feat(r8-phase1): add A-1 RS_T3 Hold benchmark script v0.1.0
fac85ad  feat(r8-phase1): complete A-1/A-2/A-3; lifecycle spec v0.1.4; interim findings v0.1.0
```

---

## Phase 1 最終狀態

| Analysis | Status | Artifact |
|---|---|---|
| P0-B Cell adequacy audit | COMPLETE | `data/_storage/r8_phase1_cell_adequacy/v0.1.1/` |
| A-1 RS_T3 Hold benchmark | COMPLETE | `data/_storage/r8_phase1_a1/v0.1.0/` |
| A-2 RS_T3 + Pullback benchmark | COMPLETE (descriptive only) | `data/_storage/r8_phase1_a2/v0.1.0/` |
| A-3 R8∩RS_T3 vs RS_T3 unconditional | COMPLETE | `data/_storage/r8_phase1_a3/v0.1.0/` |

| AC | Status |
|---|---|
| AC-2 | **SATISFIED** — 所有三個 benchmark 均已 measured and reported |
| AC-6 | **OPEN** — IF-2 / IF-3 未 closed；所有 findings = PROVISIONAL |

**Phase 1 implementation = COMPLETE。Phase 1 validation = NOT COMPLETE。**

---

## Key Findings（PROVISIONAL — AC-6 binding）

### Phase 1 Answer to Primary Research Question

> Does R8 provide incremental timing information within the RS_T3 universe?

| Regime | Answer | Basis |
|---|---|---|
| Bull | YES (PROVISIONAL) | A-3 Tier 1：Δ=+1.35%/+2.10% at 10td/20td，ROBUST across L={5,10,20,40} |
| Bear | INCONCLUSIVE | A-3 Tier 3：p≈0.03 但 CI 含 0；CI precedence rule → not promoted |
| Neutral | NO EVIDENCE | A-3：all CIs contain zero；p>0.05 across full grid |
| Pullback interaction | UNRESOLVED | A-2：0 PASS cells；38 max treatment dates |

### A-1 Key Results（bull, nlu=0）

| Horizon | θ_base | 95% CI (L=20) | n_eff |
|---|---|---|---|
| 10td | +1.50% | [+0.85%, +2.13%] | 105 |
| 20td | +3.03% | [+1.84%, +4.17%] | 71 |

### A-2 Structural Finding

Treatment_2（R8 ∩ RS_T3 ∩ `dist_above_ma20_atr < 0`）= 262 obs / 109 dates = 4.9% of Treatment_1。
0 PASS cells。R8 定義的 +5% intraday move 與 pullback state 在同一天幾乎不共存。
**這是 substantive finding，不是 methodological failure。**

Directional evidence（inference prohibited）：bull/nlu=0 20td Δ_A2 ≈ +2.20%；bear/nlu=0 20td Δ_A2 ≈ +5.00%。

### A-3 Tier 1 Results（bull, nlu=0）

| Horizon | δ_obs | 95% CI (L=20) | p (L=20) | n_eff |
|---|---|---|---|---|
| 10td | +1.35% | [+0.69%, +2.18%] | 0.0002 | 299 |
| 20td | +2.10% | [+0.94%, +3.45%] | 0.0008 | 258 |

Sensitivity ROBUST across L={5,10,20,40}。

### Benchmark hierarchy（bull, nlu=0, 20td）

```
A-1 θ_base     = +3.03%   RS_T3 unconditional baseline
A-3 Δ_A3       = +2.10%   R8 timing uplift（CI excludes 0）
A-3 θ_treat    ≈ +5.13%   implied treatment return
A-2 θ_base     = +3.22%   pullback-state baseline（≈ A-1，no material difference）
A-2 Δ_A2       ≈ +2.20%   directional only；inference prohibited
```

R8 = timing enhancement（41% of implied treatment return），not primary return driver。

---

## A-1 Script 設計決策記錄（下 session 不需重新討論）

| 決策 | 選擇 | 理由 |
|---|---|---|
| Estimand | θ_base only（descriptive anchor，no p-value） | A-1 的治理角色是 anchor benchmark，不是獨立 alpha test |
| Bootstrap option | Option X（純 Baseline_1 date pool，no joint resample） | A-1 不估 Δ；與 n_eff reference unit = baseline_1_date_pool 一致 |
| Bootstrap replicate mean | Observation-weighted（expand all sampled rows） | 與 ADR-R8P1-002 D6 event-level estimand 和 A-3 baseline_mean_return 一致；date-mean bootstrap 會產生 estimand mismatch |
| DIRECTIONAL_ONLY | Point estimates only；bootstrap_se / n_eff / CI = NULL | Option A：乾淨，無歧義；A-1 為 descriptive anchor，SE 無讀者場合 |
| INSUFFICIENT | Row retained；所有 estimates = NULL | Option 1B：保留 row 維持 8×4 shape；n_unique_dates<30 point estimate 不應被解讀 |
| Cross-check | A-1 theta_base_mean == A-3 baseline_mean_return（tolerance 1e-9） | 同一 panel snapshot；A-3 cross-check PASSED：20 matching cells |
| n_eff | n_dates / VIF；VIF = (bootstrap_se / naive_se)^2；naive_se 用 date-clustered SE | 保守 reference，與 A-3 n_eff 計算邏輯一致 |

---

## A-2 Script 設計決策記錄（下 session 不需重新討論）

| 決策 | 選擇 | 理由 |
|---|---|---|
| Estimand | Δ_A2 = θ_treat − θ_base（差分） | Phase 1 research question：R8 是否優於 RS pullback？ |
| Pullback filter symmetry | Interpretation β（symmetric，兩側都 filter） | ADR-R8P1-002 locked；isolate R8 selection effect within pullback state |
| Bootstrap | 不跑 | 0 PASS cells；Treatment_2 max 38 dates；成本無正當性 |
| Adequacy gate | Inline compute from Treatment_2 / Baseline_2 date counts | A-2 為 descriptive-only；不需外部 P0-B artifact |
| Sensitivity | 不產 sensitivity parquet | 無 bootstrap → sensitivity 無意義 |
| INSUFFICIENT | Row retained；all estimates NULL | 與 A-1 governance 一致；shape = 32 rows fixed |
| Manifest | `adequacy_table_sha256`（regime × nlu × dates × joint_adequacy 的 SHA-256） | 確保 0 PASS / 2 DIRECTIONAL_ONLY / 6 INSUFFICIENT 可追溯 |

---

## A-1 Production Run 關鍵數字

```
Panel: 63,363 rows, 1,068 unique dates, 204 unique stocks
Valid forward returns: 1td=63,269 / 5td=63,021 / 10td=62,744 / 20td=62,208
Output: 32 rows primary, 48 rows sensitivity
INV-1 through INV-6: PASS
A-1/A-3 cross-check: PASSED (20 matching cells, tolerance 1e-9)
```

## A-2 Production Run 關鍵數字

```
Panel: 262 treatment_2 rows (109 dates), 8,846 baseline_2 rows (956 dates)
Adequacy: 0 PASS, 2 DIRECTIONAL_ONLY, 6 INSUFFICIENT
Output: 32 rows primary
INV-1 through INV-6: PASS
adequacy_table_sha256: in manifest
```

---

## Schema 確認（本 session 中發現）

`daily_features` 沒有 `r8_flag`、`rs_tertile`、`regime` 欄位。這些全部是 query-time 計算的 CTE：

- `rs_tertile`：來自 `bullish_features.beta_adj_rs_20d` 的 within-date quantile（A-3 `_PANEL_SQL`）
- `r8_flag`：來自 `price_lagged` 的條件（adj_close/prev_adj_close ≥ 1.05 AND adj_close > adj_open）
- `regime[T-1]`：來自 `market_regime` 的 LAG window
- `dist_above_ma20_atr`：來自 `bullish_features.dist_above_ma20_atr`（per-stock-day scalar）
- `near_limit_up`：來自 `price_lagged` 的條件（adj_close/prev_adj_close ≥ 1.095）

所有 Phase 1 scripts（A-1 / A-2 / A-3）使用相同的 CTE 結構，確保 panel 定義一致。

---

## 下一個工作重心

```
P1-DATA clean-panel rerun path
```

**Blockers（binding on AC-6）：**

| ID | 描述 | 狀態 |
|---|---|---|
| IF-2 | `stock_info` 表為空 | OPEN |
| IF-3 | `corporate_actions` 表為空（DQ-CA-001） | OPEN |

IF-2 / IF-3 關閉後：
1. 確認 panel integrity（sector composition、suspension events）
2. 以 clean panel 重跑 A-1 / A-2 / A-3
3. 比對 provisional findings 是否改變
4. AC-6 closeout → findings 升格為 validated

**開始前請讀：**
```bash
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md   # v0.1.4
cat ~/projects/helios/research/r8_phase1_interim_findings.md # v0.1.0
```

---

## Backlog 現狀

### 沿用（未變動）

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

## Status Invariant

所有 Phase 1 findings 仍為 **PROVISIONAL**，per `r8_phase1_lifecycle_spec.md` v0.1.4 AC-6。
IF-2, IF-3 未 closed → AC-6 unconditional binding。
Phase 1 implementation complete 不解除此 label。

---

*End of handoff_2026_06_06_phase1_complete.md*
