#!/usr/bin/env python3
# scripts/cross_source_audit.py
"""跨來源資料一致性稽核 — FinMind vs TWSE vs yfinance。

對 N 個隨機 (symbol, date) 對比三家 raw OHLC，輸出 divergence 報告。

預期：三家 raw OHLC 應該幾乎一致（都是同一個交易所的成交資訊）。
若有 > 0.1% 差異就值得 audit：
- FinMind 偶爾汙染（如 2317 close=0）
- yfinance 對台股的 Adj Close 演算法可能跟 TWSE 不同
- TWSE 是真理源 (raw)

設計：
- 從 DuckDB 已有的 16 symbols 隨機抽 sample_size 個 (symbol, recent date) 組合
- FinMind: 從 DB 直接讀 (已是 raw)
- TWSE:    跑 stock_month 抓該月，挑該日
- yfinance: 跑 daily_price 抓該日

輸出：
- `data/_storage/cross_source_audit_YYYY-MM-DD.json` — 機讀
- `data/_storage/cross_source_audit_YYYY-MM-DD.md`   — 人讀，divergence > 0.1% 才列

用法：
  uv run python scripts/cross_source_audit.py --sample 5      # 預設
  uv run python scripts/cross_source_audit.py --sample 20
  uv run python scripts/cross_source_audit.py --symbols 2330,0050 --sample 3
  uv run python scripts/cross_source_audit.py --skip-yfinance  # 只比 FinMind vs TWSE

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): get_twse_row 失敗時 log warning 留 trace
                       (解決上次 missing case 完全 silent 的問題)
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from config.settings import get_settings
from data.database import connect
from data.sources.twse_client import TwseClient, TwseError
from data.sources.yfinance_client import YFinanceClient, YFinanceError
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def list_symbols_with_data() -> list[str]:
    """DB 內有 daily_price 的 symbols (排除 TAIEX，個股獨立稽核)。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_price WHERE stock_id != 'TAIEX' ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


def random_recent_date(symbol: str, max_days_back: int = 90) -> date | None:
    """從 DB 該 symbol 最近 max_days_back 天裡隨機挑一個交易日。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT date FROM daily_price
            WHERE stock_id = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            [symbol, max_days_back],
        ).fetchall()
    if not rows:
        return None
    return random.choice(rows)[0]


def get_finmind_row(symbol: str, target: date) -> dict[str, Any] | None:
    """從 DB (其實就是 FinMind 落下的 raw) 抓某天 OHLC。"""
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT open, high, low, close, volume FROM daily_price
            WHERE stock_id = ? AND date = ?
            """,
            [symbol, target],
        ).fetchone()
    if row is None:
        return None
    return {"open": row[0], "high": row[1], "low": row[2], "close": row[3], "volume": row[4]}


def get_twse_row(twse: TwseClient, symbol: str, target: date) -> dict[str, Any] | None:
    """從 TWSE STOCK_DAY 抓該月，挑該日的 OHLC。

    v0.1.1: 失敗時 log warning 留 trace (上次 missing 是 silent)。
    """
    try:
        df = twse.stock_month(symbol, target)
    except TwseError as e:
        logger.warning("audit_twse_fetch_error",
                       symbol=symbol, target=str(target), error=str(e))
        return None
    if df.is_empty():
        # stock_month 內部已 log (stat ≠ OK or empty data)
        logger.warning("audit_twse_returned_empty",
                       symbol=symbol, target=str(target),
                       hint="check stock_month log for stat≠OK reason")
        return None
    filtered = df.filter(df["date"] == target)
    if filtered.is_empty():
        logger.warning("audit_twse_target_date_not_in_month",
                       symbol=symbol, target=str(target),
                       month_n_rows=df.height,
                       hint="TWSE returned the month but not this specific date")
        return None
    row = filtered.row(0, named=True)
    return {
        "open": row["open"], "high": row["high"], "low": row["low"],
        "close": row["close"], "volume": row["volume"],
        "twse_note": row.get("twse_note", ""),
    }


def get_yfinance_row(yf_client: YFinanceClient, symbol: str, target: date) -> dict[str, Any] | None:
    """從 yfinance 抓該日的 OHLC + Adj Close。"""
    try:
        df = yf_client.daily_price(symbol, target, target)
    except YFinanceError as e:
        logger.warning("yf_fetch_failed", symbol=symbol, target=str(target), error=str(e))
        return None
    if df.is_empty():
        return None
    filtered = df.filter(df["date"] == target)
    if filtered.is_empty():
        return None
    row = filtered.row(0, named=True)
    return {
        "open": row["open"], "high": row["high"], "low": row["low"],
        "close": row["close"], "adj_close": row.get("adj_close"), "volume": row["volume"],
    }


# ─────────────────────────────────────────────────────────────
# Divergence
# ─────────────────────────────────────────────────────────────

DIVERGENCE_THRESHOLD = 0.001  # 0.1%


def relative_diff(a: float | None, b: float | None) -> float | None:
    """相對差 |a-b|/avg(|a|,|b|)；None 任一為空回 None。"""
    if a is None or b is None:
        return None
    base = (abs(a) + abs(b)) / 2
    if base == 0:
        return 0.0 if a == b else float("inf")
    return abs(a - b) / base


def compare_pair(label: str, ra: dict | None, rb: dict | None, fields: list[str]) -> dict[str, Any]:
    """比兩個 source 在同一 (symbol, date) 的 OHLC."""
    result: dict[str, Any] = {"compare": label, "diffs": {}, "max_pct": 0.0}
    if ra is None or rb is None:
        result["status"] = "missing"
        result["details"] = (
            f"a={'present' if ra else 'missing'}, b={'present' if rb else 'missing'}"
        )
        return result

    max_diff = 0.0
    for f in fields:
        d = relative_diff(ra.get(f), rb.get(f))
        if d is not None:
            result["diffs"][f] = round(d, 5)
            max_diff = max(max_diff, d)
    result["max_pct"] = round(max_diff, 5)
    result["status"] = "diverge" if max_diff > DIVERGENCE_THRESHOLD else "match"
    return result


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-source data audit (FinMind / TWSE / yfinance)"
    )
    parser.add_argument("--sample", type=int, default=5,
                        help="隨機抽樣個數 (預設 5)")
    parser.add_argument("--symbols", type=str,
                        help="逗號分隔的 symbols；不給就從 DB 全部隨機")
    parser.add_argument("--max-days-back", type=int, default=90,
                        help="只抽過去 N 天的日期 (預設 90)")
    parser.add_argument("--skip-yfinance", action="store_true",
                        help="不打 yfinance (避免被擋 / 加速)")
    parser.add_argument("--output", type=Path,
                        help="輸出目錄；預設 data/_storage/")
    parser.add_argument("--seed", type=int, default=None,
                        help="random seed (除錯重現用)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    settings = get_settings()
    output_dir = args.output or settings.data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # 決定 sample 來源
    if args.symbols:
        all_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        all_symbols = list_symbols_with_data()
    if not all_symbols:
        print("❌ DB 內沒任何個股 daily_price 資料，請先跑 download_daily.py")
        return 1

    # 建立 sample list (symbol, date)
    samples: list[tuple[str, date]] = []
    pool = list(all_symbols)
    while len(samples) < args.sample and pool:
        sym = random.choice(pool)
        d = random_recent_date(sym, args.max_days_back)
        if d is not None:
            samples.append((sym, d))

    if not samples:
        print("❌ 無法產生 sample (檢查 DB 是否有最近 90 天資料)")
        return 1

    print(f"Auditing {len(samples)} (symbol, date) samples...")
    for sym, d in samples:
        print(f"  • {sym} @ {d}")
    print()

    twse = TwseClient(sleep_between_calls=1.0)
    yf_client = None if args.skip_yfinance else YFinanceClient()

    audit_results: list[dict[str, Any]] = []

    for i, (sym, target) in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {sym} @ {target}")
        fm = get_finmind_row(sym, target)
        tw = get_twse_row(twse, sym, target)
        yf = get_yfinance_row(yf_client, sym, target) if yf_client else None

        record: dict[str, Any] = {
            "stock_id": sym,
            "date": str(target),
            "finmind": fm,
            "twse": tw,
            "yfinance": yf,
            "comparisons": [],
        }

        # 比 FinMind raw vs TWSE raw — 應該幾乎一致
        record["comparisons"].append(
            compare_pair("finmind_vs_twse", fm, tw, ["open", "high", "low", "close"])
        )
        # 比 FinMind raw vs yfinance Close (raw, 不是 adj)
        if yf is not None:
            record["comparisons"].append(
                compare_pair("finmind_vs_yfinance_raw", fm, yf, ["open", "high", "low", "close"])
            )
            # 額外：yfinance Adj Close vs FinMind raw — 差幾 % 可看到 yf 的 adjustment 強度
            if yf.get("adj_close") is not None and fm:
                ratio = yf["adj_close"] / fm["close"] if fm["close"] else None
                record["yfinance_adj_close_ratio"] = round(ratio, 5) if ratio else None

        # 顯示摘要
        for cmp in record["comparisons"]:
            icon = {"match": "✓", "diverge": "⚠", "missing": "○"}.get(cmp["status"], "?")
            print(f"    {icon} {cmp['compare']:30s} max_pct={cmp['max_pct']*100:.3f}%  {cmp['status']}")

        audit_results.append(record)

    twse.close()

    # 統計 divergence
    diverge_count = 0
    match_count = 0
    missing_count = 0
    for rec in audit_results:
        for cmp in rec["comparisons"]:
            if cmp["status"] == "diverge":
                diverge_count += 1
            elif cmp["status"] == "match":
                match_count += 1
            else:
                missing_count += 1

    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "sample_size": len(samples),
        "comparison_total": match_count + diverge_count + missing_count,
        "match": match_count,
        "diverge": diverge_count,
        "missing": missing_count,
        "divergence_threshold": DIVERGENCE_THRESHOLD,
        "results": audit_results,
    }

    today = date.today().isoformat()
    json_path = output_dir / f"cross_source_audit_{today}.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")
    md_path = output_dir / f"cross_source_audit_{today}.md"
    md_path.write_text(_render_markdown(summary), encoding="utf-8")

    print(f"\n{'='*60}\nSummary")
    print(f"{'='*60}")
    print(f"  Match:    {match_count}")
    print(f"  Diverge:  {diverge_count}")
    print(f"  Missing:  {missing_count}")
    print(f"\n📄 JSON: {json_path}")
    print(f"📄 MD:   {md_path}")

    # 不 fail exit code，divergence 本身就是 audit 訊號 (寫進報告)
    return 0


def _render_markdown(summary: dict) -> str:
    """產出人讀 markdown audit report。"""
    lines: list[str] = []
    lines.append(f"# Cross-source Audit — {summary['run_at'][:10]}")
    lines.append("")
    lines.append(f"- run_at: `{summary['run_at']}`")
    lines.append(f"- sample size: **{summary['sample_size']}**")
    lines.append(f"- divergence threshold: {summary['divergence_threshold']*100:.2f}%")
    lines.append(f"- comparisons: match={summary['match']}, "
                 f"diverge={summary['diverge']}, missing={summary['missing']}")
    lines.append("")

    # Divergence rows only
    diverge_records: list[dict] = []
    for rec in summary["results"]:
        for cmp in rec["comparisons"]:
            if cmp["status"] in ("diverge", "missing"):
                diverge_records.append({
                    "stock_id": rec["stock_id"],
                    "date": rec["date"],
                    "compare": cmp["compare"],
                    "status": cmp["status"],
                    "max_pct": cmp.get("max_pct", 0.0),
                    "diffs": cmp.get("diffs", {}),
                    "details": cmp.get("details", ""),
                })

    if diverge_records:
        lines.append("## ⚠ Divergence / Missing cases")
        lines.append("")
        lines.append("| Symbol | Date | Compare | Status | Max % | Diffs |")
        lines.append("|---|---|---|---|---:|---|")
        for r in diverge_records:
            diffs_str = ", ".join(f"{k}={v*100:.3f}%" for k, v in r["diffs"].items()) or r["details"]
            lines.append(
                f"| {r['stock_id']} | {r['date']} | {r['compare']} | "
                f"{r['status']} | {r['max_pct']*100:.3f}% | {diffs_str} |"
            )
        lines.append("")
        lines.append("**Action items**: 對每個 diverge case 進 notebook 看實際 OHLC，"
                     "判斷誰錯。若 yfinance 系統性偏離 → 可能是 Adj Close 邏輯不同；"
                     "若 FinMind 偏離 → 可能 sanity filter 沒擋住的另一種污染；"
                     "若 TWSE 偏離 → 罕見，先確認 TWSE STOCK_DAY 那月該日有資料。")
        lines.append("")
    else:
        lines.append("## ✓ No divergence detected")
        lines.append("")
        lines.append("三家 raw OHLC 全部 match (差異 < 0.1%)。")
        lines.append("這表示我們的 FinMind raw 跟 TWSE / yfinance 對齊，沒系統性偏差。")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("📝 持續發現的 divergence pattern 整理到 `docs/data_behavior_notes.md`。")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
