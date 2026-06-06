# Helios Handoff Supplement — 2026-06-06 A-3 Implementation Pack

**用途：** 補充 `handoff_2026_06_06_p0b_complete.md` 缺失的 ADR 全文。
下 session 開始請**先讀這份**，再讀 P0-B complete handoff。

---

## 先回答「新 session 找不到文件」的問題

ADR 全文在 repo 裡：

```bash
cat ~/projects/helios/research/adr/ADR-R8P1-001-block-bootstrap-effective-n.md
cat ~/projects/helios/research/adr/ADR-R8P1-002-baseline-benchmark-construction.md
cat ~/projects/helios/research/r8_phase1_cell_adequacy_spec.md
cat ~/projects/helios/research/r8_phase1_lifecycle_spec.md
```

但為避免再次找不到，以下直接嵌入 A-3 實作必須的 ADR 關鍵段落。

---

## ADR-R8P1-001 v0.1.0 關鍵決策（A-3 直接依賴）

### D1. 重採樣單位：trading date

> The unit of resampling is the **trading date**. When a date is drawn
> into a bootstrap sample, all R8 events occurring on that date are
> included as a unit. Event-level resampling is prohibited because it
> breaks same-day clustering (LA-6).

**實作意涵：** block 是 date-level，不是 (stock_id, date) pair。一個 date 被抽到，該 date 的所有 events 全部納入。

### D2. Bootstrap variant：stationary bootstrap

> The stationary bootstrap of Politis & Romano (1994) is used. Block
> lengths are drawn from a **geometric distribution with mean equal to
> the parameter L** defined in D3.

**實作意涵：** 不是固定長度的 moving block。每次 block 長度從 Geometric(1/L) 抽取，期望值 = L。

### D3. Block length

```
Primary:          L_primary = 20 trading days
Sensitivity grid: L_grid = {5, 10, 20, 40}

Hard rule (LOCKED):
    No inferential statement may rely solely on L ∈ {5, 10}.
    Primary inference must use L_primary = 20.
    L = {5, 10} are sensitivity diagnostics only.
```

**理由：** max horizon = 20td，overlapping forward returns 要求 L ≥ max_horizon。這不是 tuning choice，是結構性約束。

### D4. Overlap handling

> Forward-return windows at horizon h create overlap up to lag h−1.
> The locked method handles this by requiring L_primary >= max_horizon = 20.

### D5. Joint resample for differences（A-3 核心）

> When estimating any statistic of the form θ_A − θ_B where A and B
> are two universes drawn from the same panel (e.g. R8∩RS_T3 vs RS_T3
> unconditional), **the same date resample must be applied to both
> universes within each bootstrap replication**. Independent resampling
> of A and B is prohibited: it discards the cross-sectional correlation
> that is the very source of variance reduction in the comparison.

**實作意涵：**
```
for each bootstrap replication b:
    sampled_dates_b = stationary_bootstrap_sample(D_regime, L=20)
    treatment_b = all (stock_id, date) in Treatment_1 where date in sampled_dates_b
    baseline_b  = all (stock_id, date) in Baseline_1  where date in sampled_dates_b
    δ_b = mean_return(treatment_b) − mean_return(baseline_b)
```
不是各自獨立 bootstrap 再相減。

### D6. Reporting format + Locked constants

```
B = 5000 bootstrap replications
CI method = percentile (BCa、basic、studentised 均 EXCLUDED from locked core)
n_eff granularity = statistic-level（不是 dataset-level）
    n_eff(θ) = n_raw / VIF(θ) = n_raw / (SE_bootstrap / SE_naive)²
Seed = integer，必入 manifest，同 seed 必須 bit-identical
```

**注意：** ADR 鎖定 CI method 為 percentile，但**沒有鎖定 p-value 計算方式**。
兩常用作法：
1. `p = 2 × min(P(δ* >= 0), P(δ* <= 0))` （bootstrap null distribution）
2. 從 CI 推斷（CI 不含 0 → 雙側 p < 0.05）

ADR 沒有指定，選擇後記入 A-3 output manifest。

### D7. Regime stratification

> All bootstrap estimation is performed **stratified within regime**.
> Pooled-then-stratify is prohibited.

```
Procedure per regime r:
1. Restrict panel to events with regime[T-1] = r
2. Restrict date pool to dates in that regime
3. Apply D1-D6 within this restricted panel:
   - date-level resampling within regime
   - stationary bootstrap, L=20
   - B=5000, percentile CI
4. Estimate θ_hat, SE_bootstrap, VIF, n_eff, CI_95 separately per r
```

**Honest disclosure requirement:**
> Where a regime cell yields small n_eff (e.g. Crisis with few active R8
> dates), the resulting wide CI is a Phase 1 finding to be reported,
> not a defect to be hidden by pooling.

---

## 回答新 session 的具體問題

| 問題 | ADR 答案 |
|---|---|
| Block 是 single-date 還是 time-window? | Stationary bootstrap，期望 block length = 20td（幾何分布），不是 single-date |
| 抽取對象 | dates only（D1）；date 被抽到則整個 date 的 events 全納入 |
| Stratification | Within-regime（D7），不是 pooled-then-stratify |
| B | 5000（D6）|
| CI method | Percentile（D6），BCa excluded |
| p-value | ADR 未鎖定；選擇後記入 manifest |
| Min bootstrap iterations | 5000（D6 locked） |

---

## A-3 Output Schema（基於 ADR 確認後的版本）

新 session 的草案方向正確，補充 n_eff / VIF 欄位（ADR D6 required）：

```
regime              VARCHAR    -- verbatim from production model
near_limit_up       INTEGER    -- 0 or 1
horizon_td          INTEGER    -- 1, 5, 10, 20 (trading days)
joint_adequacy      VARCHAR    -- PASS / DIRECTIONAL_ONLY / INSUFFICIENT
inference_status    VARCHAR    -- FULL / DIRECTIONAL_ONLY / INSUFFICIENT / SKIPPED

-- Point estimates
treatment_n_events  INTEGER
baseline_n_events   INTEGER
treatment_n_dates   INTEGER    -- n_raw for bootstrap (date-level)
baseline_n_dates    INTEGER
treatment_mean_return  DOUBLE
baseline_mean_return   DOUBLE
delta_obs           DOUBLE     -- θ_treat − θ_base (observed)

-- Bootstrap inference (only when inference_status = FULL)
se_naive            DOUBLE     -- i.i.d. SE
se_bootstrap        DOUBLE     -- block-bootstrap SE
vif                 DOUBLE     -- (SE_bootstrap / SE_naive)²
n_eff               DOUBLE     -- n_raw_dates / VIF
ci_lo               DOUBLE     -- 2.5th percentile
ci_hi               DOUBLE     -- 97.5th percentile
bootstrap_p_value   DOUBLE     -- two-tailed (method recorded in manifest)
block_length_primary INTEGER   -- 20 (locked)

-- Sensitivity (reported, not primary)
-- delta_obs same; SE/CI per block length in separate sensitivity table
```

**DIRECTIONAL_ONLY cells：** point estimate (delta_obs) only，CI/p/n_eff = NULL，inference_status = 'DIRECTIONAL_ONLY'。
**INSUFFICIENT cells：** 整列 skip 或 inference_status = 'INSUFFICIENT'，不計算任何統計量。

---

## Lifecycle Spec — Forward Return Formula（locked）

Per `r8_phase1_lifecycle_spec.md` v0.1.2：

```
forward_return[T+h] = adj_close[T+h] / adj_open[T+1] − 1
```

- `T` = signal date（r8_flag = 1 的 date）
- `T+1` = 次一個交易日 open（entry point）
- `T+h` = h trading days 後的 adj_close（exit point）
- Horizons：`h ∈ {1, 5, 10, 20}` trading days

**注意：** `T+1` 的 adj_open 可能因為 T+1 date 的除權息而與 adj_close[T] 不連續。這是正確行為——公式對齊了實際進場成本。

---

## P0-B Production Results（直接貼用，不需再跑）

```python
# A-3 需要的 cell 分類（joint adequacy = weaker-of-two）
JOINT_ADEQUACY = {
    ('bull',    0): 'PASS',
    ('bull',    1): 'DIRECTIONAL_ONLY',   # D-2B B1 限制
    ('bear',    0): 'PASS',
    ('bear',    1): 'INSUFFICIENT',        # D-2B B1 = 6 obs
    ('crisis',  0): 'DIRECTIONAL_ONLY',
    ('crisis',  1): 'INSUFFICIENT',
    ('neutral', 0): 'PASS',
    ('neutral', 1): 'INSUFFICIENT',        # D-2B B1 = 2 obs
}

# Panel sizes (production run 2026-06-06)
TREATMENT_1_N = 5330
BASELINE_1_N  = 63363

# D-2A treatment n_unique_dates per cell（bootstrap date pool size）
TREATMENT_DATES = {
    ('bull',    0): 615,
    ('bull',    1): 457,
    ('bear',    0): 174,
    ('bear',    1): 96,
    ('crisis',  0): 61,
    ('crisis',  1): 54,
    ('neutral', 0): 126,
    ('neutral', 1): 68,
}
```

A-3 full-inference cells（PASS × PASS）：`('bull',0), ('bear',0), ('neutral',0)` — 三個。

---

## ADR-R8P1-001 Manifest Required Fields（A-3 output manifest 必填）

```
bootstrap_method:         "stationary"
resampling_unit:          "trading_date"
block_length_primary:     20
block_length_sensitivity: [5, 10, 20, 40]
replications:             5000
ci_method:                "percentile"
regime_stratified:        true
seed:                     <integer>
adr_version:              "ADR-R8P1-001 v0.1.0"
p_value_method:           <chosen method, e.g. "two_tailed_reflection">
forward_return_formula:   "adj_close[T+h] / adj_open[T+1] - 1"
horizons_td:              [1, 5, 10, 20]
p0b_audit_version:        "v0.1.1"
p0b_panel_snapshot_hash:  <from P0-B manifest>
```

---

## Implementation Notes

### Python 套件

`scipy` 已在 `pyproject.toml`（per memory）。Stationary bootstrap 可用：
- `arch` package (`StationaryBootstrap`)，或
- 自己實作（geometric block length sampler + date-level resample）

`arch.bootstrap.StationaryBootstrap` 是最直接的選擇。確認：

```bash
cd ~/projects/helios && uv run python3 -c "from arch.bootstrap import StationaryBootstrap; print('OK')"
```

如果沒有，先 `uv add arch`。

### 避免 AAC-6 contamination

A-3 是 inferential output，不受 AAC-6（P0-B 的 no-forward-return 規定）約束。但必須：
- **不修改** P0-B 的 4 個 parquet
- A-3 output 是獨立的新 parquet/manifest，放在 `data/_storage/r8_phase1_a3/v0.1.0/`（或類似路徑）
- A-3 manifest 引用 P0-B manifest hash（provenance chain）

### Status label

所有 A-3 findings = **PROVISIONAL**，per lifecycle spec AC-6（IF-2, IF-3 仍 OPEN）。manifest 必須明文記錄。

---

*End of handoff_2026_06_06_a3_implementation_pack.md*
