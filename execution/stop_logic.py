# execution/stop_logic.py
"""Trailing-stop level computation — v0.1.15.

Shared between ``run_exit_scan.py`` (EOD) and ``monitoring/intraday_monitor.py``
(intraday).  All thresholds are expressed in units of ``entry_atr``, which is
frozen at position entry and does not drift with current volatility.

Hysteresis design (Schmitt-trigger pattern)
-------------------------------------------
A single symmetric threshold causes the state machine to oscillate when
price hovers near the boundary.  Asymmetric thresholds create a dead-band:

    enter APPROACH: price ≤ trailing_stop + APPROACH_ENTER_BUFFER × entry_atr
    exit  APPROACH: price >  trailing_stop + APPROACH_EXIT_BUFFER  × entry_atr
    dead-band width: (APPROACH_EXIT_BUFFER - APPROACH_ENTER_BUFFER) × entry_atr

Price inside the dead-band: no zone transition, regardless of current zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Hysteresis coefficients (multiples of entry_atr above trailing_stop).
# ---------------------------------------------------------------------------

APPROACH_ENTER_BUFFER: float = 0.5
"""Enter APPROACH when price ≤ trailing_stop + 0.5 × entry_atr."""

APPROACH_EXIT_BUFFER: float = 0.8
"""Exit APPROACH (back to NORMAL) when price > trailing_stop + 0.8 × entry_atr."""

assert APPROACH_EXIT_BUFFER > APPROACH_ENTER_BUFFER, (
    "APPROACH_EXIT_BUFFER must exceed APPROACH_ENTER_BUFFER to form a dead-band."
)


class PriceZone(str, Enum):
    """Price zone relative to the trailing stop.

    Used as the state variable in the intraday monitoring state machine.
    """

    NORMAL = "NORMAL"
    APPROACH = "APPROACH"
    BREACH = "BREACH"


@dataclass(frozen=True)
class StopLevels:
    """All price thresholds for one position snapshot."""

    trailing_stop: float
    """Hard stop: max_close_since_entry - 2.0 × entry_atr."""

    approach_enter: float
    """Enter APPROACH zone when price drops to or below this level."""

    approach_exit: float
    """Exit APPROACH zone (back to NORMAL) when price rises above this level."""


def compute_stop_levels(
    max_close_since_entry: float,
    entry_atr: float,
) -> StopLevels:
    """Compute all stop thresholds for a position.

    Args:
        max_close_since_entry: High-water mark of daily close prices since
            entry.  Updated nightly by EOD run; intraday monitor uses
            yesterday's value for the entire trading day.
        entry_atr: ATR14 at entry date.  Frozen — does not reflect current
            market volatility.  Band width is stable over the position's life.

    Returns:
        :class:`StopLevels` with trailing_stop, approach_enter, approach_exit.
    """
    trailing_stop = max_close_since_entry - 2.0 * entry_atr
    approach_enter = trailing_stop + APPROACH_ENTER_BUFFER * entry_atr
    approach_exit = trailing_stop + APPROACH_EXIT_BUFFER * entry_atr
    return StopLevels(
        trailing_stop=trailing_stop,
        approach_enter=approach_enter,
        approach_exit=approach_exit,
    )


def classify_zone(
    price: float,
    levels: StopLevels,
    current_zone: PriceZone,
) -> PriceZone:
    """Classify price into a zone, applying hysteresis from current_zone.

    Transition rules
    ----------------
    BREACH (unconditional, no hysteresis):
        price ≤ trailing_stop  →  BREACH

    From NORMAL:
        price ≤ approach_enter  →  APPROACH
        otherwise               →  NORMAL

    From APPROACH:
        price >  approach_exit  →  NORMAL   (exit threshold, higher than entry)
        otherwise               →  APPROACH (dead-band: no transition)

    From BREACH:
        price >  approach_exit  →  NORMAL   (full recovery)
        price >  trailing_stop  →  APPROACH (partial recovery)
        otherwise               →  BREACH

    Args:
        price: Current last-trade price.
        levels: Precomputed thresholds for this position.
        current_zone: Zone from the previous poll cycle.  Must be persisted
            and supplied by the caller; not inferred from price alone.

    Returns:
        New :class:`PriceZone`.
    """
    if price <= levels.trailing_stop:
        return PriceZone.BREACH

    if current_zone == PriceZone.BREACH:
        if price > levels.approach_exit:
            return PriceZone.NORMAL
        return PriceZone.APPROACH

    if current_zone == PriceZone.APPROACH:
        if price > levels.approach_exit:
            return PriceZone.NORMAL
        return PriceZone.APPROACH

    # current_zone == NORMAL (or unknown default)
    if price <= levels.approach_enter:
        return PriceZone.APPROACH
    return PriceZone.NORMAL
