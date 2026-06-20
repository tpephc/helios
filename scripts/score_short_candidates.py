#!/usr/bin/env python3
# scripts/score_short_candidates.py
"""Phase 2 shortability scoring for bearish candidates — v0.1.15.

Takes Phase 1 bearish candidates from find_bearish_stocks() and adds a
shortability_score() to distinguish truly tradeable short setups from
low-convexity trend deteriorations.

Scoring dimensions (0-100):
    A. Volatility (30 pts):
        ATR percentile (252d):     high ATR = potential downside range
        Down gap count (30d):      gap-down frequency = crash tendency
    B. Liquidity (20 pts):
        Volume percentile (252d):  needed for entry/exit execution
    C. Sector relative weakness (25 pts):
        stock ROC20 - sector median ROC20 (both in % units)
    D. Float proxy (15 pts):
        issued_shares as a rough proxy for borrow availability.
        IMPORTANT: large float does NOT guarantee borrow.
        This is only a first-order filter — stocks with very small float
        are almost certainly un-borrowable, but large float is necessary
        but not sufficient.
    E. Momentum acceleration (10 pts):
        ROC5 < ROC20 AND ROC5 < 0 = accelerating decline

Output labels (label priority order is FIXED — see _determine_label()):
    AVOID_SHORT        : shortability < 30 (illiquid / small / low vol)
    NOT_BEARISH_ALIGNED: shortability OK but no MA alignment
    CRASH_PRONE_SHORT  : shortability >= 75 + full MA alignment
    SHORT_CANDIDATE    : shortability >= 50 + full MA alignment
    LOW_CONVEXITY_BEAR : bearish trend but shortability < 50

NOTE: institutional_investors table is currently empty (no flow data).
      Institutional unwind proxy deferred to when data is available.

Usage:
    uv run python scripts/score_short_candidates.py
    uv run python scripts/score_short_candidates.py --as-of 2026-05-22
    uv run python scripts/score_short_candidates.py --min-bearish 50
    uv run python scripts/score_short_candidates.py --min-short 50
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date as date_type
from datetime import timedelta

from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from data.database import connect
from find_bearish_stocks import find_bearish_stocks
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of
from market.trading_calendar import is_trading_day

logger = get_logger(__name__)

_DEFAULT_MIN_BEARISH = 40
_DEFAULT_MIN_SHORT   = 0     # show all labels by default
_LABEL_PRIORITY = {
    "CRASH_PRONE_SHORT":   4,
    "SHORT_CANDIDATE":     3,
    "LOW_CONVEXITY_BEAR":  2,
    "AVOID_SHORT":         1,
    "NOT_BEARISH_ALIGNED": 0,
}


# ── float safety ───────────────────────────────────────────────────────────────

def _sf(val: object, field: str = "", sid: str = "") -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        logger.warning("invalid_float", field=field, stock_id=sid)
        return None
    return f


# ── shortability metrics loader ────────────────────────────────────────────────

def _load_shortability_metrics(
    symbols: list[str],
    as_of: date_type,
) -> dict[str, dict]:
    """Load all Phase 2 shortability metrics for the given symbol list.

    Returns:
        Dict mapping stock_id → metrics dict.
    """
    if not symbols:
        return {}

    ph   = ",".join("?" * len(symbols))
    d365 = str(as_of - timedelta(days=365))   # ATR / vol percentile window
    d45  = str(as_of - timedelta(days=45))    # gap frequency (~30 trading days)
    d30  = str(as_of - timedelta(days=30))    # ROC5 lookback buffer
    d_as = str(as_of)

    with connect(read_only=True) as conn:

        # ── A1: ATR percentile (252d window) ─────────────────────────────
        # PERCENT_RANK() returns 0.0 for the minimum value in the window.
        # Stocks with extremely low or compressed ATR (e.g. post-halt, thin
        # float, or near-zero recent vol) will score 0%  — this is correct
        # behaviour, not a data gap.  Verify with atr_14 absolute value if
        # a stock consistently shows 0% across multiple dates.
        atr_rows = conn.execute(
            f"""
            WITH w AS (
                SELECT stock_id, date, atr_14
                FROM   daily_features
                WHERE  stock_id IN ({ph})
                  AND  date >= ?
                  AND  atr_14 IS NOT NULL
            )
            SELECT stock_id,
                   PERCENT_RANK() OVER (PARTITION BY stock_id ORDER BY atr_14) AS pctile
            FROM   w
            QUALIFY date = (SELECT MAX(date) FROM w w2 WHERE w2.stock_id = w.stock_id AND w2.date <= ?)
            """,
            symbols + [d365, d_as],
        ).fetchall()
        atr_pctile: dict[str, float] = {r[0]: r[1] for r in atr_rows}

        # ── A2: Downside gap count (last ~30 trading days) ────────────────
        # Gap-down threshold: adj_open < prev_close * 0.99 (1% gap).
        # Heuristic — filters out noise from minor auction price deviations.
        # 45 calendar days ≈ 30 trading days on Taiwan market.
        gap_rows = conn.execute(
            f"""
            WITH price_w_prev AS (
                SELECT stock_id, date, adj_open,
                       LAG(adj_close, 1) OVER (PARTITION BY stock_id ORDER BY date) AS prev_close
                FROM   daily_price_adj
                WHERE  stock_id IN ({ph})
                  AND  date >= ?
            )
            SELECT stock_id,
                   SUM(CASE WHEN prev_close IS NOT NULL
                                 AND adj_open < prev_close * 0.99
                            THEN 1 ELSE 0 END) AS down_gaps
            FROM   price_w_prev
            GROUP  BY stock_id
            """,
            symbols + [d45],
        ).fetchall()
        down_gaps: dict[str, int] = {r[0]: int(r[1]) for r in gap_rows}

        # ── B: Volume percentile (252d window) ────────────────────────────
        vol_rows = conn.execute(
            f"""
            WITH w AS (
                SELECT stock_id, date, rel_volume_20
                FROM   daily_features
                WHERE  stock_id IN ({ph})
                  AND  date >= ?
                  AND  rel_volume_20 IS NOT NULL
            )
            SELECT stock_id,
                   PERCENT_RANK() OVER (PARTITION BY stock_id ORDER BY rel_volume_20) AS pctile
            FROM   w
            QUALIFY date = (SELECT MAX(date) FROM w w2 WHERE w2.stock_id = w.stock_id AND w2.date <= ?)
            """,
            symbols + [d365, d_as],
        ).fetchall()
        vol_pctile: dict[str, float] = {r[0]: r[1] for r in vol_rows}

        # ── C: Sector relative weakness ───────────────────────────────────
        # roc_20 is stored as percentage (e.g., -9.7 = -9.7%)
        sector_rows = conn.execute(
            f"""
            WITH sector_med AS (
                SELECT cm.industry_code,
                       MEDIAN(f.roc_20) AS sector_median_roc
                FROM   daily_features f
                JOIN   company_metadata cm ON f.stock_id = cm.stock_id
                WHERE  f.date = ?
                  AND  f.roc_20 IS NOT NULL
                  AND  cm.industry_code IS NOT NULL
                GROUP  BY cm.industry_code
                HAVING COUNT(*) >= 3
            )
            SELECT f.stock_id,
                   f.roc_20,
                   s.sector_median_roc,
                   f.roc_20 - s.sector_median_roc AS relative_weakness
            FROM   daily_features f
            LEFT JOIN company_metadata cm ON f.stock_id = cm.stock_id
            LEFT JOIN sector_med s ON cm.industry_code = s.industry_code
            WHERE  f.stock_id IN ({ph})
              AND  f.date = ?
            """,
            [d_as] + symbols + [d_as],
        ).fetchall()
        relative_weakness: dict[str, tuple] = {
            r[0]: (r[1], r[2], r[3]) for r in sector_rows
        }  # stock_id → (roc_20, sector_median, rel_weakness)

        # ── D: Float proxy (issued_shares) ───────────────────────────────
        float_rows = conn.execute(
            f"SELECT stock_id, issued_shares FROM company_metadata WHERE stock_id IN ({ph})",
            symbols,
        ).fetchall()
        issued_shares: dict[str, int] = {r[0]: int(r[1]) for r in float_rows if r[1]}

        # ── E: ROC5 ──────────────────────────────────────────────────────
        roc5_rows = conn.execute(
            f"""
            WITH series AS (
                SELECT stock_id, date, adj_close,
                       LAG(adj_close, 5) OVER (PARTITION BY stock_id ORDER BY date) AS close_5d_ago
                FROM   daily_price_adj
                WHERE  stock_id IN ({ph})
                  AND  date >= ?
            )
            SELECT stock_id,
                   (adj_close / NULLIF(close_5d_ago, 0) - 1) * 100 AS roc_5
            FROM   series
            WHERE  date = ?
              AND  close_5d_ago IS NOT NULL
            """,
            symbols + [d30, d_as],
        ).fetchall()
        roc5: dict[str, float] = {r[0]: float(r[1]) for r in roc5_rows if r[1] is not None}

    # ── Assemble ──────────────────────────────────────────────────────────
    result: dict[str, dict] = {}
    for sym in symbols:
        rw = relative_weakness.get(sym, (None, None, None))
        result[sym] = {
            "atr_pctile":        atr_pctile.get(sym),
            "down_gaps_30d":     down_gaps.get(sym, 0),
            "vol_pctile":        vol_pctile.get(sym),
            "roc_20":            rw[0],
            "sector_median_roc": rw[1],
            "relative_weakness": rw[2],   # roc_20 - sector_median (% units)
            "issued_shares":     issued_shares.get(sym, 0),
            "roc_5":             roc5.get(sym),
        }
    return result


# ── scoring ────────────────────────────────────────────────────────────────────

def _compute_shortability_score(m: dict, sid: str = "") -> int:
    """Compute shortability score (0-100) from Phase 2 metrics."""
    score = 0

    atr_p  = _sf(m.get("atr_pctile"),        "atr_pctile",        sid)
    gaps   = int(m.get("down_gaps_30d") or 0)
    vol_p  = _sf(m.get("vol_pctile"),         "vol_pctile",        sid)
    rel_w  = _sf(m.get("relative_weakness"),  "relative_weakness", sid)
    shares = int(m.get("issued_shares") or 0)
    roc5   = _sf(m.get("roc_5"),              "roc_5",             sid)
    roc20  = _sf(m.get("roc_20"),             "roc_20",            sid)

    # ── A. Volatility (30 pts) ─────────────────────────────────────────
    # ATR percentile: high ATR = larger potential downside range
    if atr_p is not None:
        if atr_p >= 0.80:
            score += 20
        elif atr_p >= 0.60:
            score += 12
        elif atr_p >= 0.40:
            score += 6

    # Down gap frequency: crash tendency
    if gaps >= 3:
        score += 10
    elif gaps >= 2:
        score += 5

    # ── B. Liquidity (20 pts) ─────────────────────────────────────────
    if vol_p is not None:
        if vol_p >= 0.80:
            score += 20
        elif vol_p >= 0.60:
            score += 12
        elif vol_p >= 0.40:
            score += 6

    # ── C. Sector relative weakness (25 pts) ──────────────────────────
    # roc_20 stored as %, e.g. -9.7 = -9.7%
    # relative_weakness = stock_roc20 - sector_median_roc20 (same units)
    if rel_w is not None:
        if rel_w <= -15:
            score += 25
        elif rel_w <= -10:
            score += 18
        elif rel_w <= -5:
            score += 10
        elif rel_w <= -2:
            score += 5

    # ── D. Float proxy — necessary but NOT sufficient for borrow (15 pts)
    if shares >= 1_000_000_000:       # >= 10億股: large float
        score += 15
    elif shares >= 200_000_000:       # >= 2億股:  mid float
        score += 10
    elif shares >= 50_000_000:        # >= 5000萬: small-mid
        score += 5
    # < 5000萬: very small float, borrow likely unavailable → 0 pts

    # ── E. Momentum acceleration (10 pts) ─────────────────────────────
    if roc5 is not None and roc20 is not None:
        if roc5 < roc20 and roc5 < 0:    # accelerating decline
            score += 10
        elif roc5 < 0:
            score += 5

    return min(score, 100)


def _determine_label(shortability: int, bearish_label: str) -> str:
    """Determine shortability label with fixed priority order.

    Priority (checked top-down, first match wins):
        1. AVOID_SHORT:         shortability < 30
        2. NOT_BEARISH_ALIGNED: not in BEAR / STRONG_BEAR
        3. CRASH_PRONE_SHORT:   shortability >= 75
        4. SHORT_CANDIDATE:     shortability >= 50
        5. LOW_CONVEXITY_BEAR:  30 <= shortability < 50 AND bearish full align
                                (bearish trend, but weak short setup)
    """
    if shortability < 30:
        return "AVOID_SHORT"
    if bearish_label not in ("STRONG_BEAR", "BEAR"):
        return "NOT_BEARISH_ALIGNED"
    if shortability >= 75:
        return "CRASH_PRONE_SHORT"
    if shortability >= 50:
        return "SHORT_CANDIDATE"
    return "LOW_CONVEXITY_BEAR"


# ── main pipeline ──────────────────────────────────────────────────────────────

def score_short_candidates(
    as_of: date_type,
    min_bearish_score: int = _DEFAULT_MIN_BEARISH,
    min_short_score: int = _DEFAULT_MIN_SHORT,
) -> list[dict]:
    """Run Phase 1 (bearish filter) then Phase 2 (shortability scoring).

    Args:
        as_of: Evaluation date.
        min_bearish_score: Minimum Phase 1 score to enter Phase 2.
        min_short_score: Minimum shortability score to include in output.

    Returns:
        List of result dicts sorted by (label_priority DESC, shortability DESC).
    """
    # Phase 1
    bearish = find_bearish_stocks(as_of=as_of, min_score=min_bearish_score)
    if not bearish:
        return []

    symbols = [r["stock_id"] for r in bearish]
    logger.info("phase2_candidates", count=len(symbols), as_of=str(as_of))

    # Phase 2 metrics
    metrics = _load_shortability_metrics(symbols, as_of)

    results = []
    for r in bearish:
        sid = r["stock_id"]
        m = metrics.get(sid, {})
        short_score = _compute_shortability_score(m, sid)
        label = _determine_label(short_score, r["label"])

        if short_score < min_short_score:
            continue

        results.append({
            **r,
            **m,
            "shortability_score": short_score,
            "short_label": label,
        })

    return sorted(
        results,
        key=lambda x: (_LABEL_PRIORITY.get(x["short_label"], 0), x["shortability_score"]),
        reverse=True,
    )


# ── display ────────────────────────────────────────────────────────────────────


_TELEGRAM_LIMIT = 4096


def build_short_message(results: list[dict], as_of: date_type) -> str | None:
    """Build concise Telegram message from Phase 2 short candidate results.

    CRASH_PRONE_SHORT and SHORT_CANDIDATE shown with full detail.
    LOW_CONVEXITY_BEAR and AVOID_SHORT shown as symbol lists only.
    Returns None if no results.
    """
    if not results:
        return None

    _e = {
        "CRASH_PRONE_SHORT":   "🔴",
        "SHORT_CANDIDATE":     "🟠",
        "LOW_CONVEXITY_BEAR":  "🟡",
        "AVOID_SHORT":         "⚫",
        "NOT_BEARISH_ALIGNED": "⚪",
    }

    by_label: dict[str, list] = {}
    for r in results:
        by_label.setdefault(r["short_label"], []).append(r)

    lines = [f"🎯 空頭候選評分 ({as_of})"]

    # Full detail for actionable labels
    for label in ("CRASH_PRONE_SHORT", "SHORT_CANDIDATE"):
        group = by_label.get(label, [])
        e = _e.get(label, "")
        label_names = {"CRASH_PRONE_SHORT": "強空候選", "SHORT_CANDIDATE": "空頭候選"}
        if not group:
            lines.append(f"\n{e} {label_names[label]}: 無")
            continue
        lines.append(f"\n{e} {label_names[label]} ({len(group)})")
        for r in group:
            rw = r.get("relative_weakness")
            gaps = int(r.get("down_gaps_30d") or 0)
            rw_s = f"vs產業{rw:+.1f}%" if rw is not None else "vs產業N/A"
            lines.append(
                f"  {r['stock_id']} {r['name']}"
                f"  {r['close']:.2f}"
                f"  趨勢{r['score']} 空頭{r['shortability_score']}"
                f"  {rw_s}  {gaps}缺"
            )

    # Symbol list only for lower tiers
    for label in ("LOW_CONVEXITY_BEAR", "AVOID_SHORT"):
        group = by_label.get(label, [])
        if not group:
            continue
        e = _e.get(label, "")
        label_names = {"LOW_CONVEXITY_BEAR": "低凸性空頭", "AVOID_SHORT": "避免做空"}
        syms = " ".join(r["stock_id"] for r in group[:8])
        extra = f" +{len(group)-8}" if len(group) > 8 else ""
        lines.append(f"\n{e} {label_names[label]} ({len(group)}): {syms}{extra}")

    msg = "\n".join(lines)
    if len(msg) > _TELEGRAM_LIMIT:
        msg = msg[:_TELEGRAM_LIMIT - 20] + "\n...(截斷)"
    return msg


def _print_table(results: list[dict], as_of: date_type) -> None:
    if not results:
        print("無符合條件的個股")
        return

    _emoji = {
        "CRASH_PRONE_SHORT":   "🔴",
        "SHORT_CANDIDATE":     "🟠",
        "LOW_CONVEXITY_BEAR":  "🟡",
        "AVOID_SHORT":         "⚫",
        "NOT_BEARISH_ALIGNED": "⚪",
    }
    _label_hdr = {
        "CRASH_PRONE_SHORT":   "強空候選 — 高波動+弱勢+流動性",
        "SHORT_CANDIDATE":     "空頭候選 — 條件具備",
        "LOW_CONVEXITY_BEAR":  "低凸性空頭 — 趨勢弱但不易交易",
        "AVOID_SHORT":         "避免做空 — 流動性/波動不足",
        "NOT_BEARISH_ALIGNED": "非空頭排列",
    }

    col_hdr = (
        f"  {'代號':<6} {'名稱':<8}  {'趨勢':>4}  {'空頭':>4}"
        f"  {'ATR%':>5}  {'缺口':>4}  {'量%':>5}"
        f"  {'vs產業':>7}  {'ROC5':>6}  {'ROC20':>6}"
    )
    divider = "  " + "─" * 80

    print(f"\n📊 空頭候選評分 ({as_of})\n")
    print("  趨勢 = Phase 1 bearish score  |  空頭 = Phase 2 shortability score")

    prev_label = None
    for r in results:
        lbl = r["short_label"]
        if lbl != prev_label:
            e = _emoji.get(lbl, "")
            print(f"\n  {e} {_label_hdr.get(lbl, lbl)}")
            print(col_hdr)
            print(divider)
            prev_label = lbl

        atr_p = r.get("atr_pctile")
        vol_p = r.get("vol_pctile")
        rw    = r.get("relative_weakness")
        roc5  = r.get("roc_5")
        roc20 = r.get("roc_20")
        gaps  = int(r.get("down_gaps_30d") or 0)

        atr_s  = f"{atr_p*100:>4.0f}%" if atr_p is not None else "  N/A"
        vol_s  = f"{vol_p*100:>4.0f}%" if vol_p is not None else "  N/A"
        rw_s   = f"{rw:>+6.1f}%" if rw is not None else "   N/A"
        roc5_s = f"{roc5:>+5.1f}%" if roc5 is not None else "  N/A"
        roc20_s= f"{roc20:>+5.1f}%" if roc20 is not None else "  N/A"

        print(
            f"  {r['stock_id']:<6} {r['name']:<8}"
            f"  {r['score']:>4}  {r['shortability_score']:>4}"
            f"  {atr_s}  {gaps:>3}缺  {vol_s}"
            f"  {rw_s}  {roc5_s}  {roc20_s}"
        )

    by_label: dict[str, int] = {}
    for r in results:
        by_label[r["short_label"]] = by_label.get(r["short_label"], 0) + 1

    print(f"\n  共 {len(results)} 檔")
    for lbl, cnt in sorted(by_label.items(), key=lambda x: _LABEL_PRIORITY.get(x[0], 0), reverse=True):
        print(f"    {_emoji.get(lbl,'')} {lbl}: {cnt} 檔")

    print("\n  ⚠️  空頭分數是可交易性指標，不是做空訊號。")
    print("     float proxy ≠ 實際借券可得性。進場前確認券源與 spread。")
    print("     機構流向 (三大法人) 資料目前無法取得，待日後補入。")


# ── entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="v0.1.15 short candidate scorer")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--min-bearish", type=int, default=_DEFAULT_MIN_BEARISH,
                        help=f"Min Phase 1 bearish score (default {_DEFAULT_MIN_BEARISH})")
    parser.add_argument("--min-short", type=int, default=_DEFAULT_MIN_SHORT,
                        help=f"Min Phase 2 shortability score (default {_DEFAULT_MIN_SHORT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print only, do not send Telegram")
    args = parser.parse_args()

    if args.as_of is None:
        today = date_type.today()
        if not is_trading_day(today):
            logger.info("short_score_non_trading_day", date=str(today))
            print(f"{today} is not a trading day; exiting")
            return 0

    as_of = resolve_as_of(args.as_of)
    logger.info("short_score_start", as_of=str(as_of))

    results = score_short_candidates(
        as_of=as_of,
        min_bearish_score=args.min_bearish,
        min_short_score=args.min_short,
    )
    _print_table(results, as_of)

    if not args.dry_run:
        message = build_short_message(results, as_of)
        if message:
            tg_cfg = TelegramConfig.from_env()
            if tg_cfg:
                bot = TelegramBot(tg_cfg)
                push_simple(bot, message)
                logger.info("short_score_sent", as_of=str(as_of))

    logger.info("short_score_done", count=len(results), as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
