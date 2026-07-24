# Technical Screening & Signal Intelligence Service — Phase 0 SPEC

| 欄位 | 值 |
|---|---|
| Document ID | TS-SPEC-P0 |
| Title | Technical Screening Phase 0 Specification |
| Version | v0.1.1 |
| Document Status | SPEC_LOCKED |
| Implementation Status | AUTHORISED (V1 only；V2 受 Gate D entry requirements 與 Q-D1/Q-D2 deferred dispositions 約束) |
| Owner | tpephc |
| Review Authority | tpephc |
| Lock Authority | tpephc |
| Canonical Path | docs/research/technical_screening_phase0_spec.md |
| Repository | git@github.com:tpephc/helios.git |
| Normative Language | MUST / SHALL（強制要求）；SHOULD（預期要求，任何偏離均須有正式 disposition）；MAY（可選）；NON-NORMATIVE（說明性文字，不構成要求） |
| Draft Change Policy | LOCK 前得修訂本 DRAFT；每次提交正式審核的 revision SHOULD 留存 Git commit evidence 與 Change Log |
| Post-Lock Change Policy | LOCK 後禁止修改已鎖版本之 normative content。任何 normative 變更 MUST 建立新版本、Change Log、supersedes 關係、新 canonical hash 與新 lock commit。Implementation-detail 層之要求（如 metrics sink、bucket ordering 細節）得經正式 disposition 調整其強制層級；標示為 INV-* 之 invariant MUST NOT 降級 |
| Lock Conditions | 第 10 節全部 lock-blocking Open Decisions 已完成 disposition；非 lock-blocking decisions MUST 具明示之 deferred disposition 與下游 gate；第 9 節 Acceptance Gates 對應表已審核通過；所有 normative placeholders 已消除；canonical byte hash 與 Git commit SHA 已記錄；canonical path 唯一；working tree clean；Lock Authority 已明示批准 |
| Canonical Hash | 見下方 Lock Record（SHA-256） |
| Lock Commit | PENDING — AWAITING LOCK COMMIT（於 repository 完成 lock commit 後回填 SHA） |
| Supersedes | v0.1.0 DRAFT |
| Superseded By | None |

**Lock Identity Invariant**：

```
The version number alone SHALL NOT identify canonical content.
Canonical identity requires the tuple:
(Document ID, Version, Canonical Path, Content Hash, Lock Commit)
```

**Permitted actions at this status**：specification review、testability review、governance disposition。
**Forbidden before lock**：production implementation、threshold optimisation、outcome inspection、strategy performance claims。

### Lock Record

```
Locked at:              2026-07-23
Document ID:            TS-SPEC-P0
Version:                v0.1.1
Repository:             git@github.com:tpephc/helios.git
Canonical Path:         docs/research/technical_screening_phase0_spec.md
Canonical Hash (SHA-256):
    7eeb8da448deb1d734ebbff7a70a496b5eec00bd419f582227fa96ff565a4b25
Hash convention:
    以本文件完整內容計算，惟 Canonical Hash 欄位之 64 位十六進位值
    於計算前先置換為 64 個 '0'；驗證時依同一程序歸零後重算。
Lock Commit:            PENDING — AWAITING LOCK COMMIT
Dispositions:
    D-TSP0-A1  Gate A LOCKED（Q-A1, Q-A2, Q-A3a, Q-A3b, Q-A4, Q-A5）
    D-TSP0-C1  Gate C LOCKED（Q-C1, Q-C2）
    Q-D1, Q-D2 DEFERRED_TO_V2
Lock Authority approval:
    LOCK APPROVED. TS-SPEC-P0 v0.1.1 is authorised to transition from
    DRAFT — PRE-LOCK to SPEC_LOCKED. V1 implementation is authorised.
    V2 remains subject to the Gate D entry requirements and deferred
    dispositions (Q-D1, Q-D2).
```

---

## 1. Purpose and Scope

### 1.1 Objective

建立一套三階段、事件驅動的 technical screening pipeline：

1. **Pre-market technical screener**：以封存之 PIT 日線資料執行全市場批次掃描，產出候選池。
2. **Intraday candidate monitor**：僅追蹤候選池，增量更新指標與觸發條件，產生 setup / alert。
3. **Post-market outcome warehouse**：封存 signal decision state，進行 outcome 分析與正式實驗評估。

### 1.2 Research Question

本系統服務於一個預註冊之三臂比較實驗：

- **Arm A** — Role-separated architecture（regime / trend / setup / trigger / confirmation / risk veto）。
- **Arm B** — Correlated-indicator k-of-n voting（預註冊指標集合之多數決）。
- **Arm N** — Matched-null portfolio distribution（匹配曝險結構之虛無投資組合重抽樣）。

研究問題：**Arm A 之成本調整後樣本外結果，是否優於 Arm B，且任一 arm 是否相對 Arm N 展現可交易之 edge。**

### 1.3 Explicit Non-Goals

第一版不包含：

- fully automated execution；
- claimed alpha；
- broker-independent live fill guarantees；
- machine-learning model selection；
- portfolio deployment approval。

### 1.4 System Boundary

```
raw market data
    → immutable source snapshots
    → feature computation
    → eligibility
    → setup creation
    → trigger events
    → notifications
    → outcome evaluation
```

任何越過 snapshot 層直接讀取可變上游資料之路徑，均違反本 SPEC。

---

## 2. Definitions and Time Semantics

本章定義優先於 Gate A–D，各 gate 不得另行重複定義。

### 2.1 術語

| 術語 | 定義 |
|---|---|
| `market_date` | 訊號所屬交易日 |
| `session_date` | 實際交易時段所屬日（台股日盤與 `market_date` 相同；若未來納入盤後/夜盤商品則分離） |
| `event_ts` | 市場事件實際發生之時間戳 |
| `ingested_at` | 系統接收該筆資料之時間戳 |
| `available_at` | 系統首次**可能合法知悉**該資訊之時間戳 |
| `announcement_ts` | 公司行動（corporate action）公告可知悉之時間戳 |
| `effective_date` | 公司行動生效日（如除權息日） |
| `knowledge_cutoff_ts` | 單次 run 允許使用資訊之最晚時點 |
| `run_started_at` | 該次 run 實際啟動之時間戳 |
| `source_snapshot_id` | 來源資料分割之確定性身份（見 Gate B2） |
| `setup_instance_id` | 單一 setup 實例之確定性身份（見 Gate D1） |
| `trigger_event_id` | 單一觸發事件之確定性身份（見 Gate D1） |
| `notification_attempt_id` | 單次通知投遞嘗試之身份（見 Gate D3） |

### 2.2 核心時間 Invariant

- `event_ts` 描述市場事件何時**發生**；`available_at` 描述系統何時**可能知悉**。兩者 MUST NOT 混用。
- `market_date` 與 `knowledge_cutoff_ts` MUST 分開記錄，MUST NOT 以單一 `as_of_date` 欄位兼任。
- **INV-T1**：任何 `available_at > knowledge_cutoff_ts` 之紀錄，MUST NOT 影響該次 run 之任何輸出。
- **INV-T2**：`knowledge_cutoff_ts <= run_started_at`。
- 盤中指標 MUST 區分三類語義，並於輸出欄位命名中明示：
  - `confirmed_daily_indicator`：僅使用已收盤封存日線計算，為固定狀態；
  - `provisional_daily_indicator`：使用當日盤中價格代入日線公式之估計值，僅供盤中參考；
  - `intraday_indicator`：純盤中資料計算之指標。
- 僅 `confirmed_daily_indicator` MUST 被視為固定狀態。
- Provisional indicator MAY 參與已註冊之盤中 trigger rule，惟其 event-time computation、input boundary 與 replay semantics MUST 明確版本化。
- 正式 outcome 評估 MUST 使用 trigger timestamp 當時可觀測之 provisional value 重建訊號；MUST NOT 以收盤後 final end-of-day indicator value 取代之。

---

## 3. Gate A — Methodology Validity

### A1. Three-Arm Experimental Design

#### A1.1 Arm 定義

- **Arm A（Role-separated）**：條件依角色分層——Regime（是否允許做多）、Trend（方向）、Setup（型態）、Trigger（進場時點）、Confirmation（輔助證據）、Risk（否決權）。各角色之具體指標與參數屬 versioned rule definition。
- **Arm B（k-of-n voting）**：由預註冊指標集合（初稿建議：MACD、RSI、KDJ、OBV、MA）以 k-of-n 多數決產生訊號。k、n 與指標集合 MUST 於 LOCK 前凍結。
- **Arm N（Matched null）**：null-generation protocol，而非單一固定投資組合 arm。每一受評估之 active arm MUST 生成各自匹配之 null 分布：`Null(A)` 匹配 Arm A 之曝險結構，`Null(B)` 匹配 Arm B 之曝險結構。正式比較為 `A vs B`、`A vs Null(A)`、`B vs Null(B)`。

#### A1.2 Null 匹配結構

Arm N MUST 保持以下曝險結構與實際 arm 一致：

```
date、market regime、liquidity bucket、eligibility、
signal count per date、direction、entry timestamp convention、
holding horizon、cost model
```

#### A1.3 Null Protocol

- **Resampling unit**：完整 portfolio path，MUST NOT 以孤立單筆交易為單位。
- **Sampling**：stratum 內 SHALL 允許放回抽樣（replacement）。
- **Minimum repetitions**：MUST ≥ 1,000 次 null portfolio replication；當 Monte Carlo standard error 超過預註冊容忍值時 MUST 增加次數直至達標。1,000 為 initial minimum，不構成統計充分性之永久保證。
- **Randomness**：MUST 使用 deterministic master seed 與衍生 replication seeds；所有 seed 值 MUST 持久化於 run manifest。
- **推論基礎**：統計推論 MUST 建立於 null portfolio 分布之上，MUST NOT 建立於單次逐日配對。

#### A1.4 Sparse Strata Fallback 層級

當 strata 樣本不足時，MUST 依下列預定義層級降級，MUST NOT 於執行時臨時決定：

```
Level 1: exact date × regime × liquidity bucket
Level 2: adjacent liquidity bucket within same date and regime
Level 3: same date and regime
Level 4: null draw marked unavailable
```

Fallback 允許層級 **LOCKED（D-TSP0-A1）：L1→L2→L3；Level 3 仍不足即標記 Null unavailable，MUST NOT 跨日借用樣本**（寧缺勿偏：missing null 優於 biased null）。每次 draw 實際使用之 fallback level MUST 寫入 null replication manifest。
- Fallback 之 determinism：liquidity-bucket ordering、上下側 tie-breaking rule、是否合併兩側、最低 eligible candidate count、replacement 之 symbol multiplicity 上限、以及每次 draw 實際使用之 fallback level，MUST 於 null generation 前凍結，且 fallback level MUST 寫入 null replication manifest。

### A2. Parameter Selection Protocol

- 參數選擇協議 **LOCKED（D-TSP0-A1）：PREREGISTERED_FIXED**。所有 threshold、window、holding horizon MUST 於正式 evaluation 前凍結。Nested walk-forward validation 保留為 SPEC v2 之候選方法，本版 MUST NOT 使用。
- 採 nested validation 時：
  - purge MUST ≥ 最大 forward horizon；
  - embargo 區間 MUST 預註冊；
  - search budget MUST 於 Arm A 與 Arm B 之間對稱；禁止任一 arm 擁有較大之調參預算。
- 下列參數 MUST NOT 於全資料上直接調整後再宣稱 out-of-sample 結果：RVOL threshold、ORB window、ORB buffer、score threshold、ATR multiple、maximum entry extension、holding horizon。

#### A2.1 Pilot Window 隔離

- Pilot 資料 MUST 滿足 `pilot_end < evaluation_start`，或採 live shadow pilot period 後接不重疊之 locked evaluation period。Pilot window 之起訖 MUST 記錄於本 SPEC 或其附錄。
- Pilot 僅可用於估計 nuisance parameters：signal density、return variance、cluster dependence、effective sample size ratio、runtime load。
- Pilot MUST NOT 用於：threshold optimisation、indicator replacement、holding-horizon selection、best-subgroup selection。

### A3. Estimands and Outcomes

- **Primary estimand LOCKED（D-TSP0-A1）：net-of-costs cumulative excess return over H trading days, measured at the portfolio-day level**，其中 H = 10 trading days（Q-A3b LOCKED；5D / 20D 保留為 secondary outcome）。Primary estimand 唯一，MUST NOT 新增。
- Secondary outcomes：MFE、MAE、hit rate、downside tail、turnover、signal density、regime stability、temporal stability。Secondary outcomes 之推論位階 MUST 低於 primary estimand（見 A5）。
- 下列慣例 MUST 於 LOCK 前定義：
  - entry convention（觸發後之進場價格假設與時點）；
  - exit convention（停損、停利、time stop 之優先序）；
  - holding horizon；
  - overlapping-position policy（同一 symbol 重疊持倉之處理）；
  - corporate-action treatment（持有期間除權息之報酬計算）；
  - missing-exit policy（至資料末端仍未出場之處理）。

### A4. Power, Interim Review and Verdict Semantics

#### A4.1 Power-Design Contract（Phase 0 鎖定）

下列項目 MUST 於 Phase 0 鎖定，屬 design points，MUST NOT 被解讀為對真實 edge 之預測：

- effect-size grid（建議：5 / 10 / 20 bp）；grid 之量測尺度 MUST 固定並明示（例如：net-of-costs 之 cumulative H-day excess return per portfolio-day），MUST NOT 混用 per-trade、per-portfolio-day 與 gross/net 尺度；
- nominal alpha；
- target power；
- primary estimand（同 A3）；
- cluster unit；
- minimum evaluation window；
- interim schedule；
- continuation rule；
- final decision point。

Pilot 完成後 SHOULD 以 pilot 估計之 nuisance parameters 更新 time-to-evidence；該更新 MUST 僅使用 A2.1 許可之用途。

#### A4.2 Verdict 語義

評估結論 MUST 為下列四者之一：

```
EDGE_SUPPORTED / PRACTICALLY_NULL_SUPPORTED / INCONCLUSIVE / INVALIDATED
```

- **underpowered 之結果 MUST 判定為 INCONCLUSIVE，MUST NOT 判定為 PRACTICALLY_NULL_SUPPORTED。**
- `PRACTICALLY_NULL_SUPPORTED` MUST 以預註冊之 smallest effect size of interest（SESOI）及 formally specified 之 practical-null 程序（equivalence test、ROPE、或具預註冊 futility boundary 之 sequential design）為依據。
- **未拒絕 superiority null MUST NOT 作為 PRACTICALLY_NULL_SUPPORTED 之充分條件。** 若 LOCK 前未定案 practical-null framework，則該 verdict 暫停使用，僅保留 `EDGE_SUPPORTED / INCONCLUSIVE / INVALIDATED`。

#### A4.3 Optional-Stopping 防線

- INCONCLUSIVE MUST NOT 觸發無限期觀察。Continuation rule **LOCKED（D-TSP0-A1）：FIXED_EXTENSION**——預註冊初始評估窗口；INCONCLUSIVE 時允許**一次**固定長度延長；延長結束後 MUST issue final verdict。GROUP_SEQUENTIAL 本版 MUST NOT 使用。初始窗口與延長長度之具體月數 MUST 於 V3 評估啟動前依 pilot nuisance 估計核定，並記錄於 run manifest。
- 下列行為 MUST NOT 發生：
  - continue collecting until p < alpha；
  - unregistered interim testing；
  - changing horizon after observing results。

### A5. Multiple Testing Family

- 同一 hypothesis family 之範圍 MUST 明確列舉，至少涵蓋：arms、horizons、thresholds、regimes、subgroups、secondary metrics。
- 控制方法 **LOCKED（D-TSP0-A1）：Hierarchical testing**。層級：L1 = primary estimand, Arm A vs Arm B；L1 成立方得進入 L2 = Arm A vs Null(A)、Arm B vs Null(B)；其後依序為 secondary metrics → subgroups → exploratory。任何層級未通過，其下層結論 MUST NOT 升格為 confirmatory。
- 標示為 exploratory 之結果 MUST NOT 升格為 confirmatory conclusion；其後續驗證 MUST 以新之預註冊實驗進行。

### A6. Dependence and Resampling

- 推論 MUST 處理下列依賴結構：same-symbol repeated signals、same-date cross-sectional dependence、overlapping holding periods、market-wide shocks、re-entry dependence。
- 推論單位 SHOULD 為 date-level portfolio return 或 date-clustered bootstrap；最終方法 MUST 依 A3 之 estimand 鎖定，MUST NOT 先選定統計工具再反推研究問題。
- market event 數量與 independent research sample 數量 MUST 分開報告，MUST NOT 混用。

---

## 4. Gate B — PIT Reproducibility

### B1. Knowledge-Cutoff Contract

- 所有輸入紀錄 MUST 滿足 `available_at <= knowledge_cutoff_ts`（INV-T1）。
- `run_started_at` MUST NOT 早於所需 dataset readiness 之完成時點。
- Historical replay MUST 解析至明示之 `source_snapshot_id`；MUST NOT 默認讀取「最新版本」之可變狀態。

### B2. Immutable Snapshot Contract

- 每個 snapshot MUST 至少記錄：

```
source_snapshot_id, dataset_name, partition_manifest, content_hashes,
row_count, schema_version, calendar_snapshot_id, universe_snapshot_id,
corporate_action_snapshot_id, adjustment_policy_version, ingestion_version,
created_at, knowledge_cutoff_ts,
（各 partition 之 min_event_ts / max_event_ts / ingested_at / available_at）
```

- Identity MUST 分層，MUST NOT 以單一欄位兼任：
  - `source_snapshot_id`：單一 materialized snapshot instance 之 immutable identity；
  - `manifest_hash`：canonical manifest 之 deterministic hash；
  - `content_hash`：來源 content bytes / normalized rows 之 deterministic identity。
- 各 hash 之 input MUST 明定是否包含 `created_at`、storage path、ingestion runtime metadata；相同 content 於不同時間 re-materialize 時，`content_hash` MUST 相同、`source_snapshot_id` MAY 不同。Deterministic replay 之身份比對 MUST 以 `manifest_hash` / `content_hash` 為準。
- **Adjustment policy version**：MUST 定義 adjustment formula、rounding policy、factor chaining policy、cash dividend treatment、stock dividend treatment、capital reduction treatment、revision handling、provider-specific normalization。
- **INV-B2**：同一來源資料於不同 `adjustment_policy_version` 下 MUST 生成不同 snapshot identity。禁止 `same source_snapshot_id + different adjustment logic`。
- Snapshot MUST 為 immutable。資料源回溯修正時 MUST NOT 覆寫原 snapshot，僅得依 B6 產生新版本。

### B3. Corporate-Action Time Semantics

- **INV-B3**：公司行動之資訊可用性 MUST 以 `announcement_ts` 為鍵，MUST NOT 以 `effective_date`（ex_date）回溯回填。
- 時間欄位 MUST 分離記錄：`announcement_ts`、`effective_date`、`record_date`、`payment_date`、`revision_ts`。
- 價格資料層 MUST 分離：
  - `raw_observed_price`；
  - `pit_adjusted_price`：僅使用當時已知、且依當時 adjustment policy 可得之公司行動狀態所計算；
  - `latest_final_adjusted_price`。
- 正式 replay MUST NOT 默認使用 `latest_final_adjusted_price`。
- **Adjustment activation invariant**：資訊可用性、經濟生效性與價格序列轉換為三件不同之事，MUST 分離治理：
  - corporate-action metadata availability SHALL be keyed by `announcement_ts`；
  - price adjustment activation SHALL be governed separately by `effective_date` and `adjustment_policy_version`；
  - a known but not-yet-effective corporate action SHALL NOT automatically cause historical observed prices to be back-adjusted before the policy-defined activation point。
- `adjustment_policy_version` MUST 明確定義三條規則：knowledge activation rule、economic activation rule、back-adjustment activation rule。

### B4. PIT Universe and Survivorship

- PIT universe MUST 保留下列狀態之 symbol 至其最後可交易日：listed、suspended、delisted、merged、renamed、market-transferred、temporarily non-tradable。
- **INV-B4**：A symbol is eligible on date t only if its lifecycle interval contains t and all strategy-specific eligibility rules pass at t.
- MUST NOT 以當前存活 universe 向過去投影（current surviving universe projected backward）。
- Eligibility gate MUST 拆為可稽核之獨立條件，MUST NOT 籠統歸入單一 `lifecycle_passed`，至少包括：listed and active、not suspended、處置股限制、注意股限制、當沖資格、信用交易資格（如策略需要）、board-lot / odd-lot 相容性、price-limit proximity、liquidity、corporate-action status。

### B5. Deterministic Replay

- 相同之 source snapshots、rule version、cost model、adjustment policy、random seeds、runtime configuration，MUST 產生相同之：candidate set、setup instances、trigger events、null replication manifest、outcome records。
- Runtime configuration 之 deterministic-critical 範圍 MUST 至少列舉：timezone、calendar version、numeric precision、thread count（於影響 determinism 時）、DuckDB / Polars 等相關套件版本、sort and tie-break policy。無須鎖定全部 dependency patch version。
- 浮點比較容忍度與排序 tie-breaker MUST 明定。

### B6. Revision Policy

- Revision MUST NOT 覆寫舊 snapshot。事件類型至少包括：

```
SOURCE_CORRECTION / ANNOUNCEMENT_REVISION / ACTUAL_EFFECT_MISMATCH /
SCHEMA_MIGRATION / ADJUSTMENT_POLICY_CHANGE
```

（公司行動層面細分：ANNOUNCEMENT_REVISED_BEFORE_EFFECTIVE_DATE、ANNOUNCEMENT_REVISED_AFTER_EFFECTIVE_DATE、ACTUAL_EFFECT_DIFFERS_FROM_ANNOUNCED。）
- 每次 revision MUST 產生：new snapshot、new lineage edge、new content hash、explicit supersedes reference。

---

## 5. Gate C — Execution Fidelity

### C1. Tick-Table Snapping

- Tick table 權威來源 **LOCKED（D-TSP0-C1）**：TWSE/TPEx 官方公告之 tick-size schedule，MUST 依 effective date 解析並以 `tick_rule_version` 版本化。Historical replay MUST 依 `market_date` resolve 對應之 tick rule version；MUST NOT 以 latest schedule 回套全部歷史期間。
- 任何理論價位進入可執行語義前，MUST 依解析後之 tick table snap。
- Snap direction MUST 依 order semantic 決定：`UP` / `DOWN` / `NEAREST`。Long stop 通常 SHOULD 向下 snap；limit entry 之方向依訂單語義定義。
- Decimal 型別 MUST NOT 被視為合法報價之保證；snapping 後 MUST 驗證 price band、daily price limit、order type、board-lot / odd-lot session、market status。
- 訊號記錄 MUST 同時保存：`theoretical_price` 與 `executable_price`，以及 `tick_rule_version`、`snap_direction`，以量化 snapping 對 risk budget 之影響。

### C2. Spread, Slippage and Liquidity

- 流動性約束 MUST 同時包含：absolute turnover floor、participation-rate limit、quantity-based volume constraint、spread ceiling、estimated exit capacity。
- 參考形式（參數值屬 versioned configuration，非本 SPEC 常數）：

```
median_turnover_20d >= absolute_floor
planned_notional <= participation_rate * median_turnover_20d
planned_quantity <= fraction_of_median_volume
estimated_exit_capacity >= position_size
```

- 任何 threshold 之具體數值（含任何 participation rate 直覺值）均屬待驗證參數，MUST NOT 於本 SPEC 中宣稱安全。

### C3. Gap-Through-Stop

- **INV-C3**：MUST NOT 假設以 stop price 成交（fill at stop price by assumption 屬禁止事項）。
- 基準模型：trigger 後之 next executable price，受限於流動性與漲跌停約束。
- 訊號 outcome 記錄 MUST 包含：trigger price、first tradable price、fill delay、gap loss。

### C4. Price-Limit Lock and Suspension

- 退出模型 MUST 處理：limit-up lock、limit-down lock、no executable volume、suspension、delayed reopen、multi-day trapped position。
- 跌停鎖死且無成交時：position remains open、unrealized loss continues、exit attempts roll forward。MUST NOT 假設以跌停價立即全數成交。
- 未成交部位 MUST NOT 於 replay 中憑空消失。
- Exit simulation MUST 輸出：`stop_trigger_ts`、`first_executable_ts`、`requested_quantity`、`filled_quantity`、`average_fill_price`、`unfilled_quantity`、`days_trapped`、`exit_reason`。

### C5. Partial Fills

- 記錄 MUST 包含：requested_qty、filled_qty、remaining_qty、average_fill_price、fill timestamps、participation constraint、queue assumptions。
- 於缺乏 order-book replay 時，執行模型 MUST 明示為 approximation，MUST NOT 表述為 verified execution truth。

### C6. Versioned Cost Model

- 成本 MUST 分層：statutory cost、broker-specific cost、research assumption、live deployment cost。券商折扣率屬 deployment-specific，MUST NOT 視為市場自然常數。
- 建議資料模型：`cost_model_id, effective_from, effective_to, market, instrument_type, side, trade_type, commission_rate, commission_discount, minimum_commission, transaction_tax_rate, slippage_model_id, impact_model_id`。
- Historical replay MUST 按交易日 resolve 對應版本；MUST NOT 以最新稅費設定回套全部歷史期間。具落日條款之稅制參數（如當沖稅率待遇）MUST 以生效期間建模。
- 基準 slippage model **LOCKED（D-TSP0-C1）：Research Baseline Slippage Model v1**——`slippage = max(1 tick, 0.5 × observed bid-ask spread)`，對 long entry、long exit、short 皆向不利方向計。有 observed spread 時 MUST 使用 observed spread；歷史 bid-ask 不可得（如僅 OHLCV）時 MUST fallback 為 `1 tick`。
- 本模型屬 **research assumption only**，MUST NOT 被解讀為 execution-truth model；V3 累積實際成交資料後 SHOULD 校準並產生新版本。

---

## 6. Gate D — Runtime Correctness

### D1. Domain Identity

- `setup_instance_id` 與 `trigger_event_id` MUST 為 deterministic 且可重播。建議形式：

```
setup_instance_id = hash(symbol, trading_date, setup_type, setup_version, source_snapshot_id)
trigger_event_id = hash(setup_instance_id, trigger_sequence, canonical_trigger_event_ts, trigger_rule_version)
```

- Identity 中之 `trigger_ts` MUST 為 canonical event-time，MUST NOT 使用 processing-time、ingestion-time 或 notification-time；其 timezone、precision、rounding、session bucket 與 canonical serialization MUST 明定。

### D2. Duplicate and Re-entry Semantics

- 狀態機至少涵蓋：

```
CREATED → WATCHING → APPROACHING → ARMED → TRIGGERED
        → COOLDOWN → REARMED → INVALIDATED → EXPIRED → CLOSED
```

（上圖為 NON-NORMATIVE overview，不構成完整狀態機定義。）
- Normative state-machine definition MUST 以 transition table 表達，逐列定義 `Current state | Event | Next state | Side effect | Idempotency rule`，並涵蓋所有合法路徑（如 `WATCHING → INVALIDATED`、`ARMED → EXPIRED`、`TRIGGERED → CLOSED`、`COOLDOWN → EXPIRED`、`REARMED → TRIGGERED`）。Transition table 為 Gate D contract 之一部分，屬 V2 Entry Gate 審核項目。

- Re-entry policy MUST 明定為下列之一：`REENTRY_DISABLED` / `REENTRY_ONCE` / `REENTRY_AFTER_COOLDOWN` / `REENTRY_AFTER_FULL_RESET`，並定義 cooldown、rearm condition、maximum re-entry count。
- **預設**：one primary trigger per `setup_instance_id` per trading day。後續重複突破 SHOULD 記錄為 market events，但 MUST NOT 自動計為獨立 research samples。
- 通知觸發 MUST 採狀態轉換驅動，MUST NOT 每分鐘重複推播。

### D3. Signal / Notification Separation

- **INV-D3**：Trigger creation is a domain event. Notification delivery is an infrastructure side effect.
- `trigger_event` 為唯一 immutable domain record；`notification_attempt` 為 zero-to-many 之投遞紀錄。
- Telegram retry MUST NOT 產生新 `trigger_event_id`。
- 研究分析 MUST 僅基於 `trigger_event`；MUST NOT 以通知成功送達作為訊號存在之條件。

### D4. Telemetry Measurement Points

- 測量點 MUST 至少包括：event received、queue entered、evaluation started、evaluation completed、notification enqueued、notification delivered。
- Latency 量測 MUST 使用 monotonic clock；wall clock 僅用於 audit timestamp。
- 核心 latency 指標：ingest_to_evaluation、evaluation_duration、queue_wait、evaluation_to_notification、end_to_end_alert_latency。

### D5. Runtime SLO

- SLO 項目（初稿建議值，最終值屬 Open Decision Q-D2）：p99 Stage A cycle latency、p99 trigger evaluation latency、queue backlog age、stale quote age、event drop count、reconnect duration。
- 每項 SLO MUST 定義：measurement point、sampling frequency、metrics sink、aggregation window、failure threshold。
- Metrics sink（Open Decision Q-D1）：單機部署初期 SHOULD 採 structured logs + DuckDB telemetry table（如 `runtime_metrics(run_id, component, metric_name, observed_at, value, unit, tags_json, setup_version)`）；無強制要求導入 Prometheus。
- **本 Gate 為盤中 V2 之 entry gate，不阻擋盤前 V1 scanner 動工。**

### D6. Readiness and No-op Semantics

- 盤前與盤中 pipeline MUST 先通過 readiness gates：trading calendar、market status、source freshness、coverage、schema、snapshot integrity、corporate-action readiness。
- 每次 run MUST 留下 audit record：`run_id, scheduled_at, started_at, gate_results, failure_code, input_snapshot_ids, candidate_count, completed_at, status`。
- 結果狀態 MUST 為：

```
SUCCESS / NO_OP_NON_TRADING_DAY / NO_OP_MARKET_CLOSED /
BLOCKED_STALE_DATA / BLOCKED_INCOMPLETE_COVERAGE / FAILED_RUNTIME
```

- **INV-D6**：MUST NOT 以 stale data 產生看似正常之候選池。Every readiness failure MUST terminate without candidate production and MUST persist an audit record；terminal status MUST 依 failure class 為上述列舉之 `NO_OP_*` 或 `BLOCKED_*` 值之一；MUST NOT silent skip，亦 MUST NOT 使用列舉外之籠統狀態。

---

## 7. Initial Operating Envelope

- **Target candidate pool：20–50 symbols。** 此為 operational prior，MUST NOT 視為 permanent invariant，亦不得以硬編碼上限取代量測。
- 正式容量上限 MUST 由實測決定：subscription constraints、p99 latency、queue depth、CPU and memory headroom、notification throughput、human review capacity。容量 N 定義為滿足全部 SLO 之最大 universe size。
- 盤中系統 MUST 採兩階段架構：Stage A（低成本篩選）→ Stage B（精細訊號確認）；僅初步通過者進入 Stage B。
- 盤中相對量能 MUST 採 time-of-day normalized cumulative volume：

```
rvol_tod = cumulative_volume_today / median(historical cumulative volume at same session-time bucket)
```

  - 對齊方式 MUST 為 session minute index（`session_minute = 0, 1, 2, ...`），MUST NOT 僅依 wall-clock，以支援延後開盤與特殊交易日。
  - 分母 MUST NOT 使用全天平均量。
  - MUST 定義例外處理：insufficient history、zero-volume historical bucket、IPO / recently listed、halted、delayed open、auction-only prints、missing minute bars、half-day or abnormal session。
- Opening range breakout MUST 版本化（如 `ORB-15-v1`），定義 range 區間、trigger、confirmation、breakout buffer、volume confirmation、close confirmation、retest requirement、maximum entry extension；MUST NOT 僅以「opening range breakout」一詞作為實作依據。
- 排程器僅為 trigger。Pipeline 自身 MUST 擁有 run identity、locking、readiness gates、idempotency、audit records 與 failure state。

---

## 8. Phase Plan

| 階段 | 內容 | 進入條件 |
|---|---|---|
| Phase 0 | 本 SPEC、contracts、schemas、test matrix、governance lock | — |
| V1 | PIT pre-market scanner、immutable output snapshot、rule versioning、audit trail、Streamlit review surface | SPEC_LOCKED |
| V2 | intraday ingestion、time-of-day volume profile、state machine、telemetry、capacity test | **Entry**：Gate D contract 與 test matrix 經審核通過（telemetry schema、state-machine transition table、SLO measurement boundaries 核定）；**Exit**：Gate D 自動化測試通過、load/capacity evidence 與 telemetry completeness 驗收 |
| V3 | execution-aware outcome warehouse、three-arm experiment、pilot nuisance estimation、formal evaluation | V2 穩定運行且 pilot window 依 A2.1 隔離完成 |
| V4 | production hardening、operational recovery、deployment separation、approval workflow | V3 verdict 產出 |

---

## 9. Acceptance Gates Before Implementation

本 SPEC 之每項 normative 要求 MUST 對應至少一項 verification mechanism：（1）automated test；（2）static / schema validation；（3）reproducibility evidence；（4）governance review；（5）signed disposition or audit record。凡無法以自動化測試完整證明之要求（如 Lock Authority 批准、prohibited evidence 未使用、search budget 對稱合理性、exploratory 未升格），MUST 以（4）或（5）驗證。LOCK 前 MUST 完成 acceptance matrix 之審核，matrix 每列至少含：`Requirement | Verification type | Evidence artifact | Phase | Blocking status | Owner`。自動化測試對應項目包括：

1. No-future-data tests（INV-T1/T2）
2. Snapshot immutability tests（B2）
3. Corporate-action announcement-time tests（INV-B3）
4. Adjustment-policy-version identity tests（INV-B2）
5. Delisted-universe replay tests（INV-B4）
6. Deterministic replay tests（B5）
7. Duplicate-trigger tests（D2）
8. Notification retry isolation tests（INV-D3）
9. Tick snapping tests（C1）
10. Gap-through-stop tests（INV-C3）
11. Limit-lock persistence tests（C4）
12. Cost-version resolution tests（C6）
13. Non-trading-day no-op tests（INV-D6）
14. Telemetry completeness tests（D4/D5，V2 entry）
15. Time-of-day RVOL alignment tests（§7）
16. Null replication manifest reproducibility tests（A1.3）
17. Sparse-strata fallback path tests（A1.4）

---

## 10. Open Decisions & Decision Ledger

下列事項於 v0.1.1 未定案；每項須有 owner、blocking status、decision deadline、permitted evidence、prohibited evidence。**Lock-blocking 項目全部完成 disposition 為 LOCK 之前提；Deferred 項目得 disposition 為 DEFERRED_TO_V2，不阻擋 SPEC lock，但阻擋 V2 entry。**

### 10.1 Lock-blocking

| ID | 事項 | 候選 | Status | Evidence | Commit |
|---|---|---|---|---|---|
| Q-A1 | Null sparse-strata fallback 允許層級 | **LOCKED：L1→L2→L3，不足即 Null unavailable；禁止跨日借用**（寧缺勿偏） | LOCKED | D-TSP0-A1 | PENDING |
| Q-A2 | 參數選擇協議 | **LOCKED：PREREGISTERED_FIXED**（所有 threshold/window/horizon 於 evaluation 前凍結；nested validation 延至 SPEC v2） | LOCKED | D-TSP0-A1 | PENDING |
| Q-A3a | Primary estimand | **LOCKED：Net-of-costs cumulative excess return over H trading days, portfolio-day level** | LOCKED | D-TSP0-A1 | PENDING |
| Q-A3b | Primary holding horizon | **LOCKED：10 trading days**（5D/20D 為 secondary outcome） | LOCKED | D-TSP0-A1 | PENDING |
| Q-A4 | Continuation rule | **LOCKED：FIXED_EXTENSION**（固定窗口；INCONCLUSIVE 允許一次固定延長，之後強制 final verdict） | LOCKED | D-TSP0-A1 | PENDING |
| Q-A5 | Multiple-testing 控制方法 | **LOCKED：Hierarchical testing**（L1: primary, A vs B → L2: A vs Null(A), B vs Null(B) → secondary → subgroups → exploratory） | LOCKED | D-TSP0-A1 | PENDING |
| Q-C1 | Tick table 權威來源 | **LOCKED：TWSE/TPEx 官方公告之 tick-size schedule，依 effective date 解析；replay MUST 依 market_date resolve tick_rule_version，禁止用 latest** | LOCKED | D-TSP0-C1 | PENDING |
| Q-C2 | 基準 slippage model | **LOCKED：Research Baseline Slippage Model v1——`slippage = max(1 tick, 0.5 × observed spread)`，向不利方向；spread 不可得時 fallback 為 1 tick；屬 research assumption，非 execution-truth model** | LOCKED | D-TSP0-C1 | PENDING |

### 10.2 Deferred（不阻擋 SPEC lock；阻擋 V2 entry）

| ID | 事項 | 候選 | Status | Evidence | Commit |
|---|---|---|---|---|---|
| Q-D1 | Telemetry sink | structured logs + DuckDB（建議） | DEFERRED_TO_V2 | — | — |
| Q-D2 | 初始 SLO 閾值 | §D5 建議值 | DEFERRED_TO_V2 | — | — |

### 10.3 Ledger 規則

- 本表即 Decision Ledger；每項 decision 完成 disposition 時 MUST 更新 Status（LOCKED / DEFERRED_TO_V2 / REJECTED）、Evidence（disposition 文件 ID）與 Commit（Git SHA）。
- SPEC、disposition 文件與 Git commit 三者 MUST 形成可追溯鏈；MUST NOT 於 Ledger 外另設決策紀錄。
- **Prohibited evidence（全部 Q 項通用）**：任何基於 outcome inspection 之調參結果、任何未依 A2.1 隔離之 pilot 資料、任何 latest_final_adjusted_price 產出之歷史統計。

---

## 11. Implementation Readiness Checklist

開工前之一頁式檢查；全部勾選且 Lock Authority 批准後，方得進入 V1 implementation。

```
□ Gate A locked（Q-A1, Q-A2, Q-A3a, Q-A3b, Q-A4, Q-A5 dispositioned）
□ Gate B locked（B1–B6 invariants 經審核，無未解缺陷）
□ Gate C locked（Q-C1, Q-C2 dispositioned）
□ Gate D contract locked（transition table、telemetry schema、
  SLO measurement boundaries 核定；Q-D1/Q-D2 得 DEFERRED_TO_V2）
□ Acceptance matrix complete（§9，每列含 verification type 與 evidence artifact）
□ Open Decisions closed or explicitly deferred（§10 Ledger 已更新）
□ Canonical hash generated
□ Lock commit recorded
□ Working tree clean
□ SPEC_LOCKED approved by Lock Authority
```

---

## 12. Lifecycle

```
Current document (v0.1.1 DRAFT)
    ↓ canonical review / lock-blocking dispositions
Canonical hash + lock commit
    ↓
SPEC_LOCKED
    ↓
Implementation authorisation（僅 V1；V2 另受 Gate D entry 約束）
```

版本遞增為治理流程之副產品；canonical identity 依 Section 0 之 Lock Identity Invariant 判定，MUST NOT 以版本號單獨識別。

*— End of SPEC —*
