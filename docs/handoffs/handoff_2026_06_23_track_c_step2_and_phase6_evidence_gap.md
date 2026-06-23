# Helios Handoff — 2026-06-23 Track C Step 2 Pre-Registration + Phase 6 Evidence Gap

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 範圍

本 session 完成：

1. Track C Step 2 R1 pre-registration 起草並 commit (DRAFT, NOT LOCKED)
2. 5 個歷史 backlog handoffs / research docs 補錄進 git
3. tests/research/ test suite 進 git (F1' fixture boundary fix, 42 tests GREEN)
4. 1 個 RED commit (7fcfd09) 經 interactive rebase drop, 未進 origin
5. 暴露並文件化 Phase 6 closeout 的 evidence gap
6. 開啟 BACKLOG-WG1-REPRODUCIBILITY-001
7. 全部 push 到 origin/main

---

## Commits 進入 origin/main

依時間順序 (rebase 後最終 hash):

| Hash | Commit | 性質 |
|---|---|---|
| `560bfec` | Backlog: Phase 2B closeout handoff (2026-06-07) | Backlog 補錄 |
| `8ca25b0` | Backlog: R8 MA5 Momentum Phase 0 feasibility (2026-06-01 rev2) | Backlog 補錄 |
| `a583a88` | Backlog: Helios research program handoff (2026-05) | Backlog 補錄 |
| `d8a1d60` | Track C Step 2: R1 prereg draft (NOT LOCKED) | Forward-looking governance |
| `be1d23b` | Backlog: IF-3A complete handoff (2026-06-06) | Backlog 補錄 (含 path 修正) |
| `799c163` | Backlog: tests/research/ test suite (Phase 6 + adaptive sim) — F1' fixture boundary fix | Phase 6 evidence gap 補救 |

origin/main HEAD = `799c163` after push.

備註: 在 rebase 中 drop 的 RED commit `7fcfd09` 從未進 origin, 無需 revert。

---

## Track C Step 2 R1 Pre-Registration 狀態

**文件:** `docs/research/ud_ratio_21d_r1_prereg.md`
**狀態:** DRAFT — NOT LOCKED
**Spec:** `docs/features/ud_ratio_21d_spec.md` v0.1.4 (未動)

### 已 lock 的 contracts (不會再變)

```text
R1-U1   Universe Contract        R8 treatment_1 signal-date panel only
R1-U2   Observation Date         R8 signal dates only (year-stratified robustness)
R1-U3   Missing-Value Policy     pairwise exclusion, no imputation
R1-U4   Statistic Contract       per-day cross-sectional Spearman rho
R1-U5   Regime Conditioning      marginal nlu (0/1/2) + bull/bear, joint 2x3
R1-U6   Sequencing               threshold lock AFTER distribution diagnostics
R1-U7A  Comparison-set Eligibility  4-criteria rule
R1-U7C  Comparison Statistic     median per-day Spearman rho
§12     Result Inspection Order  8-step binding sequence
§13     Reproducibility Manifest  r1_run_manifest.json schema
§14     R1 Outcome Routing       30-day R2 deadline per RP-01
§15     Prohibited Actions       extended list including N_MIN tuning ban
```

### 仍未填的三項實質決策 (LOCK 前必填)

```text
N_MIN_CROSS_SECTION       (§6a, R1-U4a)
  Working value: 20
  Required: audit (cross-section size distribution on signal dates)

N_MIN_REGIME_DATES        (§7, R1-U5)
  Working value: 30
  Required: audit (regime cell date distribution)

R1-U7B historical anchors (§9.2)
  Required: U7A eligibility audit against Track-C history
  Possible outcome: single-anchor (collapse only) disclosure
                    if no orthogonal anchor meets U7A criteria
```

### 下次 session 起點

```text
1. R1-U7B eligibility audit
   - 枚舉 Track-C 歷史候選 case (從 research_handoff_2026_05.md 的
     Closed Studies 段開始,以及 r8_phase0_feasibility.md 等)
   - 逐筆對照 U7A criteria (1)-(4)
   - 不預設 audit 文件骨架,讓結構由實際歷史證據 shape
   - 產出 docs/research/ud_ratio_21d_r1_u7b_audit.md

2. 同時填入 N_MIN_CROSS_SECTION / N_MIN_REGIME_DATES 最終值
   - 不要在看完 R1 coverage 後再決定 (§15 禁止)

3. 三項填完 → 狀態改為 LOCKED → 獨立 commit
4. LOCKED 之後才能跑第一個 Spearman query
```

---

## Phase 6 Closeout Evidence Gap

### 發現

`research/r8_phase6_governance_report.md` (commit `901c0de`, 2026-06-22) 宣稱:

```text
| 3C | adaptive_release_engine + WG-1 | CLOSED | WG-1 PASS (3 tests, degenerate equivalence) |
```

但 `901c0de` commit 的 stat 顯示**沒有任何 `tests/research/*.py` 進 git**。
整個 Phase 6 Step 3 的 39+3 = 42 個測試直到今天 (commit `799c163`)
才第一次進 git, 且其中 2 個 WG-1 test 在進 git 時 RED。

### 措辭區分 (重要)

```text
WG-1 PASS evidence was NOT preserved      ← 已確認
WG-1 was invalid on 2026-06-21            ← 未證實,不能聲稱
```

兩者在 commit `799c163` message 內明確區分。**未來如何撰寫此事必須維持此區分。**

### Root cause (今天 RED 的原因)

`canonical_artifacts` fixture 內 `_load_feature_panel` 用
`valid["signal_date"].max()` 作 feature query 上界, 漏算 forward
lookup horizon (`entry_date + hard_ceiling_h - 1`)。

任何 entry 在 `signal_date.max()` 的 position 在 simulator T+1 feature
lookup 時必然 KeyError。

### 修法 (F1') applied in `799c163`

```text
last_signal_pos      = date_to_pos[valid_ledger.signal_date.max()]
last_lookup_pos      = last_signal_pos + hard_ceiling_h
required_feature_end = trading_calendar[last_lookup_pos]
```

加上 pre-load + post-load fixture invariant assertions
(diagnostic RuntimeError on violation)。

### Production 影響

```text
scripts/phase6_adaptive_engine.py: 未動 (git diff 901c0de HEAD = 0 lines)
docs/features/*:                   未動
features/*:                        未動
spec v0.1.4 (ud_ratio_21d):        未動
Phase 6 finding F-P6-01:           仍有效
ARM_B deployment baseline:         仍有效
```

---

## Backlog Items Opened

### BACKLOG-WG1-REPRODUCIBILITY-001 (在 `799c163` commit message 內記錄)

```text
canonical_artifacts is coupled to live DB state via
duckdb.connect(read_only=True). WG-1 currently verifies whatever
scenario boundary the DB's current ingest state implies — not a
stable, reproducible reference scenario.

Future work: snapshot-pin canonical_artifacts
  - 候選方案 (a): fixed parquet fixture
  - 候選方案 (b): ingest_watermark-pinned query
  - 候選方案 (c): 序列化 canonical_artifacts dict 到 disk

Out of scope for backlog commit. Should be planned as separate
Phase 6 follow-up.
```

### 未追加 backlog 但值得注意的 pattern

```text
"signal_date.max() 漏算 forward lookup horizon" 這個 bug pattern
可能存在於其他 fixture / production query。Future code review 時
可全 repo 搜尋 ["signal_date.max()", "valid[.*signal_date.*max"]
與類似模式檢視。
```

---

## Git Workflow 紀律觀察 (本 session)

### 維持的紀律

```text
✓ spec-first              (沒在缺證據時改 spec)
✓ lock-before-look        (沒在跑數字前 lock threshold)
✓ 客觀證據優先於回憶      (撤回 Q-MEMORY, 改用 .pyc mtime + git log evidence)
✓ retroactive correction  ("未保留" vs "失敗" 措辭嚴格區分)
✓ no RED commit to origin (RED commit 7fcfd09 經 rebase drop, 未 push)
✓ verifiable GREEN evidence (每個進 origin 的 commit 都有可驗證 evidence)
```

### 暴露的紀律 gap (history)

```text
Phase 6 closeout (901c0de):
  - tests/research/ 未進 git
  - governance_report.md "WG-1 PASS" 無 git-resident evidence
  - 違反 "per-phase commits must be green with no xfail,
         ABI evidence required before wiring"

修正方式: retroactive correction note (見 799c163 commit message)
未來預防: handoff 完成的同時必須 commit 所有 test artifacts
         (此原則應加入未來 closeout checklist)
```

---

## 環境狀態

```text
nexus:                    tradeagent@nexus:~/projects/helios
Branch:                   main
HEAD:                     799c163
origin/main:              799c163 (synced)
Working tree:             clean
Branches:                 main, feature/v0_1_16_v2_advisor_review
                          (feature branch 與本 session 無關, 保留)

DB last modified:         2026-06-23 16:05 (daily_run cron)
DB size:                  1.24 GB
DB tables (date max):
  daily_price             2026-06-23
  daily_features          2026-06-23
  bullish_features        2026-06-23
  bearish_features        2026-06-23
  market_regime           2026-06-23
  corporate_actions       2026-06-02  (落後 21 天, 既有 lag)
  signals                 2026-06-08  (落後 15 天, 既有 lag)
```

---

## 下次 session 啟動 checklist

```text
[ ] 確認 git status 為 working tree clean
[ ] 確認 HEAD = origin/main (no local-only commits)
[ ] Track C Step 2 工作: 開始 R1-U7B eligibility audit
    [ ] 不要直接產出 audit 文件骨架
    [ ] 從 Track-C 歷史 case 候選清單開始, 對照 U7A criteria
[ ] 同步決定 N_MIN_CROSS_SECTION 與 N_MIN_REGIME_DATES
[ ] 三項填完後, 將 R1 prereg 狀態改為 LOCKED, 獨立 commit
[ ] LOCK 前不要跑任何 Spearman query
```

---

*End of handoff.*
