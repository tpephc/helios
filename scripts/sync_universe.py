#!/usr/bin/env python3
# scripts/sync_universe.py
"""Dynamic universe management — v0.1.0 (2026-05-20, v0.1.15).

Fetches current market cap rankings from FinMind (TaiwanStockMarketValue),
selects top-N TWSE-listed common stocks, diffs against the current
`dynamic_top200` section of config/universe.yaml, and optionally commits
the changes.

Design constraints
------------------
- Only manages the `dynamic_top200` section of universe.yaml.
  The curated `universes:` section (blue_chip_etf / sector_etf /
  mid_cap_momentum) is never touched.
- ETFs (stock_id starts with 0 in Taiwan) are excluded from the
  market-cap ranking but remain in the curated section.
- Symbols removed from top-N that have an OPEN position in the DB are
  placed in `protected` status: kept in dynamic_top200.symbols for data
  continuity and exit-scan coverage, but flagged in universe_snapshot
  with passed=False so generate_signals skips them for new entries.
- Logs every rebalance to universe_snapshot (existing DB table).
- Default mode: --dry-run (no writes). Use --commit to apply changes.

Usage
-----
    # Preview (safe — no writes)
    uv run python scripts/sync_universe.py

    # Commit changes to universe.yaml + DB
    uv run python scripts/sync_universe.py --commit

    # Different top-N
    uv run python scripts/sync_universe.py --top 100 --commit

Version: v0.1.0 (2026-05-20 — initial implementation)
"""
from __future__ import annotations

import httpx

import argparse
import sys
from datetime import date as date_type
from datetime import datetime
from pathlib import Path

import yaml

from data.database import connect, init_schema
from portfolio.selector import is_etf
from utils.logger import get_logger

logger = get_logger(__name__)

_UNIVERSE_PATH = Path(__file__).parent.parent / "config" / "universe.yaml"
_DYNAMIC_KEY = "dynamic_top200"


# ─────────────────────────────────────────────────────────────
# Market cap fetch
# ─────────────────────────────────────────────────────────────


def _fetch_market_cap_twse(
    top_n: int,
    exclude_etf: bool,
) -> list[str]:
    """Fetch top-N TWSE stocks by market cap via TWSE Open API.

    Primary: BWIBBU_ALL (has MarketValue directly, one call)
    Fallback: t187ap03_L (已發行普通股數) × STOCK_DAY_ALL (ClosingPrice)
    """
    base = "https://openapi.twse.com.tw/v1"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    def _clean(s: str) -> float:
        try:
            return float(str(s).replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0

    # ── Primary: BWIBBU_ALL ──────────────────────────────────
    try:
        r = httpx.get(f"{base}/exchangeReport/BWIBBU_ALL", headers=headers, timeout=30)
        r.raise_for_status()
        rows = r.json()
        if rows:
            logger.info("twse_bwibbu_fetched",
                        rows=len(rows), sample_keys=list(rows[0].keys()))
        cap_list: list[tuple[str, float]] = []
        for row in rows:
            sid = str(row.get("Code") or row.get("股票代號") or "").strip()
            mv = _clean(row.get("MarketValue") or row.get("市值") or 0)
            if not sid or mv <= 0:
                continue
            if exclude_etf and is_etf(sid):
                continue
            cap_list.append((sid, mv))
        if cap_list:
            cap_list.sort(key=lambda x: x[1], reverse=True)
            result = [s for s, _ in cap_list[:top_n]]
            logger.info("twse_bwibbu_ranked", total=len(cap_list), top_n=len(result))
            return result
        logger.warning("twse_bwibbu_no_market_value",
                       hint="MarketValue field missing — trying fallback")
    except Exception as e:
        logger.warning("twse_bwibbu_failed", error=str(e))

    # ── Fallback: t187ap03_L × STOCK_DAY_ALL ────────────────
    try:
        r1 = httpx.get(f"{base}/opendata/t187ap03_L", headers=headers, timeout=30)
        r1.raise_for_status()
        company_rows = r1.json()
        r2 = httpx.get(f"{base}/exchangeReport/STOCK_DAY_ALL", headers=headers, timeout=30)
        r2.raise_for_status()
        price_rows = r2.json()
        if company_rows:
            logger.info("twse_t187_columns", cols=list(company_rows[0].keys()))
        if price_rows:
            logger.info("twse_day_columns", cols=list(price_rows[0].keys()))
        close_map: dict[str, float] = {}
        for row in price_rows:
            sid = str(row.get("Code") or "").strip()
            c = _clean(row.get("ClosingPrice") or 0)
            if sid and c > 0:
                close_map[sid] = c
        cap_list2: list[tuple[str, float]] = []
        for row in company_rows:
            sid = str(row.get("公司代號") or "").strip()
            shares = _clean(row.get("已發行普通股數或TDR原股發行股數") or 0)
            if not sid or shares <= 0:
                continue
            if exclude_etf and is_etf(sid):
                continue
            close = close_map.get(sid, 0.0)
            if close <= 0:
                continue
            cap_list2.append((sid, shares * close))
        cap_list2.sort(key=lambda x: x[1], reverse=True)
        result2 = [s for s, _ in cap_list2[:top_n]]
        logger.info("twse_fallback_ranked", total=len(cap_list2), top_n=len(result2))
        return result2
    except Exception as e:
        logger.warning("twse_fallback_failed", error=str(e))
        return []


def _fetch_market_cap(
    top_n: int,
    market: str,
    exclude_etf: bool,
    on_date: date_type,
) -> list[str]:
    """Wrapper: fetch top-N market cap symbols."""
    symbols = _fetch_market_cap_twse(top_n=top_n, exclude_etf=exclude_etf)
    if not symbols:
        logger.warning(
            "sync_universe_no_symbols",
            hint="TWSE API unavailable or returned no data.",
        )
    return symbols


# ─────────────────────────────────────────────────────────────
# Position protection
# ─────────────────────────────────────────────────────────────


def _open_position_symbols() -> set[str]:
    """Return set of symbols with currently OPEN positions (any account).

    v0.1.18 note: intentionally NOT filtered by account_id. Universe
    membership is shared across all accounts. If ANY account has an open
    position in a symbol, it must remain in the universe for data
    continuity and exit-scan coverage.
    """
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM positions WHERE status = 'OPEN'"
        ).fetchall()
    return {r[0] for r in rows}


# ─────────────────────────────────────────────────────────────
# universe.yaml read / write
# ─────────────────────────────────────────────────────────────


def _load_yaml() -> dict:
    return yaml.safe_load(_UNIVERSE_PATH.read_text(encoding="utf-8")) or {}


def _save_yaml(data: dict) -> None:
    _UNIVERSE_PATH.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _current_dynamic_symbols(data: dict) -> list[str]:
    return list(data.get(_DYNAMIC_KEY, {}).get("symbols", []))


# ─────────────────────────────────────────────────────────────
# DB logging
# ─────────────────────────────────────────────────────────────


def _log_to_db(
    snapshot_date: date_type,
    symbols_in: set[str],
    symbols_protected: set[str],
    symbols_removed: set[str],
) -> None:
    """Write rebalance results to universe_snapshot table."""
    rows = []
    for sid in sorted(symbols_in):
        rows.append((snapshot_date, _DYNAMIC_KEY, sid, None, None, None, True, None))
    for sid in sorted(symbols_protected):
        rows.append((
            snapshot_date, _DYNAMIC_KEY, sid, None, None, None, False,
            "protected: open position",
        ))
    for sid in sorted(symbols_removed):
        rows.append((
            snapshot_date, _DYNAMIC_KEY, sid, None, None, None, False,
            "removed: outside top-N",
        ))
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO universe_snapshot
              (snapshot_date, universe_name, stock_id,
               avg_turnover_20d, avg_volume_20d, days_traded_60d,
               passed, reject_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    logger.info(
        "universe_snapshot_written",
        date=str(snapshot_date),
        universe=_DYNAMIC_KEY,
        in_universe=len(symbols_in),
        protected=len(symbols_protected),
        removed=len(symbols_removed),
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v0.1.0 dynamic universe rebalance"
    )
    parser.add_argument("--top", type=int, default=200,
                        help="top-N symbols by market cap (default 200)")
    parser.add_argument("--market", default="TWSE",
                        help="exchange filter (default TWSE)")
    parser.add_argument("--date", type=str, default=None,
                        help="market cap date YYYY-MM-DD (default: today)")
    parser.add_argument("--commit", action="store_true",
                        help="write changes to universe.yaml + DB (default: dry-run)")
    args = parser.parse_args(argv)

    dry_run = not args.commit
    as_of = date_type.fromisoformat(args.date) if args.date else date_type.today()

    init_schema()
    print(
        f"Helios sync_universe — {datetime.now().isoformat(timespec='seconds')}  "
        f"as_of={as_of}  top={args.top}  "
        f"{'DRY-RUN' if dry_run else 'COMMIT'}"
    )


    new_symbols = _fetch_market_cap(
        top_n=args.top,
        market=args.market,
        exclude_etf=True,
        on_date=as_of,
    )

    if not new_symbols:
        print(
            "❌ No market cap data returned — check FinMind token / date / API tier.\n"
            "   Run with a past trading day: --date 2026-05-19"
        )
        return 1

    print(f"\nFetched {len(new_symbols)} symbols from TWSE (top {args.top})")

    data = _load_yaml()
    current = set(_current_dynamic_symbols(data))
    new_set = set(new_symbols)
    open_pos = _open_position_symbols()

    added = new_set - current
    raw_removed = current - new_set
    protected = raw_removed & open_pos   # removed but has open position → keep
    removed = raw_removed - protected    # truly removed

    # Final symbol list = new top-N + protected (still held)
    final_symbols = sorted(new_set | protected)

    # ── Print diff report ────────────────────────────────────
    print(f"\n{'─'*52}")
    print(f"  Current dynamic universe:  {len(current):>4} symbols")
    print(f"  New top-{args.top} from FinMind:  {len(new_set):>4} symbols")
    print(f"{'─'*52}")
    if added:
        print(f"  ✅ Added   ({len(added):>3}): {', '.join(sorted(added)[:20])}"
              + (" ..." if len(added) > 20 else ""))
    else:
        print("  ✅ Added   (  0): —")
    if removed:
        print(f"  ❌ Removed ({len(removed):>3}): {', '.join(sorted(removed)[:20])}"
              + (" ..." if len(removed) > 20 else ""))
    else:
        print("  ❌ Removed (  0): —")
    if protected:
        print(f"  🔒 Protected ({len(protected):>2}): {', '.join(sorted(protected))} "
              f"(open position — kept in universe until natural exit)")
    print(f"{'─'*52}")
    print(f"  Final dynamic_top200: {len(final_symbols)} symbols")

    if dry_run:
        print(
            "\n(DRY-RUN: no changes written. Use --commit to apply.)"
        )
        return 0

    # ── Commit ───────────────────────────────────────────────
    if _DYNAMIC_KEY not in data:
        data[_DYNAMIC_KEY] = {}
    data[_DYNAMIC_KEY]["last_rebalance"] = as_of.isoformat()
    data[_DYNAMIC_KEY]["top_n"] = args.top
    data[_DYNAMIC_KEY]["market"] = args.market
    data[_DYNAMIC_KEY]["exclude_etf"] = True
    data[_DYNAMIC_KEY]["symbols"] = final_symbols
    _save_yaml(data)
    print(f"\n✅ universe.yaml updated — dynamic_top200.symbols = {len(final_symbols)}")

    _log_to_db(as_of, new_set, protected, removed)

    # Trigger incremental download for newly added symbols
    if added:
        print(f"\n📥 Triggering download for {len(added)} new symbols...")
        import subprocess, sys
        subprocess.run(
            [sys.executable, "scripts/download_daily.py",
             "--symbols", ",".join(sorted(added))],
            check=True,
        )
        print("   Build adjusted prices + features for new symbols:")
        print(f"   uv run python scripts/build_adjusted_prices.py --symbols {','.join(sorted(added))}")
        print(f"   uv run python scripts/compute_features.py --symbols {','.join(sorted(added))}")

    logger.info(
        "sync_universe_complete",
        as_of=str(as_of),
        added=len(added),
        removed=len(removed),
        protected=len(protected),
        final_count=len(final_symbols),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
