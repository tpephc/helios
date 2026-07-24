# TS-SPEC-P0 v0.1.1 — Lock Record（Sidecar）

> 本文件為 TS-SPEC-P0 v0.1.1 之外部封存紀錄。Locked SPEC 本體於 LOCK 後不再變更；
> Lock Commit SHA 與 Checklist 完成狀態記錄於此，不回填至 locked file，
> 以維持 canonical hash 之五元組完整性。

## Canonical Identity

| 欄位 | 值 |
|---|---|
| Document ID | TS-SPEC-P0 |
| Version | v0.1.1 |
| Canonical Path | docs/research/technical_screening_phase0_spec.md |
| Repository | git@github.com:tpephc/helios.git |
| Canonical Hash (SHA-256) | 7eeb8da448deb1d734ebbff7a70a496b5eec00bd419f582227fa96ff565a4b25 |
| Hash Convention | 以文件完整內容計算，惟文件內 Canonical Hash 欄位之 64 位十六進位值於計算前置換為 64 個 '0' |
| Lock Commit SHA | PENDING — 待回填 |
| Locked At | 2026-07-23 |

## Dispositions

| Disposition | Scope | Status |
|---|---|---|
| D-TSP0-A1 | Gate A（Q-A1, Q-A2, Q-A3a, Q-A3b, Q-A4, Q-A5） | LOCKED |
| D-TSP0-C1 | Gate C（Q-C1, Q-C2） | LOCKED |
| Q-D1, Q-D2 | Gate D（telemetry sink、SLO 閾值） | DEFERRED_TO_V2 |

## Lock Authority Approval

> LOCK APPROVED. TS-SPEC-P0 v0.1.1 is authorised to transition from
> DRAFT — PRE-LOCK to SPEC_LOCKED. V1 implementation is authorised.
> V2 remains subject to the Gate D entry requirements and deferred
> dispositions (Q-D1, Q-D2).

## Implementation Readiness Checklist（完成狀態）

```
[x] Gate A locked（D-TSP0-A1）
[x] Gate B locked（B1–B6 invariants 經審核，無未解缺陷）
[x] Gate C locked（D-TSP0-C1）
[x] Gate D contract locked（Q-D1/Q-D2 DEFERRED_TO_V2）
[x] Acceptance matrix complete（§9）
[x] Open Decisions closed or explicitly deferred（§10 Ledger）
[x] Canonical hash generated（見上）
[ ] Lock commit recorded（待回填）
[ ] Working tree clean（commit 時驗證）
[x] SPEC_LOCKED approved by Lock Authority
```

## 封存操作程序

```bash
# 1. 將 locked SPEC 逐字複製至 repo（不得經編輯器重存）
cp technical_screening_phase0_spec.md ~/projects/helios/docs/research/

# 2. 複製本 sidecar（建議同目錄）
cp TS-SPEC-P0_v0.1.1_lock_record.md ~/projects/helios/docs/research/

# 3. Commit
cd ~/projects/helios
git add docs/research/technical_screening_phase0_spec.md \
        docs/research/TS-SPEC-P0_v0.1.1_lock_record.md
git commit -m "docs(spec): lock TS-SPEC-P0 v0.1.1"
git rev-parse HEAD

# 4. 驗證 hash 一致性（歸零重算，應輸出 7eeb8da4...）
python3 - <<'PY'
import re, hashlib
s = open('docs/research/technical_screening_phase0_spec.md').read()
s = re.sub(r"(Canonical Hash \(SHA-256\):\n)    [0-9a-f]{64}",
           r"\g<1>    " + "0"*64, s)
print(hashlib.sha256(s.encode()).hexdigest())
PY

# 5. 將 commit SHA 回填本 sidecar 之 Lock Commit SHA 欄位，
#    並將 Checklist 最後兩項勾選（第二次 commit 或工作紀錄均可）
```

## 注意事項

- Locked SPEC 本體於 LOCK 後 MUST NOT 修改；任何 normative 變更依 Post-Lock Change Policy 產生新版本。
- 本 sidecar 得更新（Lock Commit SHA 回填、Checklist 勾選），不影響 canonical hash。
