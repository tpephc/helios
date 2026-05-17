#!/usr/bin/env python3
# scripts/data_quality_report.py
"""系統化資料品質報告 — 純 DuckDB 讀取，不打 API。

目的：把 daily_price 內容用結構化指標 profile 一遍，產出兩份報告：
- `data/_storage/quality_report_YYYY-MM-DD.json` — 機讀，未來 monitoring 可消費
- `data/_storage/quality_report_YYYY-MM-DD.md`   — 人讀，看異常案例與摘要

per-symbol 指標：
- 列數 / 時間範圍
- 缺日 (missing trading days vs expected from TAIEX baseline)
- 重複 (stock_id, date) 列數
- 零成交日比例
- 最大連續 gap (天)
- 異常漲跌幅 (|daily| > 10.5%，多半是除權息未調整)
- 漲跌停日數 (|daily| >= 9.5%)
- 流動性 tier (依日均成交金額分高/中/低)
- 首尾日期 (上市 / 下市 proxy)

cross-symbol 指標：
- ETF 是否同步缺漏 (理論上同日休市應一致)
- 與 TAIEX 的交易日對齊度
- institutional / monthly_revenue 覆蓋率

用法：
  uv run python scripts/data_quality_report.py
  uv run python scripts/data_quality_report.py --symbols 2330,0050
  uv run python scripts/data_quality_report.py --output /custom/path

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): expected_trading_days 改用 TAIEX baseline (解決偽 80 missing);
                       abnormal_returns filter close > 0 (解決零 close 造成的 +inf%);
                       fetch_arrow_table → to_arrow_table (Polars deprecation)
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from config.settings import get_settings
from data.database import connect
from market import is_trading_day
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# DB readers
# ─────────────────────────────────────────────────────────────


def list_symbols_in_db() -> list[str]:
    """取得 daily_price 表內所有 distinct stock_id。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT stock_id FROM daily_price ORDER BY stock_id"
        ).fetchall()
    return [r[0] for r in rows]


def read_symbol_data(stock_id: str) -> pl.DataFrame:
    """讀某 symbol 的全部日 K 資料 → Polars DataFrame。"""
    with connect(read_only=True) as conn:
        arrow_tbl = conn.execute(
            "SELECT * FROM daily_price WHERE stock_id = ? ORDER BY date",
            [stock_id],
        ).to_arrow_table()
    return pl.from_arrow(arrow_tbl)  # type: ignore[return-value]


def count_duplicates(stock_id: str) -> int:
    """重複 (stock_id, date) 列數。理論上 PRIMARY KEY 不允許，這裡保險檢查。"""
    with connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cnt - 1), 0) FROM (
                SELECT COUNT(*) AS cnt FROM daily_price
                WHERE stock_id = ?
                GROUP BY date
                HAVING cnt > 1
            )
            """,
            [stock_id],
        ).fetchone()
    return int(row[0]) if row else 0


# ─────────────────────────────────────────────────────────────
# Per-symbol profiling
# ─────────────────────────────────────────────────────────────

ABNORMAL_THRESHOLD = 0.105   # 10.5%, 超過台股漲跌停 → 多半除權息未調整
LIMIT_TOUCH_THRESHOLD = 0.095  # 9.5%, 接近漲跌停 (容差 0.5%)


def _liquidity_tier(avg_turnover: float | None) -> str:
    if avg_turnover is None:
        return "unknown"
    if avg_turnover >= 1e9:
        return "high"
    if avg_turnover >= 1e8:
        return "mid"
    return "low"


def _count_expected_trading_days(start: date, end: date) -> int:
    """日曆預期的交易日數。

    v0.1.7: 改用 TAIEX 在 DB 內的實際交易日數做為 baseline。
    這比 `is_trading_day()` 準確得多 (後者過度樂觀，會把彈性放假、補班、颱風休市等
    台灣特殊假日算成交易日 → 對 5 年資料會誤報 ~80 個偽 missing)。

    fallback 順序：
    1. TAIEX 在 [start, end] 範圍內的實際交易日數 (最準)
    2. is_trading_day() 計算 (TAIEX 沒涵蓋時)
    """
    # 嘗試 1: TAIEX baseline
    try:
        with connect(read_only=True) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM daily_price
                WHERE stock_id = 'TAIEX' AND date BETWEEN ? AND ?
                """,
                [start, end],
            ).fetchone()
        if row and row[0] > 0:
            return int(row[0])
    except Exception:
        pass

    # 嘗試 2: 日曆 fallback
    from datetime import timedelta
    n = 0
    d = start
    while d <= end:
        if is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def per_symbol_report(stock_id: str) -> dict[str, Any]:
    """單 symbol 的完整品質報告 dict。"""
    df = read_symbol_data(stock_id)

    if df.is_empty():
        return {
            "stock_id": stock_id,
            "status": "no_data",
            "n_rows": 0,
        }

    df = df.sort("date")
    first_d = df["date"].min()
    last_d = df["date"].max()
    n_rows = df.height

    # 預期 vs 實際交易日
    expected_days = _count_expected_trading_days(first_d, last_d)
    missing = expected_days - n_rows  # 可能為負 (DB 有 calendar 沒有的日)

    # 重複列
    n_dup = count_duplicates(stock_id)

    # 零成交日
    n_zero_vol = df.filter(pl.col("volume") == 0).height
    zero_vol_ratio = n_zero_vol / n_rows if n_rows else 0.0

    # 連續 gap (相鄰兩日的日曆天數差)
    df_g = df.with_columns(
        gap_days=(pl.col("date") - pl.col("date").shift(1)).dt.total_days()
    )
    max_gap_days = df_g["gap_days"].max()
    max_gap_days = int(max_gap_days) if max_gap_days is not None else 0

    # 異常漲跌幅 (v0.1.7: filter close > 0 避免零 close 造成的 +inf%)
    df_pct = (
        df.filter(pl.col("close") > 0)
        .with_columns(pct=(pl.col("close") / pl.col("close").shift(1) - 1))
    )
    abnormal = df_pct.filter(pl.col("pct").abs() > ABNORMAL_THRESHOLD)
    abnormal_samples = (
        abnormal.select(["date", "close", "pct"])
        .sort(pl.col("pct").abs(), descending=True)
        .head(5)
        .to_dicts()
    )

    # 漲跌停觸發 (用同一份 filtered df 計算)
    limit_touches = df_pct.filter(pl.col("pct").abs() >= LIMIT_TOUCH_THRESHOLD)
    n_limit = limit_touches.height

    # 流動性
    avg_turnover = df["turnover"].mean()
    avg_volume = df["volume"].mean()
    # 振幅: (high-low)/close
    df_amp = df.with_columns(
        amplitude=((pl.col("high") - pl.col("low")) / pl.col("close"))
    )
    avg_amplitude = df_amp["amplitude"].mean()

    # 缺值
    n_null_close = df.filter(pl.col("close").is_null()).height
    n_null_volume = df.filter(pl.col("volume").is_null()).height

    return {
        "stock_id": stock_id,
        "status": "ok",
        "n_rows": n_rows,
        "first_date": str(first_d),
        "last_date": str(last_d),
        "expected_trading_days": expected_days,
        "missing_days": missing,
        "duplicate_rows": n_dup,
        "zero_volume": {
            "count": n_zero_vol,
            "ratio": round(zero_vol_ratio, 4),
        },
        "max_consecutive_gap_days": max_gap_days,
        "abnormal_returns": {
            "threshold": ABNORMAL_THRESHOLD,
            "count": abnormal.height,
            "samples": [
                {"date": str(s["date"]), "close": s["close"],
                 "pct": round(s["pct"], 4) if s["pct"] is not None else None}
                for s in abnormal_samples
            ],
        },
        "limit_touches": {
            "threshold": LIMIT_TOUCH_THRESHOLD,
            "count": n_limit,
        },
        "liquidity": {
            "avg_turnover": float(avg_turnover) if avg_turnover else None,
            "avg_volume": float(avg_volume) if avg_volume else None,
            "avg_amplitude": (
                round(float(avg_amplitude), 4) if avg_amplitude else None
            ),
            "tier": _liquidity_tier(avg_turnover),
        },
        "nulls": {
            "close": n_null_close,
            "volume": n_null_volume,
        },
    }


# ─────────────────────────────────────────────────────────────
# Cross-symbol profiling
# ─────────────────────────────────────────────────────────────


def cross_symbol_report(per_symbol_results: list[dict[str, Any]]) -> dict[str, Any]:
    """跨 symbol 的對齊與覆蓋分析。"""
    # 過濾掉 no_data 的
    valid = [r for r in per_symbol_results if r.get("status") == "ok"]
    if not valid:
        return {"status": "no_data"}

    # 找出 TAIEX 作為基準
    taiex = next((r for r in valid if r["stock_id"] == "TAIEX"), None)

    # 每個 symbol 的日期集合
    symbol_dates: dict[str, set[date]] = {}
    for r in valid:
        sid = r["stock_id"]
        with connect(read_only=True) as conn:
            dates = conn.execute(
                "SELECT date FROM daily_price WHERE stock_id = ?",
                [sid],
            ).fetchall()
        symbol_dates[sid] = {d[0] if isinstance(d[0], date) else d[0].date() for d in dates}

    # TAIEX-aligned：以 TAIEX 為基準，每個 symbol 缺多少天
    taiex_alignment: dict[str, dict[str, Any]] = {}
    if taiex and "TAIEX" in symbol_dates:
        taiex_dates = symbol_dates["TAIEX"]
        for sid, sdates in symbol_dates.items():
            if sid == "TAIEX":
                continue
            # 只比對該 symbol 的日期範圍內
            symbol_min = min(sdates) if sdates else None
            symbol_max = max(sdates) if sdates else None
            if symbol_min is None:
                continue
            relevant_taiex = {d for d in taiex_dates if symbol_min <= d <= symbol_max}
            missing_from_symbol = relevant_taiex - sdates
            taiex_alignment[sid] = {
                "missing_when_taiex_open": len(missing_from_symbol),
                "samples": sorted([str(d) for d in missing_from_symbol])[:5],
            }

    # institutional / monthly_revenue 覆蓋率
    coverage: dict[str, Any] = {}
    with connect(read_only=True) as conn:
        for table in ("institutional_investors", "monthly_revenue"):
            try:
                row = conn.execute(
                    f"SELECT COUNT(DISTINCT stock_id) FROM {table}"
                ).fetchone()
                coverage[table] = int(row[0]) if row else 0
            except Exception as e:
                coverage[table] = f"error: {e}"

    return {
        "n_symbols": len(valid),
        "taiex_baseline": taiex is not None,
        "taiex_alignment": taiex_alignment,
        "supplementary_coverage": coverage,
    }


# ─────────────────────────────────────────────────────────────
# Markdown rendering
# ─────────────────────────────────────────────────────────────


def render_markdown(summary: dict[str, Any]) -> str:
    """產生人讀 Markdown 報告。"""
    lines: list[str] = []
    lines.append(f"# Helios Data Quality Report — {summary['run_at'][:10]}")
    lines.append("")
    lines.append(f"- run_at: `{summary['run_at']}`")
    lines.append(f"- helios_version: `{summary.get('helios_version', 'unknown')}`")
    lines.append(f"- symbols checked: **{len(summary['per_symbol'])}**")
    lines.append("")

    # ── per-symbol 表 ──
    lines.append("## Per-symbol summary")
    lines.append("")
    lines.append("| Symbol | Rows | Range | Missing | Dup | Zero-vol | MaxGap | Abnormal | Limit | Tier |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|---|")
    for r in summary["per_symbol"]:
        if r.get("status") != "ok":
            lines.append(f"| {r['stock_id']} | 0 | — | — | — | — | — | — | — | — |")
            continue
        rng = f"{r['first_date']} → {r['last_date']}"
        zv = f"{r['zero_volume']['count']} ({r['zero_volume']['ratio']*100:.1f}%)"
        ab = r["abnormal_returns"]["count"]
        lim = r["limit_touches"]["count"]
        tier = r["liquidity"]["tier"]
        lines.append(
            f"| {r['stock_id']} | {r['n_rows']} | {rng} | "
            f"{r['missing_days']} | {r['duplicate_rows']} | {zv} | "
            f"{r['max_consecutive_gap_days']} | {ab} | {lim} | {tier} |"
        )
    lines.append("")

    # ── 異常案例 ──
    has_anomalies = any(
        r.get("status") == "ok" and r["abnormal_returns"]["count"] > 0
        for r in summary["per_symbol"]
    )
    if has_anomalies:
        lines.append("## Abnormal return samples (|daily| > 10.5%)")
        lines.append("")
        lines.append("通常是除權息或拆分未調整。Step 3 indicator 設計必須考慮。")
        lines.append("")
        for r in summary["per_symbol"]:
            if r.get("status") != "ok" or not r["abnormal_returns"]["samples"]:
                continue
            lines.append(f"### {r['stock_id']}")
            lines.append("")
            for s in r["abnormal_returns"]["samples"]:
                lines.append(f"- `{s['date']}` close={s['close']:.2f} pct={s['pct']*100:+.2f}%")
            lines.append("")

    # ── cross-symbol ──
    cs = summary.get("cross_symbol", {})
    if cs and cs.get("taiex_alignment"):
        lines.append("## TAIEX alignment (symbol 缺漏 vs TAIEX 開盤日)")
        lines.append("")
        lines.append("理論上同期間 symbol 與 TAIEX 應該同步交易。差異 = 個股停牌或資料缺失。")
        lines.append("")
        lines.append("| Symbol | Missing when TAIEX open | Sample dates |")
        lines.append("|---|---:|---|")
        for sid, info in cs["taiex_alignment"].items():
            samples = ", ".join(info["samples"]) if info["samples"] else "—"
            lines.append(f"| {sid} | {info['missing_when_taiex_open']} | {samples} |")
        lines.append("")

    if cs.get("supplementary_coverage"):
        lines.append("## Supplementary coverage")
        lines.append("")
        for tbl, cnt in cs["supplementary_coverage"].items():
            lines.append(f"- **{tbl}**: {cnt} distinct stock_id")
        lines.append("")

    # ── 衍生建議 ──
    lines.append("## Findings hints")
    lines.append("")
    issues_found: list[str] = []
    for r in summary["per_symbol"]:
        if r.get("status") != "ok":
            continue
        sid = r["stock_id"]
        if r["missing_days"] > 5:
            issues_found.append(
                f"`{sid}` 缺 {r['missing_days']} 個交易日 — 可能資料未補完整"
            )
        if r["duplicate_rows"] > 0:
            issues_found.append(
                f"`{sid}` 有 {r['duplicate_rows']} 個重複日 — 違反 PRIMARY KEY 預期，查 finmind_client sort+unique"
            )
        if r["zero_volume"]["ratio"] > 0.1:
            issues_found.append(
                f"`{sid}` 零成交日 {r['zero_volume']['ratio']*100:.1f}% (>10%) — 流動性極低，考慮排除策略 universe"
            )
        # 任何 abnormal return 都該注意 (Step 3 必須處理)
        if r["abnormal_returns"]["count"] >= 1:
            issues_found.append(
                f"`{sid}` 出現 {r['abnormal_returns']['count']} 次 >10.5% 跳空 — "
                f"幾乎肯定是除權息未調整，Step 3 RSI/ATR/MACD 之前必須做 dividend adjustment"
            )
        # 漲跌停日如果是 abnormal 之外的（純漲跌停觸發），也提一下
        non_abnormal_limits = (
            r["limit_touches"]["count"] - r["abnormal_returns"]["count"]
        )
        if non_abnormal_limits >= 3:
            issues_found.append(
                f"`{sid}` 有 {non_abnormal_limits} 次接近漲跌停但未跨 10.5% — "
                f"ATR 計算需注意被截斷的真實波動"
            )
        if r["max_consecutive_gap_days"] > 14:
            issues_found.append(
                f"`{sid}` 最大連續缺 {r['max_consecutive_gap_days']} 天 — 可能停牌、下市，或 universe 設定錯誤"
            )
    if issues_found:
        for issue in issues_found:
            lines.append(f"- {issue}")
    else:
        # 區分「真的沒問題」vs「資料量不足」
        avg_rows = sum(
            r.get("n_rows", 0) for r in summary["per_symbol"]
            if r.get("status") == "ok"
        ) / max(1, sum(1 for r in summary["per_symbol"] if r.get("status") == "ok"))
        if avg_rows < 100:
            lines.append("- 資料量偏少 (avg < 100 rows/symbol)，建議跑 `--full` 重抓 5 年再 profile")
        else:
            lines.append("- 無明顯異常，所有指標在合理範圍")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("📝 把學到的 patterns 整理到 `docs/data_behavior_notes.md`，做為 Step 3 indicator 實作的需求依據。")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def _get_helios_version() -> str:
    try:
        import tomllib
        data = tomllib.loads(Path("pyproject.toml").read_text())
        return data.get("project", {}).get("version", "unknown")
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Systematic data quality profiling for daily_price"
    )
    parser.add_argument(
        "--symbols", type=str,
        help="逗號分隔；不給就 profile 全部",
    )
    parser.add_argument(
        "--output", type=Path,
        help="輸出目錄；預設 data/_storage/",
    )
    args = parser.parse_args()

    settings = get_settings()
    output_dir = args.output or settings.data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = list_symbols_in_db()

    if not symbols:
        print("❌ daily_price 表內沒任何 symbol，請先跑 download_daily.py")
        return 1

    print(f"Profiling {len(symbols)} symbols: {symbols}")
    print()

    per_symbol_results: list[dict[str, Any]] = []
    for i, sid in enumerate(symbols, 1):
        try:
            r = per_symbol_report(sid)
            per_symbol_results.append(r)
            if r.get("status") == "ok":
                tier = r["liquidity"]["tier"]
                print(
                    f"  [{i:2d}/{len(symbols)}] ✓ {sid:8s}  "
                    f"rows={r['n_rows']:4d}  "
                    f"missing={r['missing_days']:3d}  "
                    f"abnormal={r['abnormal_returns']['count']:2d}  "
                    f"tier={tier}"
                )
            else:
                print(f"  [{i:2d}/{len(symbols)}] ○ {sid:8s}  no data")
        except Exception as e:
            logger.exception("profile_error", stock_id=sid)
            print(f"  [{i:2d}/{len(symbols)}] ✗ {sid:8s}  ERROR: {e}")
            per_symbol_results.append({
                "stock_id": sid, "status": "error", "error": str(e),
            })

    cs_report = cross_symbol_report(per_symbol_results)

    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "helios_version": _get_helios_version(),
        "per_symbol": per_symbol_results,
        "cross_symbol": cs_report,
    }

    # JSON output
    today = date.today().isoformat()
    json_path = output_dir / f"quality_report_{today}.json"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n📄 JSON: {json_path}")

    # MD output
    md_path = output_dir / f"quality_report_{today}.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    print(f"📄 MD:   {md_path}")
    print()
    print("💡 把發現的 patterns 累積到: docs/data_behavior_notes.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
