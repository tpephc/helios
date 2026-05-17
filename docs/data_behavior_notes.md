# 台股資料行為觀察筆記

> **用途**：累積實際運行 Helios 過程中觀察到的台股資料 quirks、pattern、反直覺事實。
> 這個檔案是 **Step 3 (features/technical) 與 Step 5 (risk) 設計的需求依據**。
> 每次跑完 `data_quality_report.py` 或在 notebook 看到有意思的 pattern，整理到這裡。
>
> **不放**：實作細節、設計決策、code review（那些在 CHANGELOG / docs/）。
> **要放**：「我發現台股資料 X 有 Y 行為」這類觀察。

---

## 格式建議

每個 entry 用以下結構：

```
### YYYY-MM-DD — <一句話標題>

**觀察**：看到什麼具體現象（最好附資料 / 圖）
**影響**：對哪些後續模組會有影響
**處置**：要怎麼設計來吸收這個現象
**追蹤**：(可選) 開放問題
```

---

## 觀察清單 (待累積)

### YYYY-MM-DD — TEMPLATE: 除權息日的價格 gap

**觀察**：(範例) 0056 每年 X 月有 N 次單日 -8% 至 -15% 跳空，常出現在月底。
這些不是真實虧損，是除權息（FinMind 預設沒做 adjustment）。

**影響**：
- RSI / Bollinger / MACD 會被觸發假訊號
- ATR 計算會被異常 inflated
- regime detection 可能誤判為 bear

**處置**：
- Step 3 indicators 計算前必須先做 dividend adjustment
- 或：在 features layer 加 `is_ex_dividend_day` flag，讓策略可以選擇性忽略
- 或：FinMind 的 `TaiwanStockPriceAdj` dataset 直接拿調整後價格

**追蹤**：
- 哪個方案 trade-off 最好？前者保留原始資料但增加 features 工作；
  後者乾淨但失去原始 close 的可追溯性。

---

### YYYY-MM-DD — TEMPLATE: 漲跌停的群聚

**觀察**：(範例) 某些中型股在 X 事件後連續多日漲跌停，
表面看 |daily return| = 9.99% 但實際是限制下的「被截斷波動」。

**影響**：
- ATR 嚴重低估真實波動
- 過去 N 天 high-low range 被壓縮
- 流動性實際上是斷裂的（無法成交，但價格在動）

**處置**：
- 規則：連 3 天以上 |return| 接近 9.5% 的 symbol 在 strategy 評分扣分
- 或：直接 exclude from universe 直到 cool-down 期過後

---

(在下面繼續累積真實觀察…)

---

## 2026-05-16 (更新) — v0.1.7 raw baseline 確立

### 7. FinMind 免費版邊界發現

**觀察**：`TaiwanStockPriceAdj`（還原權息）回 `{"msg":"Your level is register. Please update your user level.", "status":400}`。
免費 token (`register` tier) 只能用 raw 價格 dataset (`TaiwanStockPrice`)。

**處置**（這個發現逼出更好的架構）：
- 不要把 adjustment ownership 外包給 FinMind 黑盒
- features layer 自己用 TWSE TWTB4U + STOCK_DAY 註記算 adjustment
- 副作用：我們的 raw 跟 TWSE 的 raw 一致，cross-validation 更乾淨

---

### 8. Sanity filter 在真實資料找到的第一個壞列

**觀察**：2317 鴻海 2025-07-30 FinMind 回 close=0 / open=0。Sanity 自動丟，2317 從 1215 降到 1214 rows，quality_log 寫滿 audit。

**影響**：證明資料層的衛生檢查設計是必要的，不是 over-engineering。下一檔 zero-close 自動處理，不用我們手動發現。

---

### 9. 確認的真實公司行動 (v0.1.9 adjustment layer 必要 test cases)

跑 5 年資料抓到這些「應該被 adjustment 吸收」的事件：

| Symbol | Date       | Type     | Raw pct |
|--------|------------|----------|---------|
| 0050   | 2025-06-18 | 1拆4     | -74.78% |
| 2303   | 2022-06-22 | 除權息   | -10.55% |
| 2454   | 2022-06-23 | 除權息   | -14.62% |
| 2454   | 2023-06-20 | 除權息   | -11.97% |
| 3711   | 2022-06-29 | 除權息   | -13.08% |

**v0.1.9 features/dividend_adjustment.py 跑完之後**，這些日期的 pct_change 應該都在 ±3% 以內（吸收掉除權息的 mechanical drop，留下真實的市場波動）。
這是 unit test 的 golden cases。

---

### 10. 半導體個股的接近漲跌停頻率（真實市場行為）

| Symbol | 5 年 |return| ≥ 9.5% 次數 |
|--------|---------------------------|
| 2303 聯電    | 11 |
| 2454 聯發科  | 11 |
| 3711 日月光  | 11 |
| 2308 台達電  | 6  |
| 2317 鴻海    | 5  |
| 2330 台積電  | 3  |

**對照 ETF**：0050 / 0056 / 006208 / 00878 都只有 2-3 次 → ETF 因為持股分散，極端波動被稀釋。

**含義**：對半導體個股做 ATR-based stop-loss 或 position sizing，要把「漲跌停截斷」的效應算進去，不能直接用 H-L range。
