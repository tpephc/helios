# Versioning 規範

> Helios 採用語意化版號 + 雙層版本紀錄

## 路徑註解規範 (v0.1.2 起)

每個 code/config 檔案的**第一行**必須是相對於專案根的路徑註解：

### Python

```python
# storage/signals.py
"""模組描述...

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""
```

### YAML

```yaml
# config/risk_limits.yaml
# Version: v0.1.0 (2026-05-16)
# Changelog:
#   v0.1.0 (2026-05-16): Initial implementation
```

### .env.example / pyproject.toml

```bash
# .env.example
ENV=dev
...
```

**適用範圍**：.py、.yaml、.toml、.env.example  
**不適用**：.md（自身會被閱讀）、.gitignore

**理由**：檔案被複製、貼上 PR diff、單獨 share 時立即看得出歸屬。

## 三個版號層級

| 層級 | 位置 | 用途 |
|---|---|---|
| 專案版 | `pyproject.toml::project.version` | 整體 MVP 進度 (v0.1, v0.2, ...) |
| 專案 changelog | `CHANGELOG.md` | 跨檔案的事件 (Step 完成、review 採納、breaking change) |
| 檔案版 | 每個檔案 docstring 內 | 該檔案的細節歷史 |

## 版號規則

`vX.Y.Z` 採用 SemVer 寬鬆變體：

- `X` (major)：架構性大改、breaking change、API 不相容
- `Y` (minor)：新功能、新模組
- `Z` (patch)：bug fix、refactor、小調整、文件改動

當前專案版：`v0.1.x` (v0.1 MVP 開發中)

## 檔案版號格式

### Python 檔

```python
"""模組描述...

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): 改了什麼，盡量具體
  v0.1.0 (2026-05-16): Initial implementation
"""
```

### YAML 檔

```yaml
# Module: <名稱>
# Version: v0.1.1 (2026-05-16)
# Changelog:
#   v0.1.1 (2026-05-16): 改了什麼
#   v0.1.0 (2026-05-16): Initial implementation
```

### Markdown 檔

文件頂端加：

```markdown
> Version: v0.1.1 (2026-05-16) — [Latest change description]
```

## Bump 規則

| 動作 | 結果 |
|---|---|
| 新增檔案 | 開頭 v0.1.0 |
| 修 bug / 小調整 | patch +1 (v0.1.0 → v0.1.1) |
| 新增函數 / 欄位 / 大幅 refactor | minor +1 (v0.1.1 → v0.2.0) — **只有專案 minor bump 時**才用 |
| Breaking change | major +1 — **跨 MVP 階段時用** (v0.x → v1.0) |

實務上：MVP 階段 99% 的檔案改動都是 patch。

## Changelog 保留條目數

- 檔案內 changelog 至少保留**最近 5 條**
- 超過 5 條後可下沉到 git commit history
- 重大改動 (review 採納、架構轉折) 一律寫進 `CHANGELOG.md` 不丟

## 提交流程 (建議)

修改一個檔案時：

1. 改 code / config
2. Bump 檔案 docstring 內版號 (patch +1)
3. 在該 changelog 加一行說明本次改動
4. 若是跨多個檔案的同一次改動 → 同時更新 `CHANGELOG.md` [Unreleased] 段
5. Commit 時 message 與 changelog 描述一致

## 範例：一個檔案的演化

```python
# 初版
"""ATR-based position sizing.

Version: v0.1.0 (2026-05-16)
Changelog:
  v0.1.0 (2026-05-16): Initial implementation
"""

# 加了一個參數
"""ATR-based position sizing.

Version: v0.1.1 (2026-05-17)
Changelog:
  v0.1.1 (2026-05-17): Added min_position_twd parameter
  v0.1.0 (2026-05-16): Initial implementation
"""

# 改了演算法
"""ATR-based position sizing.

Version: v0.1.2 (2026-05-18)
Changelog:
  v0.1.2 (2026-05-18): Switched from fixed ATR multiplier to volatility-targeting
  v0.1.1 (2026-05-17): Added min_position_twd parameter
  v0.1.0 (2026-05-16): Initial implementation
"""
```
