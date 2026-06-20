#!/usr/bin/env python3
# scripts/find_bullish_setups.py
"""Bullish setup candidate screener — v0.1.0.

Lists stocks from the dynamic_top200 universe that show accumulation
or markup conditions based on bullish_features temporal observations.

IMPORTANT DESIGN CONSTRAINT:
  This script lists CANDIDATES ONLY. It does NOT:
  - Assign scores or composite rankings
  - Replace or modify trend_breakout_v1 signal generation
  - Make entry recommendations

  The correct sequence (per backlog #18/#19) is:
    1. Observe candidates from this screener
    2. Run forward outcome study (research/bullish_feature_outcomes.py)
    3. Calibrate thresholds from outcome evidence
    4. Build entry_classifier AFTER calibration

  Using this screener's output as an entry signal before step 3
  is using [ASSUMED] thresholds as production logic — do not do this.

Output: a table of symbols meeting minimum feature thresholds,
grouped by pattern profile. All thresholds are [ASSUMED].

Usage:
  uv run python scripts/find_bullish_setups.py
  uv run python scripts/find_bullish_setups.py --as-of 2026-05-22
  uv run python scripts/find_bullish_setups.py --dry-run

Version: v0.1.0 (2026-05-26)
Changelog:
  v0.1.0 (2026-05-26): Initial — candidate listing without scoring.
    Mirrors find_bearish_stocks.py v0.1.15 discipline.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as date_type
from pathlib import Path

import yaml

from data.database import connect
from communication.telegram import TelegramBot, TelegramConfig
from communication.telegram.sender import push_simple
from utils.logger import get_logger
from utils.trading_dates import resolve_as_of
from market.trading_calendar import is_trading_day

logger = get_logger(__name__)

_DEFAULT_MIN_STREAK = 3      # min above_ma20_streak to appear in results
_MAX_RESULTS = 50
_MAX_TELEGRAM_ROWS = 15
_TELEGRAM_LIMIT = 4096

# [ASSUMED] thresholds — all pending calibration via backlog #18 methodology
_THRESHOLDS = {
    # Compression profile: base formation candidates
    "compression": {
        "above_ma20_streak_min": 3,
        "volume_contraction_days_10d_min": 4,    # at least 4/10 days vol < 0.7x
        "tight_range_days_10d_min": 4,           # at least 4/10 days ATR compressed
        "atr_compression_ratio_max": 0.85,       # current ATR below baseline
    },
    # Reclaim profile: MA reclaim after a dip
    "reclaim": {
        "ma20_reclaim_confirmed_min": 1,         # reclaim confirmed >= 1 day ago
        "above_ma20_streak_min": 3,
        "failed_breakdown_count_10d_min": 1,     # at least 1 demand absorption event
    },
    # Momentum profile: breakout with volume
    "momentum": {
        "above_ma20_streak_min": 5,
        "volume_breakout_days_5d_min": 2,        # at least 2 high-vol up days
        "above_ma50_streak_min": 3,
    },
}


def find_bullish_setups(
    as_of: date_type,
) -> list[dict]:
    """Screen dynamic_top200 for bullish setup candidates on as_of date.

    Returns list of dicts with feature values and profile classifications.
    Multiple profiles can match the same symbol.
    """
    cfg_path = Path("config/universe.yaml")
    try:
        with cfg_path.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("universe_config_missing", path=str(cfg_path))
        raise

    universe: list[str] = cfg["dynamic_top200"]["symbols"]
    if not universe:
        raise ValueError("dynamic_top200.symbols is empty")

    placeholders = ",".join("?" * len(universe))

    query = (
        "SELECT"
        "    b.stock_id, b.date,"
        "    p.adj_close                                     AS close,"
        "    f.sma_20, f.sma_50, f.sma_200,"
        "    f.rsi_14, f.roc_20,"
        "    b.above_ma20_streak,"
        "    b.above_ma50_streak,"
        "    b.ma20_reclaim_confirmed,"
        "    b.ma50_reclaim_confirmed,"
        "    b.volume_contraction_days_10d,"
        "    b.tight_range_days_10d,"
        "    b.volume_breakout_days_5d,"
        "    b.failed_breakdown_count_10d,"
        "    b.beta_adj_rs_20d,"
        "    b.atr_compression_ratio,"
        "    b.atr_compression_days_10d,"
        "    COALESCE(cm.short_name, b.stock_id) AS name"
        " FROM   bullish_features b"
        " JOIN   daily_price_adj p"
        "        ON b.stock_id = p.stock_id AND b.date = p.date"
        " JOIN   daily_features f"
        "        ON b.stock_id = f.stock_id AND b.date = f.date"
        " LEFT JOIN company_metadata cm ON b.stock_id = cm.stock_id"
        " WHERE  b.stock_id IN (" + placeholders + ")"
        "   AND  b.date = ?"
        "   AND  b.above_ma20_streak >= ?"
    )

    with connect(read_only=True) as conn:
        rows = conn.execute(
            query,
            universe + [str(as_of), _DEFAULT_MIN_STREAK],
        ).fetchall()

    columns = [
        "stock_id", "date", "close",
        "sma_20", "sma_50", "sma_200",
        "rsi_14", "roc_20",
        "above_ma20_streak", "above_ma50_streak",
        "ma20_reclaim_confirmed", "ma50_reclaim_confirmed",
        "volume_contraction_days_10d", "tight_range_days_10d",
        "volume_breakout_days_5d", "failed_breakdown_count_10d",
        "beta_adj_rs_20d", "atr_compression_ratio",
        "atr_compression_days_10d", "name",
    ]

    results = []
    for row in rows:
        r = dict(zip(columns, row))
        profiles = _classify_profiles(r)
        if not profiles:
            continue
        r["profiles"] = profiles
        results.append(r)

    # Sort: symbols matching more profiles first, then by above_ma20_streak
    # NOTE: above_ma20_streak is NOT forward-return validated (R5 Section C,
    # 2026-05). Spearman mildly negative, CI spans zero. Current sort is a
    # heuristic, not evidence-backed. Consider volume_contraction_days_10d.
    results.sort(
        key=lambda x: (len(x["profiles"]), x["above_ma20_streak"] or 0),
        reverse=True,
    )

    if len(results) > _MAX_RESULTS:
        logger.warning("results_truncated", total=len(results), kept=_MAX_RESULTS)
        results = results[:_MAX_RESULTS]

    return results


def _classify_profiles(r: dict) -> list[str]:
    """Return list of matching profile names for one feature row."""
    matching = []

    # Compression profile
    c = _THRESHOLDS["compression"]
    if (
        _ge(r.get("above_ma20_streak"), c["above_ma20_streak_min"])
        and _ge(r.get("volume_contraction_days_10d"), c["volume_contraction_days_10d_min"])
        and _ge(r.get("tight_range_days_10d"), c["tight_range_days_10d_min"])
        and _le(r.get("atr_compression_ratio"), c["atr_compression_ratio_max"])
    ):
        matching.append("COMPRESSION")

    # Reclaim profile
    rc = _THRESHOLDS["reclaim"]
    if (
        _ge(r.get("ma20_reclaim_confirmed"), rc["ma20_reclaim_confirmed_min"])
        and _ge(r.get("above_ma20_streak"), rc["above_ma20_streak_min"])
        and _ge(r.get("failed_breakdown_count_10d"), rc["failed_breakdown_count_10d_min"])
    ):
        matching.append("RECLAIM")

    # Momentum profile
    m = _THRESHOLDS["momentum"]
    if (
        _ge(r.get("above_ma20_streak"), m["above_ma20_streak_min"])
        and _ge(r.get("volume_breakout_days_5d"), m["volume_breakout_days_5d_min"])
        and _ge(r.get("above_ma50_streak"), m["above_ma50_streak_min"])
    ):
        matching.append("MOMENTUM")

    return matching


def _ge(val: object, threshold: float) -> bool:
    """Safe >= comparison, returns False on None."""
    try:
        return float(val) >= threshold  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _le(val: object, threshold: float) -> bool:
    """Safe <= comparison, returns False on None."""
    try:
        return float(val) <= threshold  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _fmt(v: float | None, dec: int = 2) -> str:
    return "N/A" if v is None else f"{v:.{dec}f}"


def _print_table(results: list[dict], as_of: date_type) -> None:
    if not results:
        print("無符合條件的候選股")
        return

    _profile_emoji = {
        "COMPRESSION": "🔵",
        "RECLAIM": "🟢",
        "MOMENTUM": "🚀",
    }

    print(f"\n📈 多頭候選列表 ({as_of})")
    print(f"   ⚠️  [ASSUMED] thresholds — do NOT use as entry signals before backlog #18 calibration\n")

    _col_hdr = (
        f"  {'代號':<6} {'名稱':<8}  {'Profile':<18}"
        f"  {'收盤':>8}  {'MA20連':>6}  {'量縮10':>6}  {'壓縮10':>6}"
        f"  {'ATR比':>6}  {'量爆5':>5}  {'RS20':>6}  {'RSI':>5}"
    )
    print(_col_hdr)
    print("  " + "─" * 100)

    for r in results:
        profile_str = " ".join(
            _profile_emoji.get(p, p) + p for p in r["profiles"]
        )
        rs = r.get("beta_adj_rs_20d")
        rs_str = f"{rs:+.1f}%" if rs is not None else "  N/A"
        atr_c = r.get("atr_compression_ratio")
        atr_str = f"{atr_c:.2f}" if atr_c is not None else " N/A"

        print(
            f"  {r['stock_id']:<6} {r['name']:<8}"
            f"  {profile_str:<18}"
            f"  {r['close']:>8.2f}"
            f"  {r['above_ma20_streak'] or 0:>6d}"
            f"  {r['volume_contraction_days_10d'] or 0:>6d}"
            f"  {r['tight_range_days_10d'] or 0:>6d}"
            f"  {atr_str:>6}"
            f"  {r['volume_breakout_days_5d'] or 0:>5d}"
            f"  {rs_str:>6}"
            f"  {_fmt(r['rsi_14'], 1):>5}"
        )

    profile_counts: dict[str, int] = {}
    for r in results:
        for p in r["profiles"]:
            profile_counts[p] = profile_counts.get(p, 0) + 1

    summary = "  ".join(
        f"{_profile_emoji.get(p, '')}{p}={v}"
        for p, v in sorted(profile_counts.items())
    )
    print(f"\n  共 {len(results)} 檔候選   {summary}")
    print(
        "\n  Profiles: COMPRESSION=壓縮基底  RECLAIM=均線收復  MOMENTUM=放量突破"
    )
    print("  ⚠️  以上為觀察候選，非進場訊號。需完成 backlog #18 outcome study 後才能校準。")


def build_bullish_message(results: list[dict], as_of: date_type) -> str | None:
    if not results:
        return None

    _pe = {"COMPRESSION": "🔵", "RECLAIM": "🟢", "MOMENTUM": "🚀"}
    total = len(results)
    lines = [
        f"📈 多頭候選 ({as_of})  共 {total} 檔",
        "⚠️ [ASSUMED] thresholds — 觀察用，非進場訊號",
    ]

    shown = results[:_MAX_TELEGRAM_ROWS]
    for r in shown:
        p_str = "".join(_pe.get(p, p[0]) for p in r["profiles"])
        rs = r.get("beta_adj_rs_20d")
        rs_str = f"RS{rs:+.0f}%" if rs is not None else ""
        lines.append(
            f"  {p_str} {r['stock_id']} {r['name']}"
            f"  {r['close']:.2f}"
            f"  MA20+{r['above_ma20_streak'] or 0}d"
            f"  {rs_str}"
        )
    if len(results) > _MAX_TELEGRAM_ROWS:
        lines.append(f"  ...其餘 {len(results) - _MAX_TELEGRAM_ROWS} 檔")

    msg = "\n".join(lines)
    if len(msg) > _TELEGRAM_LIMIT:
        msg = msg[:_TELEGRAM_LIMIT - 20] + "\n...(截斷)"
    return msg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.1.0 bullish setup candidate screener"
    )
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print only, do not send Telegram")
    args = parser.parse_args()

    if args.as_of is None:
        today = date_type.today()
        if not is_trading_day(today):
            logger.info("bullish_setups_non_trading_day", date=str(today))
            print(f"{today} is not a trading day; exiting")
            return 0

    as_of = resolve_as_of(args.as_of)
    logger.info("bullish_setups_start", as_of=str(as_of))

    results = find_bullish_setups(as_of=as_of)
    _print_table(results, as_of)

    if not args.dry_run:
        message = build_bullish_message(results, as_of)
        if message:
            tg_cfg = TelegramConfig.from_env()
            if tg_cfg:
                bot = TelegramBot(tg_cfg)
                push_simple(bot, message)
                logger.info("bullish_setups_sent", as_of=str(as_of))

    logger.info("bullish_setups_done", count=len(results), as_of=str(as_of))
    return 0


if __name__ == "__main__":
    sys.exit(main())
