# Helios 資料來源總覽

<!-- docs/data_sources.md -->
<!-- 建立：2026-06-07 | 維護：每次新增/變更資料來源時更新 -->

## 概述

本文件記錄 Helios 系統所有資料來源的現況、覆蓋範圍、已知限制與維護事項。
分為三類：**生產用途**（daily_run / execution path）、**研究用途**（backtests / Phase 1）、**行事曆基礎設施**。

---

## 1. 市場行情資料

### 1.1 Shioaji（永豐 API）— 生產主要來源

| 項目 | 內容 |
|---|---|
| 用途 | 日線行情（daily_quotes pipeline）、盤中報價（intraday_monitor） |
| 寫入表 | `daily_price`、`daily_price_adj`（via build_adjusted_prices） |
| 覆蓋範圍 | TWSE 上市股票；universe top-200 by market cap |
| 流量 | ~2 MB/day（vs FinMind ~21–61 MB） |
| Cron | `daily_run.py` 16:00 Taipei |
| 已知限制 | 不提供權證 strike_price/expiry_date/exercise_ratio（warrant screener 延後至 v0.3.0） |
| 相關模組 | `data/sources/shioaji_client.py`、`scripts/shioaji_download_daily.py` |
| 憑證 | 生產 API key（環境變數） |

### 1.2 FinMind — 備援 / 歷史補抓

| 項目 | 內容 |
|---|---|
| 用途 | 歷史資料補抓、dividend/split 來源（`ingest_dividends.py`） |
| 寫入表 | `corporate_actions`（dividend_result 類型） |
| 覆蓋範圍 | TWSE 上市股票；dynamic_top200 universe |
| 已知限制 | 流量較大；不作為生產日線主要來源 |
| 相關模組 | `data/sources/finmind_client.py`、`scripts/ingest_dividends.py` |

### 1.3 YFinance — 已棄用

| 項目 | 內容 |
|---|---|
| 狀態 | **DEPRECATED**（v0.1.14 後由 Shioaji 取代） |
| 殘留 | `data/sources/yfinance_client.py` 仍存在（待清理） |
| 注意 | 任何新程式碼不應引用 yfinance |

---

## 2. 指數 / 大盤資料

### 2.1 TAIEX（大盤指數）

| 項目 | 內容 |
|---|---|
| 用途 | 交易日曆 fallback（v0.1.x）、RS 計算基準 |
| 寫入表 | `daily_price`（stock_id = 'TAIEX'） |
| 來源 | Shioaji |
| 注意 | v0.2.0 起 `is_trading_day()` 改用 exchange_calendars XTAI，不再依賴 TAIEX row 存在性 |

### 2.2 產業指數

| 項目 | 內容 |
|---|---|
| 用途 | 產業輪動分析 |
| 寫入表 | `sector_index_daily` |
| 來源 | Shioaji |

---

## 3. 企業基本資料

### 3.1 公司資訊

| 項目 | 內容 |
|---|---|
| 用途 | 股票名稱、產業分類、市值 |
| 寫入表 | `company_metadata`、`stock_info` |
| 來源 | Shioaji（`sync_company_info.py`） |
| 已知限制 | `stock_info` population pipeline 尚不完整（IF-2 → P2） |

### 3.2 法人買賣超

| 項目 | 內容 |
|---|---|
| 用途 | 機構投資人動向特徵 |
| 寫入表 | `institutional_investors` |
| 來源 | TWSE OpenAPI / FinMind |

### 3.3 月營收

| 項目 | 內容 |
|---|---|
| 用途 | 基本面特徵 |
| 寫入表 | `monthly_revenue`（目前 row count = 0，無 ingestion script） |
| 狀態 | **P2-DATA — OPEN** |

**來源評估（2026-06-07）：**

| 來源 | 歷史深度 | 筆數/次 | 適用場景 |
|---|---|---|---|
| TWSE OpenAPI `/opendata/t187ap05_P` | **當月 only**（302 筆，單月全市場） | 302 | 每月增量 append |
| FinMind | 多年歷史 | 可按股票查詢 | 歷史補抓（一次性） |

**建議架構：雙來源策略**
- 歷史補抓：FinMind → `monthly_revenue`（一次性）
- 每月增量：TWSE OpenAPI → `monthly_revenue`（月底 cron append）

**注意：**
- TWSE API 日期格式為民國年（例：11504 = 民國 115 年 4 月 = 2026-04）
- API 無 parameters，每次回傳當月全市場；無法指定歷史月份
- 現有 `monthly_revenue` schema 有 `revenue_yoy` 欄位，TWSE API 有 YoY% 可直接對應
- 目前無任何 research pipeline 依賴此表，非緊急

---

## 4. 公司行動（Corporate Actions）

### 4.1 Dividend / Split — 已完成

| 項目 | 內容 |
|---|---|
| 狀態 | **ACTIVE** |
| 寫入表 | `corporate_actions`（kind: 息/權息/權/split 等） |
| 來源 | FinMind `dividend_result` API |
| 覆蓋範圍 | dynamic_top200 universe；199 distinct symbols；1,106 rows |
| 相關 commit | `76f1f45`（IF-3A CLOSED） |
| 相關模組 | `scripts/ingest_dividends.py` |

### 4.2 Suspension / Halt / Resumption — 待建

| 項目 | 內容 |
|---|---|
| 狀態 | **P2 — OPEN**（IF-3B） |
| 現況 | `corporate_actions` 無 suspend/halt/resume 類型記錄 |
| Source candidates | MOPS 公開資訊觀測站、TWSE OpenAPI（endpoint 尚待確認） |
| 已知限制 | r8_events population 中 confirmed halt-resumption = 0；目前 non-binding |
| 參考文件 | `research/if3b_source_discovery_spec.md` v0.1.1 |

### 4.3 資本減資（Capital Reduction）

| 項目 | 內容 |
|---|---|
| 狀態 | 已知存在，尚未系統性 ingest |
| 已知案例 | 2327（DQ-ADJ-003，已分類） |
| 注意 | 與 dividend ingestion 不同 pipeline，需獨立處理 |

---

## 5. 交易日曆

### 5.1 exchange_calendars XTAI — Layer 2

| 項目 | 內容 |
|---|---|
| 狀態 | **ACTIVE**（v0.2.0） |
| 覆蓋範圍 | 2006-06-07 → 2027-06-07（含颱風假、補班日、農曆春節） |
| 安裝 | `.venv` 內 `exchange_calendars` 套件 |
| 注意 | 套件升版後需確認 `last_session` 是否延伸；`TW_HOLIDAYS_FALLBACK` 可相應縮減 |

### 5.2 TWSE OpenAPI `/holidaySchedule` — Layer 1

| 項目 | 內容 |
|---|---|
| 狀態 | **ACTIVE**（v0.2.0） |
| 覆蓋範圍 | 當年度（API 不支援歷史年份查詢） |
| 寫入表 | `twse_holidays`（24 筆/年；3 筆交易日通知已過濾） |
| 日期格式 | 民國年 YYYMMDD（例：1150101 = 2026-01-01） |
| 年度維護 | 每年初執行 `uv run python scripts/ingest_twse_holidays.py` |
| 相關模組 | `scripts/ingest_twse_holidays.py`、`scripts/migrate_add_twse_holidays.py` |

### 5.3 TW_HOLIDAYS_FALLBACK — Layer 3

| 項目 | 內容 |
|---|---|
| 狀態 | **ACTIVE**（縮減版，僅覆蓋 XTAI last_session 之後） |
| 覆蓋範圍 | 2027-06-08 之後（估算值，非官方公告） |
| 維護 | 每年 review；等 exchange_calendars 升版後更新起始日期 |
| 位置 | `market/trading_calendar.py` `TW_HOLIDAYS_FALLBACK` |

---

## 6. 證券生命週期

### 6.1 Security Lifecycle

| 項目 | 內容 |
|---|---|
| 狀態 | **ACTIVE** |
| 寫入表 | `security_lifecycle`（PIT schema：stock_id, listed_from, listed_to, market） |
| 來源 | MOPS 手動驗證 seed（18 stocks，36 rows） |
| Canonical tool | `scripts/seed_security_lifecycle.py` |
| 廢棄 tool | `scripts/ingest_security_lifecycle.py`（**RETIRED**，tombstone） |
| 用途 | IF-1 remediation；`listed_market_daily_price_adj` 過濾基礎 |

---

## 7. 研究用途特殊來源

### 7.1 R8 Phase 1 Research Panel

| 項目 | 內容 |
|---|---|
| 主要表 | `listed_market_daily_price_adj`（IF-1 clean panel，236,713 rows） |
| 過濾邏輯 | security_lifecycle JOIN；排除 emerging board 掛牌前資料 |
| 特徵表 | `bullish_features`、`bearish_features`、`daily_features` |
| 注意 | `daily_price_adj`（244,044 rows）含 IF-1 污染，研究不應直接使用 |

---

## 8. 外部 API 限制摘要

| API | 歷史深度 | 速率限制 | 已知限制 |
|---|---|---|---|
| Shioaji | 視合約 | 生產 key | 不提供權證衍生品欄位 |
| FinMind | 深度較佳 | 有請求限制 | 流量大 |
| TWSE OpenAPI `/holidaySchedule` | **當年度 only** | 無認證 | year 參數無效 |
| exchange_calendars XTAI | 2006-06-07 起 | N/A（本地套件） | last_session = 2027-06-07（需隨套件升版） |
| MOPS | 待評估 | 未知 | IF-3B source candidate |

---

## 維護 Checklist

### 年度（每年1月）
- [ ] `uv run python scripts/ingest_twse_holidays.py` — 更新當年度假日
- [ ] 確認 `exchange_calendars` XTAI `last_session`，更新 `TW_HOLIDAYS_FALLBACK`
- [ ] 確認 `TW_HOLIDAYS_FALLBACK` 內估算假日與 TWSE 官方公告一致

### 每次 universe 變更後
- [ ] 確認 `ingest_dividends.py` universe resolver 能覆蓋新 symbols
- [ ] 確認 `security_lifecycle` 有對應記錄

### 每次新增資料來源時
- [ ] 更新本文件
- [ ] 新增對應 ingestion script
- [ ] 新增 data quality test

---

*Last updated: 2026-06-07*
*Maintainer: 每次新增/變更資料來源時更新*
