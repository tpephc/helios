#!/usr/bin/env python3
# scripts/find_bearish_stocks.py
"""Top-200 bearish stock screener — v0.1.15.

Identifies stocks in the dynamic_top200 universe currently in bearish
trend alignment with a composite score.

Scoring (0-100):
    MA alignment (40):
        close < sma_20 < sma_50 < sma_200 + both deltas negative  = 40
        close < sma_20 < sma_50 (partial, sma_200 not yet broken)  = 20
    Momentum (30):
        RSI component (rsi_14):
            RSI < 30                                               = 25
            RSI 30-40                                              = 18
            RSI 40-50                                              = 8
        ROC20 bonus (roc_20 stored as %, e.g. -12.5 = -12.5%):
            ROC20 < -10%                                           = +5
    Volume confirmation (30):
        on a true down day (close < prev_close) AND close < sma_20:
            rel_volume_20 >= 1.5                                   = 30
            rel_volume_20 1.0-1.5                                  = 15

Designed as a risk filter / exclusion watchlist, not a short-selling signal.
For backtesting use universe_snapshot table to avoid lookahead bias.

Usage:
    uv run python scripts/find_bearish_stocks.py
    uv run python scripts/find_bearish_stocks.py --as-of 2026-05-22
    uv run python scripts/find_bearish_stocks.py --min-score 50
    uv run python scripts/find_bearish_stocks.py --all
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date as date_type
from pathlib import Path

import yaml

from data.database import connect
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of

logger = get_logger(__name__)

_DEFAULT_MIN_SCORE = 40
_MAX_IN_CLAUSE_ITEMS = 500
_MAX_RESULTS = 50
_LABEL_PRIORITY = {"STRONG_BEAR": 4, "BEAR": 3, "WEAK_BEAR": 2, "WATCH": 1}


# ── float safety guard ─────────────────────────────────────────────────────────

def _safe_float(val: object, field: str, stock_id: str) -> float | None:
    """Return val as float, or None if null/NaN/inf."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        logger.warning("invalid_float_in_feature", field=field, stock_id=stock_id)
        return None
    if math.isnan(f) or math.isinf(f):
        logger.warning("nan_or_inf_in_feature", field=field, stock_id=stock_id)
        return None
    return f


# ── display formatters ─────────────────────────────────────────────────────────

def _fmt_rsi(val: float | None) -> str:
    return "  N/A" if val is None else f"{val:>5.1f}"


def _fmt_roc(val: float | None) -> str:
    return "   N/A" if val is None else f"{val:>+6.1f}%"


def _fmt_rvol(val: float | None) -> str:
    return "  N/A" if val is None else f"{val:>5.2f}x"


# ── scoring engine ─────────────────────────────────────────────────────────────

def _compute_score(r: dict) -> tuple[int, str]:
    """Compute bearish score and label from a feature row.

    Returns:
        (score 0-100, label)
        label: STRONG_BEAR | BEAR | WEAK_BEAR | WATCH | INSUFFICIENT_DATA | NONE
    """
    sid = r.get("stock_id", "?")
    close      = _safe_float(r["close"],             "close",             sid)
    ma20       = _safe_float(r["sma_20"],            "sma_20",            sid)
    ma50       = _safe_float(r["sma_50"],            "sma_50",            sid)
    ma200      = _safe_float(r["sma_200"],           "sma_200",           sid)
    d20        = _safe_float(r["sma_20_delta_5d"],   "sma_20_delta_5d",   sid)
    d50        = _safe_float(r["sma_50_delta_10d"],  "sma_50_delta_10d",  sid)
    rsi        = _safe_float(r["rsi_14"],            "rsi_14",            sid)
    roc        = _safe_float(r["roc_20"],            "roc_20",            sid)
    rvol       = _safe_float(r["rel_volume_20"],     "rel_volume_20",     sid)
    prev_close = _safe_float(r["prev_close"],        "prev_close",        sid)

    # Guard: core fields + deltas required
    if any(v is None for v in (close, ma20, ma50, ma200)):
        return 0, "INSUFFICIENT_DATA"
    if d20 is None or d50 is None:
        return 0, "INSUFFICIENT_DATA"

    score = 0

    # ── MA alignment (40 pts) ──────────────────────────────
    full_align = (close < ma20 < ma50 < ma200) and d20 < 0 and d50 < 0
    partial_align = not full_align and (close < ma20 < ma50)

    if full_align:
        score += 40
    elif partial_align:
        score += 20
    else:
        return 0, "NONE"

    # ── Momentum: RSI (25 pts) ─────────────────────────────
    if rsi is not None:
        if rsi < 30:
            score += 25
        elif rsi < 40:
            score += 18
        elif rsi < 50:
            score += 8

    # ── Momentum: ROC20 bonus (5 pts) ─────────────────────
    if roc is not None and roc < -10:
        score += 5

    # ── Volume confirmation (30 pts) ──────────────────────
    # Volume signal is meaningful only on a true down day (close < prev_close).
    # Using close < sma_20 alone would count today's rebound above prev_close.
    is_down_day = (prev_close is not None) and (close < prev_close)
    if is_down_day and close < ma20 and rvol is not None:
        if rvol >= 1.5:
            score += 30
        elif rvol >= 1.0:
            score += 15

    score = min(score, 100)

    if score >= 75 and full_align:
        label = "STRONG_BEAR"
    elif score >= 50 and full_align:
        label = "BEAR"
    elif score >= 30:
        label = "WEAK_BEAR"
    else:
        label = "WATCH"

    return score, label


# ── data loader ────────────────────────────────────────────────────────────────

def find_bearish_stocks(
    as_of: date_type,
    min_score: int = _DEFAULT_MIN_SCORE,
    include_none: bool = False,
) -> list[dict]:
    """Screen dynamic_top200 for bearish conditions on as_of date.

    Args:
        as_of: Evaluation date with features available in daily_features.
        min_score: Minimum composite score to include (0-100).
        include_none: If True, include NONE / WATCH results.

    Returns:
        List of result dicts sorted by (label_priority DESC, score DESC),
        capped at _MAX_RESULTS.
    """
    config_path = Path("config/universe.yaml")
    try:
        with config_path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("universe_config_missing", path=str(config_path))
        raise

    universe: list[str] = cfg["dynamic_top200"]["symbols"]
    if not universe:
        raise ValueError("dynamic_top200.symbols is empty in config/universe.yaml")
    if len(universe) > _MAX_IN_CLAUSE_ITEMS:
        logger.warning(
            "universe_too_large_for_in_clause",
            count=len(universe),
            max_allowed=_MAX_IN_CLAUSE_ITEMS,
        )

    # Build parameterised IN clause — placeholders are only '?' chars, no injection risk.
    # Still avoid f-string for WHERE fragment to keep the pattern clean.
    placeholders = ",".join("?" * len(universe))
    query = (
        "WITH windowed AS ("
        "    SELECT f.stock_id, f.date, p.adj_close AS close,"
        "           LAG(p.adj_close, 1) OVER w AS prev_close,"
        "           f.sma_20, f.sma_50, f.sma_200,"
        "           f.rsi_14, f.roc_20, f.rel_volume_20,"
        "           (f.sma_20 - LAG(f.sma_20,  5) OVER w) AS sma_20_delta_5d,"
        "           (f.sma_50 - LAG(f.sma_50, 10) OVER w) AS sma_50_delta_10d,"
        "           (p.adj_close - f.sma_200) / NULLIF(f.sma_200, 0) * 100 AS dist_sma200_pct,"
        "           COALESCE(cm.short_name, f.stock_id) AS name"
        "    FROM   daily_features f"
        "    JOIN   daily_price_adj p ON f.stock_id = p.stock_id AND f.date = p.date"
        "    LEFT JOIN company_metadata cm ON f.stock_id = cm.stock_id"
        "    WHERE  f.stock_id IN (" + placeholders + ")"
        "      AND  f.sma_20  IS NOT NULL"
        "      AND  f.sma_50  IS NOT NULL"
        "      AND  f.sma_200 IS NOT NULL"
        "      AND  f.sma_200 != 0"
        "    WINDOW w AS (PARTITION BY f.stock_id ORDER BY f.date)"
        ") "
        "SELECT * FROM windowed WHERE date = ?"
    )

    with connect(read_only=True) as conn:
        rows = conn.execute(query, universe + [str(as_of)]).fetchall()

    columns = [
        "stock_id", "date", "close", "prev_close",
        "sma_20", "sma_50", "sma_200",
        "rsi_14", "roc_20", "rel_volume_20",
        "sma_20_delta_5d", "sma_50_delta_10d", "dist_sma200_pct", "name",
    ]

    results = []
    for row in rows:
        r = dict(zip(columns, row))
        score, label = _compute_score(r)
        if label in ("NONE", "INSUFFICIENT_DATA") and not include_none:
            continue
        if score < min_score:
            continue
        r["score"] = score
        r["label"] = label
        results.append(r)

    results = sorted(
        results,
        key=lambda x: (_LABEL_PRIORITY.get(x["label"], 0), x["score"]),
        reverse=True,
    )

    if len(results) > _MAX_RESULTS:
        logger.warning("results_truncated", total=len(results), kept=_MAX_RESULTS)
        results = results[:_MAX_RESULTS]

    return results


# ── display ────────────────────────────────────────────────────────────────────

def _print_table(results: list[dict], as_of: date_type) -> None:
    if not results:
        print("無符合條件的個股")
        return

    _emoji = {
        "STRONG_BEAR": "🔴", "BEAR": "🟠",
        "WEAK_BEAR": "🟡", "WATCH": "⚪",
    }
    _label_hdr = {
        "STRONG_BEAR": "強空頭 (≥75分)",
        "BEAR":        "空頭   (≥50分)",
        "WEAK_BEAR":   "弱空頭 (≥30分)",
        "WATCH":       "觀察   (<30分)",
    }
    _col_hdr = (
        f"  {'代號':<6} {'名稱':<8}  {'分數':>4}"
        f"  {'收盤':>8}  {'MA20':>8}  {'MA50':>8}  {'MA200':>8}"
        f"  {'距MA200':>8}  {'RSI':>5}  {'ROC20':>7}  {'量比':>6}"
    )
    _divider = "  " + "─" * 98

    print(f"\n📊 空頭篩選結果 ({as_of})\n")

    prev_label = None
    for r in results:
        if r["label"] != prev_label:
            emoji = _emoji.get(r["label"], "")
            print(f"\n  {emoji} {_label_hdr.get(r['label'], r['label'])}")
            print(_col_hdr)
            print(_divider)
            prev_label = r["label"]

        print(
            f"  {r['stock_id']:<6} {r['name']:<8}"
            f"  {r['score']:>4}"
            f"  {r['close']:>8.2f}"
            f"  {r['sma_20']:>8.2f}"
            f"  {r['sma_50']:>8.2f}"
            f"  {r['sma_200']:>8.2f}"
            f"  {(r['dist_sma200_pct'] or 0):>+7.1f}%"
            f"  {_fmt_rsi(r['rsi_14'])}"
            f"  {_fmt_roc(r['roc_20'])}"
            f"  {_fmt_rvol(r['rel_volume_20'])}"
        )

    by_label: dict[str, int] = {}
    for r in results:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1

    summary = "  ".join(
        f"{_emoji.get(k,'')}{k}={v}"
        for k, v in sorted(
            by_label.items(),
            key=lambda x: _LABEL_PRIORITY.get(x[0], 0),
            reverse=True,
        )
    )
    print(f"\n  共 {len(results)} 檔 / 200 大成分股   {summary}")
    print("\n  評分：MA排列(40) + RSI(25) + ROC20加速(5) + 量能確認(30)")
    print("  MACD / Lower-Highs-Lows → v0.1.16 補上")


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 bearish stock screener")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--min-score", type=int, default=_DEFAULT_MIN_SCORE,
                        help=f"Minimum score (default {_DEFAULT_MIN_SCORE})")
    parser.add_argument("--all", action="store_true",
                        help="Show all tiers including WATCH")
    args = parser.parse_args()

    as_of = resolve_as_of(args.as_of)
    min_score = 0 if args.all else args.min_score
    logger.info("bearish_screen_start", as_of=str(as_of), min_score=min_score)

    results = find_bearish_stocks(as_of=as_of, min_score=min_score)
    _print_table(results, as_of)

    logger.info("bearish_screen_done", count=len(results), as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
