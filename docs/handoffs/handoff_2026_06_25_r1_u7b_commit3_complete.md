# Helios Handoff — 2026-06-25 R1-U7B Commit 3 Complete

## 全域慣例（所有後續 session 適用）

- **主要對話語言：中文**
- **所有 Python 檔案：嚴格遵循 PEP 格式**
- **DuckDB 路徑：`data/_storage/helios.duckdb`**
- **Server：`tradeagent@nexus:~/projects/helios`**

---

## Session 結束狀態（2026-06-25）

R1-U7B audit Phase 1 enumeration **LOCKED at Commit 3 of 5**。下一
session 接續 Phase 2 §D U7A evaluation。

### 已 land 的 commit

```text
cd283f3  docs(audit): R1-U7B Phase 1 enumeration freeze v0.1.1 LOCKED
         (pushed to origin/main)
```

### 5-Commit Pipeline 狀態

```text
[X] Commit 1 (63f275f, 2026-06-24): boundary spec v0.1.0 +
                                    prereg §9.1 amendment
[X] Commit 2 (531bec5, 2026-06-24): boundary spec v0.1.0 → v0.1.1
                                    scope amendment
[X] Commit 3 (cd283f3, 2026-06-25): Phase 1 enumeration LOCKED
[ ] Commit 4 (NEXT):                Phase 2 §D U7A evaluation
[ ] Commit 5:                       Phase 3 §E synthesis +
                                    R1 prereg LOCK +
                                    Commit 5 consolidation
```

---

## Commit 3 最終狀態

```text
File:                docs/research/ud_ratio_21d_r1_u7b_audit.md
Lines:               5,682
Status:              COMMIT 3 LOCK READY → LOCKED at cd283f3

Phase 1 totals:
  Seed scope:        96 files
  §A.2.1 lineage:     4 (audit infrastructure + Track-C Step 1)
  §A.2.4 method:     26 (1:1 with entries)
  §A.3 INCLUDED:     19 unique files → 41 rows (36 finding clusters)
  §A.4 EXCLUDED:     47 unique files = 47 rows (1:1)

  Partition:         4 + 26 + 19 + 47 = 96  ✓
  Coverage:          92 / 92 = 100%
  Disjointness:      all 6 cross-partition intersections ∅  ✓

§B orphan scan:
  Inventory:         22 research/ + 66 scripts/ + 2 tests/research/
  §B.3 appendix:      1 (replay_engine.py, script-level closed-study)
  §B.4 excluded:      3 (mae_atr_study, open_gap_study,
                        p1_data_contamination_audit)
  Coverage:          90 / 90 = 100%
```

### Lock review verified (audit-internal + git metadata)

```text
[✓]  CHECK 1: Schema consistency
       §A.3 (41 rows), §A.4 (47 rows), §A.2.4 (26 entries)
       全部 schema 完整、numbering 連續
[✓]  CHECK 2: Arithmetic invariants
       Partition 4 + 26 + 19 + 47 = 96, all 6 intersections ∅
[✓]  CHECK 3: Git metadata
       108 commit_sha 全 7-hex, 82 commit_date 全 ISO,
       37 unique SHAs all exist in repo (verified)
```

---

## Protocol Freeze 維持狀態

```text
§A.0 contains 15 locked rules + Protocol Freeze closure
新增規則總數 (Batch 5 / 6a / 6b / Fix A / §A.5 / §B):  0
新增 retrospective notes (under A.0.R Non-Binding):     2
```

兩段 retrospective notes 已視覺分層至 `A.0.R Design Rationale —
Non-Binding`，與 binding protocol 物理混合但語意明確分離。

---

## Next Session 接續腳本（嚴格順序，不要跳）

### Step 1：環境驗證

```bash
cd ~/projects/helios

# 確認 commit 3 仍在 main HEAD
git log --oneline -5
# 預期: cd283f3 ... R1-U7B Phase 1 enumeration freeze v0.1.1 LOCKED

# 確認 audit 文件大小
wc -l docs/research/ud_ratio_21d_r1_u7b_audit.md
# 預期: 5682

# 確認 working tree clean
git status
# 預期: nothing to commit, working tree clean
```

### Step 2：Paste prereg §9.1 全文給 Claude

```bash
# Show the full §9.1 U7A criteria definition (locked text)
sed -n '/^## §9\.1\|^### §9\.1/,/^## §9\.2\|^## §10\|^## §11/p' \
  docs/research/ud_ratio_21d_r1_prereg.md
```

把整段 paste 到對話內。**不要靠記憶或推測 U7A criteria**。Phase 2
所有判斷必須以 locked prereg 文字為單一權威。

### Step 3：Confirm Phase 2 schema

Claude 會基於 §9.1 文字 derive §D schema。預期 schema 結構：

```text
| anchor_candidate_id   |
| source_row            | Row N (§A.3 reference, primary only)
| canonical_artifact    | source_file
| finding_cluster_label |
| C1_<name>             | PASS / FAIL + reasoning
| C2_<name>             | PASS / FAIL + reasoning
| ...
| u7a_verdict           | ADMIT (all PASS) / REJECT (any FAIL)
| spearman_eligible     | YES / NO
```

具體 Cn 對應到 §9.1 哪 5 criteria 由 prereg locked 文字決定，**不
要由 Claude 自行命名**。

### Step 4：Aggregator handling 規則（已在前 session 鎖定）

```text
§A.3 secondary aggregators (5 個) 不應作為 U7A anchor candidates。
標 NOT_ANCHOR_AGGREGATOR 跳過，除非 prereg §9.1 明文允許 aggregator
參與 U7A。

Phase 2 anchor universe = 36 unique finding clusters / primary
sources, NOT 41 raw §A.3 rows.

5 個 aggregator rows 待 Step 3 後從 §A.3 抽出列名單。
```

### Step 5：Phase 2 Batch 切法（建議，可調整）

```text
D1: Rows 1-3   (phase0_findings 3 clusters)
D2: Rows 4-8   (R8 Phase 0 + research_handoff_2026_05 R1/R2/R5/Study B)
D3: Aggregator skip pass (Row 9, Row 33, + 3 others TBD)
D4: Rows 10-12 (R8 Phase 1 A-1/A-2/A-3 ← critical anchors)
D5: Rows 13-14 (R8 Phase 2A/2B)
D6: Rows 15-21 (R8 Phase 3/4)
D7: Rows 22-28 (R8 Phase 5/6)
D8: Rows 29-32 (P1-DATA chain + remediation closeout)
D9: Rows 34-41 (JOURNAL + RESEARCH_JOURNAL clusters)
```

每個 Batch 結束時觸發 reviewer review，避免 evaluation fatigue
影響 5/5 judgment quality。

### Step 6：絕對禁止項

```text
[X] LOCK 前不要跑任何 Spearman query (per prereg §9.1 amendment)
[X] LOCK 前不要修改 §A.0 / §A.1 / §A.3 / §A.4 任何分類或編號
[X] 不要把 aggregator rows 當 U7A anchor candidates
[X] 不要靠記憶推測 U7A criteria — 必須以 prereg §9.1 locked 文字為準
[X] 不要 unilaterally classify; 每個 Cn PASS/FAIL 都需要 reviewer
    confirmation
```

---

## Phase 1 Pending Items (carry to Commit 4 / 5)

### Prereg LOCK 前剩餘決策（per audit Status block）

```text
[ ] N_MIN_CROSS_SECTION   working value: 20 (待 lock 確認)
[ ] N_MIN_REGIME_DATES    working value: 30 (待 lock 確認)
[ ] R1-U7B anchors        待 Phase 2 U7A 結果填入
```

這三項都是 R1 prereg LOCK 的 binding TBD，**不應在 Commit 4 處理，
應留到 Commit 5 R1 prereg LOCK 一併處理**。

### Commit 5 Consolidation Target (audit-template-level)

兩段 retrospective notes 已記錄在 audit §A.0.R 中，明示為 Commit 5
consolidation input：

```text
1. Three-phase model: Phase 1A Document Identity → Phase 1B
   Evidence Extraction → Phase 1C Anchor Resolution

2. Operative question reframe:
   NOT "what kind of document is this?"
   BUT "which document owns this finding for governance purposes?"

3. Commit 5 §A.0 consolidation target structure:
     Core Principle 1: Identity
     Core Principle 2: Evidence Ownership
     Core Principle 3: Governance Lifecycle
   剩餘 12 條 §A.0 rules 大部分降級為:
     Appendix A: Operational Notes
     Appendix B: Examples
     Appendix C: Reviewer Guidance
```

這個 consolidation **不在 Commit 4 範圍內**。Commit 4 純粹做 §D U7A
evaluation，protocol structure 不動。

---

## 重要 conceptual deliverable (durable beyond R1-U7B)

```text
Governance ownership ≠ importance.

A document can be very important (roadmap, journal, handoff)
without being the canonical governance owner for any finding.
Canonical owner = the document that locks the finding for
governance purposes.

In R1-U7B: roadmap.md is important but its findings' canonical
owners are phase0_findings.md / interim_findings.md; handoffs
are important for continuity but never canonical owners.

This makes Phase 2 / U7A evaluation clean:
  U7A operates on canonical owners only, not on every document
  that mentions a finding.

This principle applies to any future research lineage audit, not
just R1-U7B.
```

---

## 環境狀態

```text
Helios server:           tradeagent@nexus
Helios repo:             ~/projects/helios
Main branch HEAD:        cd283f3
audit.md:                docs/research/ud_ratio_21d_r1_u7b_audit.md
                         (5,682 lines, committed at cd283f3)
prereg:                  docs/research/ud_ratio_21d_r1_prereg.md
                         (DRAFT, NOT LOCKED, awaits Commit 5)
boundary spec:           docs/research/ud_ratio_21d_r1_u7b_enumeration_boundary.md
                         v0.1.1 LOCKED at 531bec5

Working machine:         Windows Terminal
Local download path:     C:\Users\tpephc\Downloads
Workflow:                edit on Claude sandbox → scp to nexus →
                         git add + commit on nexus
```

---

## Next Session First Message Template

```text
延續 R1-U7B audit pipeline。Commit 3 (cd283f3) 已 LOCKED Phase 1
enumeration。現在開始 Commit 4: Phase 2 §D U7A evaluation。

prereg §9.1 全文如下（從 nexus 直接 cat 出來）：

[paste sed -n '/...' command output here]

請依以下順序開始：
  1. Confirm U7A criteria 5 個是否全部都在這段內
  2. Derive §D schema from locked text
  3. 列出 5 個 §A.3 secondary aggregator rows，全部標
     NOT_ANCHOR_AGGREGATOR
  4. 開始 Batch D1: Rows 1-3
```

---

## Status Invariant

```text
Phase 1 enumeration:  LOCKED at cd283f3
Phase 2 evaluation:   NOT STARTED
Phase 3 synthesis:    NOT STARTED
R1 prereg:            DRAFT, NOT LOCKED
Protocol Freeze:      EFFECTIVE through Commit 4
```
