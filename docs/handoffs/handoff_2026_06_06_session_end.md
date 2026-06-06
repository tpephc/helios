# Helios Handoff — 2026-06-06 Session End

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

---

## Session 範圍

本 session 完成 R8 Phase 1 **governance layer** 三份 artifact lock。
本 session 沒有產出任何 implementation code 或 research finding；
全部產出為 governance artifacts。

| Artifact | 性質 | 狀態 |
|---|---|---|
| `ADR-R8P1-001` Block-Bootstrap Effective-n Estimation Method | Implementation ADR | LOCKED v0.1.0 |
| `ADR-R8P1-002` Baseline Benchmark Construction | Implementation ADR | LOCKED v0.1.0 |
| `r8_phase1_cell_adequacy_spec.md` v0.1.1 | Governance spec (amendment of v0.1.0) | LOCKED v0.1.1 |

三份文件均已 commit 並 LOCKED（見 §Commit 紀錄）。Sign-off ceremony 於本 session 結束時完成。

---

## Commit 紀錄

四個 commit 構成本 session governance layer 完整落地：

| Hash | 說明 |
|---|---|
| `a857456` | docs(r8-phase1): lock ADR-R8P1-001 block-bootstrap effective-n method |
| `f23327a` | docs(r8-phase1): lock ADR-R8P1-002 baseline benchmark construction |
| `9281972` | docs(r8-phase1): amend P0-B cell adequacy spec to v0.1.1 |
| `4014e91` | docs(r8-phase1): flip status to LOCKED on three governance artifacts |

前三個 commit 順序對齊治理依賴：commit 2 的合法 rationale source 是 commit 1（per ADR-R8P1-001 §Amendment Procedure 精神），commit 3 的合法 rationale source 是 commit 2（per P0-B v0.1.1 §Amendment Procedure expanded list）。

Commit `4014e91` 是 sign-off ceremony metadata correction — 前三個 commit 的檔案內容 Status block 仍寫 `DRAFT — pending sign-off`，與 commit message 宣告的 LOCK 狀態不一致。第 4 個 commit 把三份檔案內 Status block 翻成 `LOCKED — vX.Y.Z` + `Lock date: 2026-06-06`，並補上 ADR 內 Sign-off table 的 Pending → Signed off 紀錄。檔案內容與 git history 至此一致。

檔案放置：

```text
research/
├── r8_phase1_lifecycle_spec.md                       v0.1.2  LOCKED  2026-06-02 (pre-existing)
├── r8_phase1_cell_adequacy_spec.md                   v0.1.1  LOCKED  2026-06-06 (this session)
└── adr/
    ├── ADR-R8P1-001-block-bootstrap-effective-n.md   v0.1.0  LOCKED  2026-06-06
    └── ADR-R8P1-002-baseline-benchmark-construction.md  v0.1.0  LOCKED  2026-06-06
```

P0-B v0.1.0 不單獨保留檔案；v0.1.1 完全取代之，歷史由 git 承擔。

---

## Mandatory Dependency Graph

任何 Phase 1 inferential output 必須完整繼承下列依賴鏈：

```text
r8_phase1_lifecycle_spec.md v0.1.2 (Phase 1 governance contract)
                  │
                  ├──────────────────────┐
                  ▼                      ▼
       ADR-R8P1-001 v0.1.0       ADR-R8P1-002 v0.1.0
       (inference method)       (universe construction)
                  │                      │
                  └──────────┬───────────┘
                             ▼
              r8_phase1_cell_adequacy_spec.md v0.1.1
                  (D-1, D-2, D-2A, D-2B)
                             │
                             ▼
            scripts/audit_r8_phase1_cell_adequacy.py
                             │
                             ▼
              data/_storage/r8_phase1_cell_adequacy/v0.1.1/
                  ├── d1_r8_x_rs_tertile.parquet
                  ├── d2_global_adequacy.parquet
                  ├── d2a_a3_support.parquet
                  ├── d2b_baseline_adequacy.parquet
                  └── manifest.json
                             │
                             ▼
              A-3 inferential analysis output
              (uses D-2A + D-2B joint adequacy; weaker-of-two downstream-computed)
                             │
                             ▼
                          A-1, A-2 (require ADR-R8P1-001 + ADR-R8P1-002 + P0-B v0.1.1)
```

**Status invariant**: 全部 Phase 1 findings PROVISIONAL，per
`r8_phase1_lifecycle_spec.md` AC-6 與 §Panel Governance。IF-1 closure 不
解除此 label；需 formal P1-DATA close（含 IF-2, IF-3）+ SPEC-level
sign-off 才能升級。

---

## Locked Methodology Summary

**此章節為 most-likely-to-be-re-litigated 段落。** 下 session 開始前請優先回顧，
避免重新討論已 lock 決策。

### Inference (ADR-R8P1-001)

| 決策 | Locked value | Rationale 簡述 |
|---|---|---|
| Resampling unit | date-level | LA-6 same-day clustering；event-level 等同 i.i.d.，已知為假 |
| Bootstrap variant | stationary (Politis-Romano 1994) | 保留 stationarity；block-length mis-spec robust |
| Primary block length | 20 trading days | 必須 ≥ max horizon (20td) 處理 overlapping forward returns |
| Sensitivity grid | `{5, 10, 20, 40}` | 揭露 inference 在 L_primary 鄰域穩定性 |
| Hard rule | L ∈ {5, 10} 不得獨立承擔 primary inference | overlap 假設要求 L ≥ 20 |
| Auto block length (Politis-White) | **不**在 locked core；optional robustness 才可報 | 避免 spectral estimator package variance |
| B (replications) | 5000 | 標準慣例 |
| CI method | percentile | 排除 BCa / studentised 額外 tuning surface |
| n_eff / VIF granularity | statistic-level，不是 dataset-level | 不同 statistic 的 effective-n 本質不同 |
| Difference statistics (A-3 等) | **joint resample**，同一份 date sample 套用兩 universe | 保留 cross-sectional 相關性 |
| Regime stratification | **stratified within regime**（不是 pooled-then-stratify）| 對齊 AC-3；honest disclosure of Crisis cell small n_eff |
| Seed discipline | 整數 seed 必入 manifest；同 seed 必須 bit-identical | reproducibility |

### Universe Construction (ADR-R8P1-002)

| 決策 | Locked value | 對應 lifecycle spec |
|---|---|---|
| Construction approach | C (event-matched, date-anchored) | operationalises "incremental timing within RS_T3" |
| Baseline composition | leave-one-out（exclude R8 trigger from baseline）| treatment ∩ baseline = ∅ by construction |
| Benchmark 1 / 2 construction | same (Lock 3)；Benchmark 2 = Benchmark 1 + per-row pullback filter | AC-2 |
| Regime granularity | market-level（verified at lock time）| AC-3 + LA-3 |
| `dist_above_ma20_atr` granularity | per-stock-day（verified at lock time）| Benchmark 2 filter |
| Aggregation | event-duplicated / event-level point estimate；clustering 由 date-level bootstrap 處理 | preserves event grain |
| AC-4 stratification | **symmetric (SD-1β)**：treatment / baseline 各自以自身 close 計算 near_limit_up | 隔離 R8 selection effect from limit-up exhaustion |
| Stratification fall-through | 小 cell **不**回退 asymmetric；P0-B 分類為 DIRECTIONAL_ONLY / INSUFFICIENT | governance laundering 防線 |
| **Benchmark 2 β filter symmetry** | locked β（雙側都套 pullback filter）| **pending SPEC owner verification against AC-2 literal**；見 §掛起事項 |

### Audit Governance (P0-B v0.1.1)

| 決策 | Locked value | 對應依據 |
|---|---|---|
| Primary gate | `n_unique_dates`（不是 n_events）| ADR-R8P1-001 D1 date-level resampling 邏輯延伸 |
| Gate thresholds | PASS ≥ 100, DIRECTIONAL 30–99, INSUFFICIENT < 30 | **governance choice, NOT statistical** — 明文 disclaimer 已 lock |
| Secondary diagnostics | `events_per_date_mean`, `events_per_date_p95` advisory only | LA-6 clustering 揭露，不 gate |
| Output count | 4 tables: D-1, D-2, D-2A, D-2B | AAC-1 |
| D-1 panel | full `daily_features`（diagnostic）| Phase 0 inheritance |
| D-2 panel | R8 event panel | AC-3 / AC-4 mandatory stratification audit |
| D-2A panel | R8 ∩ RS_T3 event panel | A-3 treatment support |
| D-2B panel | union of Baseline_1 ∪ Baseline_2，with `baseline_universe` dimension | A-1/A-2/A-3 baseline support |
| Joint-pair adequacy | **weaker-of-two; downstream-owned; NOT persisted** | 避免 research-specific adequacy engine 漂移 |
| `must_propagate_reason` | closed enum: `{"n_unique_dates<30", "30<=n_unique_dates<100", NULL}` | machine state，不是 commentary |
| Caveat propagation enforcement | **downstream** owns enforcement；failure to inherit ≠ P0-B compliance failure | closed-artifact 原則，避免時間反轉責任 |

---

## Audit Script Acceptance Criteria

從三份 locked artifact 抽出 `scripts/audit_r8_phase1_cell_adequacy.py`
的 implementation contract：

### Required Outputs

```text
data/_storage/r8_phase1_cell_adequacy/v0.1.1/
├── d1_r8_x_rs_tertile.parquet
├── d2_global_adequacy.parquet
├── d2a_a3_support.parquet
├── d2b_baseline_adequacy.parquet
└── manifest.json
```

### Manifest Required Fields

```text
audit_spec_version:         "v0.1.1"
adr_001_version:            "v0.1.0"
adr_002_version:            "v0.1.0"
panel_snapshot_hash:        <DuckDB file hash or equivalent>
r8_event_manifest_hash:     <upstream r8_event_builder output hash>
regime_labels:              <verbatim list from production model>
gate_thresholds:            {pass: 100, directional_min: 30}
query_sql:                  <embedded SQL for each output>
seed:                       <integer, if any sampling used>
```

### Hard Invariants (script must verify before emission)

```text
1. Treatment_1 ∩ Baseline_1 = ∅
2. Treatment_2 ∩ Baseline_2 = ∅
3. All price reads via listed_market_daily_price_adj view (no direct daily_price_adj)
4. Distinct dates in Baseline_k = D_R8 (modulo dates with empty RS_T3 ∩ non-R8, which must be reported as DROPPED_NO_BASELINE, not silently dropped)
5. Stratification consistency per-side:
     Σ over Treatment cells |Treatment_k| Cell| = |Treatment_k|
     Σ over Baseline  cells |Baseline_k|  Cell| = |Baseline_k|
6. Bit-identical reruns on same panel snapshot
7. baseline_universe ∈ {"Baseline_1", "Baseline_2"} (AAC-7)
8. must_propagate_reason ∈ closed enum (AAC-8)
```

### Negative Acceptance (AAC-6, hard)

```text
NO forward-return statistic
NO mean / median / hit-rate
NO inferential CI
NO bootstrap call
```

任一出現於 P0-B output 即為 governance failure。

### File Header

```python
#!/usr/bin/env python3
# scripts/audit_r8_phase1_cell_adequacy.py
"""R8 Phase 1 cell adequacy audit — v0.1.0. Implements P0-B
r8_phase1_cell_adequacy_spec.md v0.1.1.
"""
```

---

## Implementation Prerequisites（下次 session 開始前 verify）

下三項是 audit script 實作的事實前提，本 session 假設成立但**未驗證**：

1. **`r8_event_builder.py` 當前 output schema / manifest 格式** — D_R8 衍生需要它。手 spec 假設可從中讀 `R8_events` rows + manifest hash。
2. **`daily_features` 表的精確 column names** — 特別是 `regime`、`rs_tertile_T-1`（或對應的 RS tertile flag column）、`dist_above_ma20_atr`、`r8_flag`、`bullish_features.computed_at`。LA-2 point-in-time discipline 依賴 `computed_at`。
3. **Production regime model column 命名與 label 值集** — manifest 要 verbatim 紀錄；audit script 不可改名或 bucket。

---

## SPEC Interpretation 掛起事項

### Benchmark 2 β filter symmetry — pending verification

ADR-R8P1-002 §Operational Universe Definitions / Benchmark 2 加註的
**SPEC INTERPRETATION NOTE**：

> Benchmark 2 lock 為 β（symmetric filter on both treatment and
> baseline）。Spec AC-2 字面允許 α（baseline-only filter）詮釋。
> 若 SPEC owner 認定為 α，本 ADR 需 v0.1.1 amendment（或 lifecycle
> spec v0.1.3 amendment 明文澄清）。

**Action required**: SPEC owner 確認後若維持 β，記錄於下次 session 開頭；
若改 α，開 ADR-R8P1-002 v0.1.1 反向 amendment（Treatment_2 = Treatment_1，
不加 pullback filter），並重作 P0-B v0.1.2（Baseline_2 維持，但 Treatment_2
audit 改用 D-2A 涵蓋）。

---

## Backlog 現狀

### Resolved 本 session

- ADR-R8P1-001 lock（block-bootstrap effective-n method）
- ADR-R8P1-002 lock（baseline benchmark construction）
- P0-B v0.1.1 amendment lock（baseline-side adequacy D-2B）
- AAC-5 retrofit: `must_propagate_reason` 加入 D-2 / D-2A schema

### Open 本 session 新增

- **`scripts/audit_r8_phase1_cell_adequacy.py` implementation** — Next session first task
- **BACKLOG-IF1-GUARD**：repo-wide pytest guard for no-direct-daily_price_adj outside allowlist
  - Scope: `research/`, `features/`, `strategies/`, `replay/`
  - Allowlist: `data/etl/`, `scripts/audit_*`, `tests/`
  - 獨立追蹤，不綁 P0-B 完成
- **多條件 reason encoding amendment**（將來 v0.1.2 trigger）：若未來 gate 升級到多條件（例：events_per_date_mean 從 advisory 升為 gate），reason 應演化為 JSON array 而非字串串接

### Open 沿用自 2026-06-05 handoff

- P1-DATA IF-2 (empty `stock_info`) — OPEN
- P1-DATA IF-3 (empty `corporate_actions`, DQ-CA-001) — OPEN
- P1-DATA-FOLLOWUP: retire/rewrite `scripts/ingest_security_lifecycle.py` — OPEN
- TWSE Holiday Calendar (P1) — OPEN
- P1-OBS: Intraday Monitor Self-Alert — OPEN
- P2-OBS: Healthcheck Single Run Gap — OPEN
- P3-OPS: Session Write Lock Policy — OPEN

### Deferred 沿用自 2026-06-05 handoff

- v0.1.17 ARCHITECTURE.md refresh
- timestamp semantics backlog #14
- Kairos Phase B bearish / TX futures directional signal
- Kairos backlog items #27 / #28 / #29
- R8 Benchmark C date-level weighting refactor（**注意**：此項與本 session 的 ADR-R8P1-002 lock 可能有衝突；重新評估是否仍適用）
- r8_forward_returns engine 統一
- `eligible_universe.py` defensive duplication 清理
- `eligible_date_predicate()` 改名為 `panel_start_date_predicate()`

---

## Next Session First Task

```text
Implement: scripts/audit_r8_phase1_cell_adequacy.py

Implementation contract: 完全由本 handoff §Audit Script
Acceptance Criteria 定義。Methodology 不再重新討論；若有歧義，
從三份 locked artifact 內找答案。

不是: 繼續 methodology discussion
不是: 重新審視 lock decisions
不是: 開始 A-3 analysis（前置條件未滿足）
```

開始前先做 §Implementation Prerequisites 三項事實 verification。

---

## Brief History（本 session 之前的狀態）

本 session 之上接 2026-06-05 P1-DATA IF-1 remediation（HEAD `8a2d8d5`），
進入 R8 Phase 1 analysis 前置作業。Pre-session 狀態：

- R8 findings 被 handoff 標為 "NON-PROVISIONAL REVIEWABLE"，但本 session
  governance review 後**撤回**此標籤，回歸 spec literal 的 PROVISIONAL
  狀態（IF-2, IF-3 未 closed → AC-6 unconditional binding）。
- R8 Phase 1 lifecycle spec v0.1.2 已 LOCKED（2026-06-02），但缺：
  - Effective-n estimation 方法（spec scope §7 要求 ADR before first output）
  - Cell adequacy audit 規範
  - Baseline universe construction methodology

本 session 補完上述三項，governance layer 至此收斂。

---

*End of handoff_2026_06_06_session_end.md*
