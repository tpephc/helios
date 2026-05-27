# Helios `scripts/daily_run.py` Patch — v0.1.16 (v2)

**Target:** `scripts/daily_run.py`
**Base:** v0.1.14.3 (Git HEAD `cc33fa6`)
**Target:** v0.1.16

v2 changes from v1:
- Step 0a passes `as_of` and an `is_trading_day` predicate to
  `recover_in_flight_orders` (C-P0-5 trading-calendar awareness).
- Step 7 uses unit-bearing field names (`requested_lots`, `filled_shares`).
- LiveBroker instantiation uses `PreTradeGuard.sim_relaxed()` when
  `simulation=True` (decision 2: week-1 sim cap relaxation).

---

## Two edits + one new file

### Edit 1: Insert Step 0a (startup_recovery)

Locate this section (around line 47):

```python
    with shutdown_guard(as_of, telegram_notify=telegram_notify) as guard:
        # ── Step 0: prev-run check ────────────────────────
        if not args.ignore_prev_check:
            ok, msg = check_previous_run(as_of)
            print(f"[0] {msg}")
            if not ok:
                raise PreflightDecline(f"prev_check_failed: {msg}")
```

Replace with:

```python
    # ── Step 0a: startup recovery (BEFORE shutdown_guard) ───────────────────
    # Resolves in-flight orders from a previous (possibly crashed) process.
    # Runs before shutdown_guard because shutdown_guard's prev_check assumes
    # the journal is in a consistent state — startup_recovery establishes that.
    #
    # v2 (C-P0-5): passes as_of + trading-day predicate so stale-SUBMITTED
    # detection uses fill_date semantics, NOT wall-clock 16h (which misfires
    # over weekends).
    from scripts.startup_recovery import recover_in_flight_orders
    from utils.trading_calendar import is_trading_day  # see "New file" below

    recovery_summary = recover_in_flight_orders(
        as_of=as_of,
        is_trading_day=is_trading_day,
        notify=telegram_notify,
    )
    print(
        f"[0a] startup_recovery: "
        f"orphan_intents={recovery_summary['orphan_intents_resolved']} "
        f"stale_submitted={recovery_summary['stale_submitted_resolved']}"
    )
    if recovery_summary['resolution_errors']:
        print(
            f"[0a] WARNING: {len(recovery_summary['resolution_errors'])} "
            f"recovery operations FAILED — check logs"
        )

    with shutdown_guard(as_of, telegram_notify=telegram_notify) as guard:
        # ── Step 0b: prev-run check ───────────────────────
        if not args.ignore_prev_check:
            ok, msg = check_previous_run(as_of)
            print(f"[0b] {msg}")
            if not ok:
                raise PreflightDecline(f"prev_check_failed: {msg}")
```

### Edit 2: Step 7 — use `position_opened` + new field names

Locate Step 7 (around line 122). Replace with:

```python
        # ── Step 7: auto-execute entry signals via LiveBroker ────────────
        # v0.1.16: use result.position_opened (NOT result.success) to decide
        # whether to count as executed. SUBMITTED-but-unfilled orders are
        # tracked as 'pending_reconcile'.
        # v2: uses sim_relaxed guard config when in simulation mode.
        from execution.live_broker import LiveBroker
        from execution.pre_trade_guard import PreTradeGuard
        from config.settings import get_settings

        cfg = get_settings()
        if cfg.shioaji_simulation:
            # Week-1 sim threshold relaxation (decision 2)
            guard_config = PreTradeGuard.sim_relaxed()
            logger.info(
                "daily_run_using_sim_relaxed_guard",
                max_order_notional=guard_config.max_order_notional,
                max_daily_notional=guard_config.max_daily_notional,
            )
        else:
            # Production — strict thresholds
            guard_config = PreTradeGuard()

        exec_summary = {
            "executed": [],            # FILLED, position opened
            "pending_reconcile": [],   # SUBMITTED, awaiting fill
            "failed": [],              # FAILED, PARTIAL, CANCELLED, EXPIRED
        }
        if pending:
            broker = LiveBroker(bot=bot, guard=guard_config)
            for sig in pending:
                symbol = sig.get("stock_id") or sig.get("symbol", "")
                signal_id = sig.get("signal_id") or sig.get("id", "")
                if not symbol:
                    logger.warning("daily_run_skip_no_symbol", sig=str(sig))
                    exec_summary["failed"].append(symbol)
                    continue
                result = broker.submit_buy(
                    symbol=symbol,
                    lots=1,           # v0.1.16: Common lot only
                    fill_date=fill_date,
                    signal_id=signal_id,
                )
                if result.position_opened:
                    exec_summary["executed"].append(symbol)
                    logger.info(
                        "daily_run_entry_executed",
                        symbol=symbol, status=result.status.value,
                        price=result.avg_fill_price,
                        filled_shares=result.filled_shares,
                        order_id=result.order_id,
                    )
                elif result.is_pending:
                    exec_summary["pending_reconcile"].append(symbol)
                    logger.warning(
                        "daily_run_entry_pending_reconcile",
                        symbol=symbol, status=result.status.value,
                        order_id=result.order_id,
                        broker_order_id=result.broker_order_id,
                    )
                else:
                    exec_summary["failed"].append(symbol)
                    logger.warning(
                        "daily_run_entry_failed",
                        symbol=symbol, status=result.status.value,
                        error_code=result.error_code,
                        error_message=result.error_message,
                        order_id=result.order_id,
                    )
            print(
                f"[7] executed={len(exec_summary['executed'])} "
                f"pending_reconcile={len(exec_summary['pending_reconcile'])} "
                f"failed={len(exec_summary['failed'])}"
            )
        else:
            print("[7] no pending signals, skip execution")
```

### Edit 3: Update summary block

Locate the `guard.set_summary(...)` call. Replace with:

```python
        # ── Summary (v0.1.16 v2: + recovery + pending_reconcile fields) ──
        guard.set_summary({
            "exits": exit_summary["exits_fired"],
            "pending_pushed": len(pending),
            "executed": len(exec_summary["executed"]),
            "pending_reconcile": len(exec_summary["pending_reconcile"]),
            "failed_entries": len(exec_summary["failed"]),
            "reconciliation": "skipped" if recon.skipped else "ran",
            # v0.1.16 startup_recovery counts
            "recovery_orphan_intents":
                recovery_summary["orphan_intents_resolved"],
            "recovery_stale_submitted":
                recovery_summary["stale_submitted_resolved"],
            "recovery_errors":
                len(recovery_summary["resolution_errors"]),
            # Sim guard mode flag (Telegram surfacing)
            "guard_mode": (
                "sim_relaxed" if cfg.shioaji_simulation else "production"
            ),
            **{k: exit_summary[k] for k in ("exits_failed", "exits_failed_symbols",
                "skipped_no_data", "skipped_no_data_symbols", "open_position_days",
                "avg_position_days", "max_position_days")},
        })
```

---

## New file: `utils/trading_calendar.py`

Helios may already have a `is_trading_day` utility somewhere; v2 makes
that dependency explicit. If your codebase already has one, point Step
0a's import at it. Otherwise, this minimal stub gets you started:

```python
# utils/trading_calendar.py
"""Trading calendar predicates — v0.1.16.

Minimal implementation. For production, replace with a calendar that
consults company_metadata or a TWSE holiday table.
"""
from __future__ import annotations

from datetime import date


# Stub: weekday-only. Replace with full TWSE calendar before live trading.
def is_trading_day(d: date) -> bool:
    """Return True if d is a Taiwan stock market trading day.

    v0.1.16 minimum: weekday check only (Mon=0 ... Fri=4).
    Does NOT account for Taiwan public holidays. Operator MUST replace
    this before enabling live_trading_enabled=True.
    """
    return d.weekday() < 5
```

---

## Manual verification

After applying patches:

```bash
cd ~/projects/helios

# Syntax check
uv run python -c "from scripts.startup_recovery import recover_in_flight_orders; print('OK')"
uv run python -m py_compile scripts/daily_run.py
uv run python -c "from utils.trading_calendar import is_trading_day; print(is_trading_day.__doc__)"

# Dry-run (no broker calls expected if no pending signals)
HELIOS_SKIP_EXIT_SCAN=true uv run python scripts/daily_run.py \
    --as-of 2026-05-23 \
    --no-listener \
    --ignore-prev-check 2>&1 | head -30

# Expected output:
#   [0a] startup_recovery: orphan_intents=0 stale_submitted=0
#   [0b] prev_check_passed
#   ...
#   [7] executed=0 pending_reconcile=0 failed=0
```
