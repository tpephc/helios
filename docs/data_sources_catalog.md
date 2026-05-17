# Helios 資料源 Catalog

> 這份是 Helios 所有 data source 決策的**權威參考**。
> 來源：外部 quant review (2026-05-16) + 4 個 TWSE endpoint 親自驗證 + FinMind 實戰經驗。
> 任何 data 層的新增 / 修改，先對齊這份再動工。

---

## 1. 架構原則：4 個角色

不是「一個主源、其他備援」，而是**四種角色並存**：

```
┌─────────────────┬────────────────────────────────────────────┐
│ Role            │ Definition                                 │
├─────────────────┼────────────────────────────────────────────┤
│ primary         │ 系統日常 ingest 的源                       │
│ secondary truth │ 權威驗證源 (官方資料，慢但準)              │
│ cross-validation│ 獨立檢查源 (跟 primary 不同 lineage)       │
│ fallback        │ primary 失敗時的備胎                       │
└─────────────────┴────────────────────────────────────────────┘
```

**這四個角色可以是同一個 source 在不同 dataset 扮演不同角色。**

---

## 2. 三家 Source 的角色分配 (per dataset) — v0.1.7 hotfix 後修正

**關鍵發現 (2026-05-16)**：FinMind 免費版 (`register` tier) **不開放 `TaiwanStockPriceAdj`** (還原權息)，必須付費升級 Sponsor。
這個限制反而推動了更好的架構決策：**adjustment ownership 應該在 features layer，由我們自己用 TWSE TWTB4U + STOCK_DAY 註記算**，不外包給 FinMind 黑盒。

### 修正後角色分工

| Dataset                    | primary       | secondary truth | cross-val | fallback   |
|----------------------------|---------------|-----------------|-----------|------------|
| daily_price (5 年歷史 bulk) | **FinMind raw** | —             | yfinance  | TWSE 月 query |
| daily_price (T-1 增量)     | **TWSE STOCK_DAY_ALL** | FinMind raw | —    | yfinance   |
| daily_price (adjustment)    | **features/dividend_adjustment.py 自己算** | TWSE TWTB4U + STOCK_DAY 註記為輸入 | yfinance Adj Close | — |
| TAIEX                      | FinMind       | TWSE MI_5MINS_HIST | yfinance ^TWII | yfinance |
| 產業類股指數                | **TWSE MI_INDEX** | —          | —         | —          |
| 上市公司清單 / 產業分類      | **TWSE t187ap03_L** | —        | FinMind stock_info | —  |
| 除權息日 + 配息預告         | **TWSE TWTB4U** | —             | FinMind   | —          |
| 三大法人 (個股)             | **TWSE T86**  | FinMind T86     | —         | —          |
| 融資融券 (個股)             | **TWSE MI_MARGN_ALL** | FinMind | —         | —          |
| 月營收                      | **TWSE t187ap05_L** | FinMind   | —         | —          |
| 漲跌停統計 (大盤)           | **TWSE BFI84U** | —             | —         | —          |
| 暫停交易 / 即將上市          | **TWSE suspendListing / newlisting** | — | — | —      |
| 國際 reference (美股/利率/匯率) | **FinMind** | —             | —         | —          |

### 關鍵原則（更新版）

- **FinMind 從「主力日常 source」降級為「歷史 bulk 工具 + 國際 reference」**
  - 5 年 backfill 還是 FinMind 最快 (18.9 秒抓 16 symbols × 5 年實測)
  - 國際資料 (macro features) 短期內只有 FinMind 有
- **TWSE 升為「daily ops primary」**：免費、不吃 FinMind 限速、STOCK_DAY_ALL 一次 1700 檔
- **產業類股 / 漲跌停 / 除權息預告 / 停牌 → TWSE 獨家**
- **adjustment 我們自己算** — TWSE TWTB4U 給除權息 + STOCK_DAY 註記給拆分，全部可解釋

### FinMind 免費版 vs 付費版 (Sponsor)

| Dataset 名                          | 免費版 | Sponsor |
|------------------------------------|-------|---------|
| TaiwanStockPrice (raw)             | ✓     | ✓       |
| TaiwanStockInfo                    | ✓     | ✓       |
| TaiwanStockInstitutionalInvestorsBuySell | ✓ | ✓     |
| TaiwanStockMonthRevenue            | ✓     | ✓       |
| TaiwanStockMarginPurchaseShortSale | ✓     | ✓       |
| **TaiwanStockPriceAdj (還原權息)** | ❌    | ✓       |
| TaiwanStockPriceTick (歷史逐筆)    | ❌    | ✓       |
| (其他付費 dataset)                  | ❌    | ✓       |

→ Helios 全程不依賴付費 dataset。

---

## 3. Endpoint Catalog（依角色排序）

### 3.1 FinMind (primary 主力)

| Dataset                       | 用途                          |
|-------------------------------|-------------------------------|
| TaiwanStockPriceAdj           | 個股還原權息 OHLCV (5 年隨意) |
| TaiwanStockPrice              | TAIEX (指數無 adjustment 需求) |
| TaiwanStockInfo               | 全市場 stock list             |
| TaiwanStockInstitutionalInvestorsBuySell | 三大法人        |
| TaiwanStockMonthRevenue       | 月營收                        |
| TaiwanStockMarginPurchaseShortSale | 融資融券                |

註：FinMind 免費版有嚴格 rate limit，需內建 token bucket。

---

### 3.2 TWSE OpenAPI (`https://openapi.twse.com.tw/v1`)

無 token，免費，rate limit 寬鬆但需自律 (建議 ≥ 1s/req)。

#### A. 個股 / 全市場 OHLCV

| Endpoint                          | 內容                  | 歷史 | Helios 用途 |
|-----------------------------------|-----------------------|------|--------------|
| `/exchangeReport/STOCK_DAY_ALL`   | 全市場 ~1700 檔當日 OHLC | 當日 | T-1 增量、cross-check FinMind |
| `/exchangeReport/STOCK_DAY_AVG_ALL` | 個股日收 + 月均價   | 當日 | VWAP-like, mean reversion (v0.2) |

#### B. 大盤 / 指數

| Endpoint                          | 內容                          | 歷史 | Helios 用途 |
|-----------------------------------|-------------------------------|------|--------------|
| `/exchangeReport/MI_INDEX`        | 50+ 指數含 30+ 產業類股       | 當日 | **sector rotation**、regime |
| `/exchangeReport/FMTQIK`          | 大盤成交量值                  | 當日 | regime strength, panic detection |
| `/indicesReport/MI_5MINS_HIST`    | TAIEX 過去 10 日 OHLC         | 滾動 | TAIEX 增量更新 |
| `/exchangeReport/BFI84U`          | 漲跌停統計                    | 當日 | mania/panic regime signal |

#### C. 法人 / 籌碼

| Endpoint                          | 內容                          | 用途 |
|-----------------------------------|-------------------------------|--------------|
| `/fund/T86`                       | 三大法人個股買賣超             | flow confirmation |
| `/fund/BFI82U`                    | 法人大盤級總計                 | regime strength |
| `/fund/MI_QFIIS`                  | 外資及陸資持股比率             | foreign positioning |
| `/exchangeReport/MI_MARGN`        | 大盤融資融券                   | sentiment, leverage |
| `/exchangeReport/MI_MARGN_ALL`    | 個股融資融券                   | retail flow |
| `/exchangeReport/TWT93U`          | 借券                          | short pressure |
| `/fund/TWT38U`                    | ETF flow                      | ETF rotation |

#### D. 公司治理 / Metadata / 公司行動

| Endpoint                          | 內容                          | 用途 |
|-----------------------------------|-------------------------------|--------------|
| `/opendata/t187ap03_L`            | 上市公司基本資訊（產業、上市日、股本） | universe management |
| `/opendata/t187ap05_L`            | 月營收                        | revenue momentum |
| `/opendata/t187ap14_L`            | 財報（ROE、debt、cashflow）   | quality filter (v0.3) |
| `/exchangeReport/TWTB4U`          | **除權息預告**                | dividend adjustment 驗證 |
| `/company/suspendListing`         | 暫停交易清單                  | **下單前安全檢查** |
| `/company/newlisting`             | 即將上市                      | universe early-warning |
| `/exchangeReport/PRICING_OPER`    | 盤後定價交易                  | 機構盤後動向 (v0.2) |
| `/exchangeReport/BWIBBU_ALL` 或 `BWIBBU_d` | P/E、殖利率、PBR     | quality filter |

### 3.3 TWSE 歷史 API (`https://www.twse.com.tw/exchangeReport`)

舊版但是真正能 query 歷史的（從 2010-01-04）。

| Endpoint                          | 內容                          | 限制 |
|-----------------------------------|-------------------------------|--------------|
| `STOCK_DAY?date=YYYYMMDD&stockNo=` | 個股某月日 K (~20 筆)        | **per-month**, 一次只回一個月 |

**重要欄位**：`註記` 欄位含 `**` 標記，表示該日為拆分/變更面額日。我們可以用這個自動建 known_corporate_actions 表。

### 3.4 yfinance (fallback)

```python
yf.Ticker("2330.TW").history(start, end)   # 個股
yf.Ticker("^TWII").history(start, end)     # TAIEX
```

- Adj Close 是 Yahoo 自己的 adjustment（跟 FinMind 不一定一致，差異本身有 audit 價值）
- 限速中等但 Yahoo 反爬偶爾擋
- 主要當 fallback 用，平時不打

### 3.5 TPEx (`https://www.tpex.org.tw/openapi/`) — 上櫃 (v0.2+)

上櫃 schema 跟上市不同（OTC ≠ TWSE）。當前 Helios universe 都在上市，**暫不納入**。中型動能股 universe 啟用時再加。

### 3.6 TAIFEX (`https://openapi.taifex.com.tw/`) — 期貨 (v0.3+)

| Endpoint                          | Helios 用途 |
|-----------------------------------|--------------|
| 台指期日 OHLC                     | overnight regime, macro risk |
| OI (未平倉)                       | trend persistence, positioning |
| Put/Call Ratio                    | sentiment extremes |

---

## 4. Parsing Quirks (踩坑清單)

### 4.1 日期格式三種

| 來源                | 格式            | 範例         | Parser |
|---------------------|-----------------|--------------|--------|
| STOCK_DAY (歷史)    | `民國/月/日`    | `114/01/02`  | `parse_roc_slashed` |
| STOCK_DAY_ALL       | `民國連月日`    | `1150508`    | `parse_roc_compact` |
| MI_5MINS_HIST       | `民國連月日`    | `1150504`    | `parse_roc_compact` |
| MI_INDEX            | `民國連月日`    | `1150410`    | `parse_roc_compact` |
| FinMind             | ISO            | `2026-05-16` | 原生 |
| yfinance            | datetime       | datetime obj | 原生 |

民國轉西元：`year + 1911`。

### 4.2 數字含千分號

```python
"45,045,125"   # 成交股數
"--"           # null
""             # 沒交易（如 +R 後墜的權證）
```

統一 parser:
```python
def parse_twse_num(s: str) -> float | None:
    if not s or s.strip() in ("--", ""):
        return None
    return float(s.replace(",", ""))
```

### 4.3 漲跌欄位

```
STOCK_DAY:  "漲跌價差": "+10.00" / "-25.00" / " 0.00"
MI_INDEX:   "漲跌": "+", "漲跌點數": "635.47"  ← 分兩欄
STOCK_DAY_ALL: "Change": "-0.7000"  ← 正負含在數字
```

統一 parser 要照 endpoint 走。

### 4.4 「註記」欄位

`STOCK_DAY.data[i][-1]` 是註記：
- `""` (空) → 正常
- `"**"` → 拆分 / 變更面額 / ETF 反分割
- 其他特殊符號 → 看 `notes[]` 解釋

### 4.5 ETF rebalance 造成的 volume anomaly

特別是 0050 換股日的 volume 會異常爆大。這不是壞資料，是真實事件。

### 4.6 OTC / TWSE schema 不一致

TPEx 跟 TWSE 是不同單位、不同 schema。當前只用 TWSE，未來加 OTC 時要做 schema mapping。

### 4.7 除權息日的 raw price gap

FinMind TaiwanStockPrice 跟 TWSE 都是 raw → 跨除權息日有 gap。
**FinMind TaiwanStockPriceAdj 跟 yfinance Adj Close 是 adjusted**，但兩者的 adjustment 演算法不一定一致 (拆分一致、配息調整有差幾 cent 可能性)。

### 4.8 Holiday gaps

trading_calendar 不會涵蓋所有台灣特殊假日（補班 / 補休 / 颱風休市）。已知 v0.1.6 → v0.1.7 改用 TAIEX baseline 解決。

### 4.9 停牌個股

`/company/suspendListing` 是停牌清單。下單前必須檢查（v0.5+ 必備）。

---

## 5. Helios Roadmap 對齊

### v0.1.7 (current) — Data Layer Hardening
- ✅ FinMind TaiwanStockPriceAdj 採用
- ✅ OHLC sanity filter
- ✅ TAIEX baseline

### v0.1.8 — TWSE Validation Layer Phase 1 (Layer A)
- `twse_client.py`:
  - `daily_all()` → STOCK_DAY_ALL
  - `indices_today()` → MI_INDEX (含產業類股 → 落 sector_index_daily 表)
  - `taiex_recent()` → MI_5MINS_HIST
  - `stock_month(sid, ym)` → STOCK_DAY (historical spot-check)
- `yfinance_client.py`:
  - `daily_price()` / `taiex()` 5 年 fallback
- `cross_source_audit.py`: 對 5 個 (symbol, date) 三源比對

### v0.1.9 — Official Truth + Universe + Safety
- `twse_client.company_info()` → t187ap03_L (上市公司 + 產業分類)
- `twse_client.dividend_forecast()` → TWTB4U (除權息預告 → 驗證 FinMind adj)
- `twse_client.suspend_listing()` → 停牌清單 (下單安全)
- Universe management 從 hardcoded 改 metadata-driven (用 t187ap03_L + 市值篩選)
- `data/known_corporate_actions` 表 ingest from TWTB4U + STOCK_DAY 註記

### v0.2.0 — 籌碼層
- T86 (三大法人個股) — FinMind 主、TWSE 驗證
- MI_MARGN_ALL (個股融資融券) — 同上
- BFI84U (漲跌停統計) — regime feature
- FMTQIK (大盤成交量) — regime feature
- TWT38U (ETF flow)
- 接到 Step 3 features 的 sentiment / flow indicators

### v0.3.0+ — TAIFEX / 財報
- 台指期 OHLC + OI + Put/Call
- t187ap14_L 財報 → quality filter
- t187ap05_L 月營收 (TWSE 版，跟 FinMind 對照)

---

## 6. 不採納 / 暫緩

- **TPEx (上櫃)**：當前 universe 都在上市，schema 不同延後
- **MIS 即時報價** (`mis.twse.com.tw/stock/api`)：盤中即時，Helios 是 EOD 系統不需要
- **盤後定價 PRICING_OPER**：v0.2 再評估

---

## 7. 「不會只有單一 source」的設計含義

quant production 系統的常見 anti-pattern：
- ❌ FinMind 一個 token 一條鏈路打到死
- ❌ 突然限速或 API 改版 → 系統停擺
- ❌ 拿到錯資料卻沒任何 cross-check → 烏龍下單

Helios 的 defense in depth：
1. **primary 跑日常** → FinMind adj
2. **secondary truth 每日 spot-check** → TWSE STOCK_DAY_ALL 抓「昨天」對比
3. **cross-validation 不定期抽樣** → yfinance 5 個隨機 (symbol, date)
4. **fallback 自動切換** → primary 失敗時走 yfinance（Layer B 才做）
5. **divergence 寫 quality_log** → 累積 audit trail，可回溯

這份 catalog 就是這個架構的「合約書」。

---

**Document Version**: v1.0 (2026-05-16)
**Last reviewed by external quant review**: 2026-05-16
