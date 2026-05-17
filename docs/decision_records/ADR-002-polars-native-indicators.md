# ADR-002: Polars-native indicators

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1.11

## Context

Technical indicators (SMA, RSI, ATR, Donchian, etc.) are well-known and many implementations exist:
- **TA-Lib** — C-optimized, industry standard, but C compilation friction
- **pandas-ta** — Pure Python, popular, but pandas-coupled and slow
- **vectorbt** — Comprehensive but heavyweight framework
- **Hand-rolled in Polars** — Transparent, fast, no extra deps

The question is whether to take a library dependency or build indicators in our existing Polars stack.

Forces:
- Indicator math is **public knowledge**. The "formula" itself is not proprietary.
- We have a single source of truth principle (`features/technical.py`).
- Polars is already a hard dependency. Adding pandas + pandas-ta means dual DataFrame systems.
- Debugging an indicator anomaly is much easier when the implementation is 5 lines of Polars rather than a TA-Lib black box.
- ATR is computed on adj OHLC (avoid dividend pollution). This requires careful sequencing — library implementations make assumptions about input cleanliness.

## Decision

**All indicators in Helios are implemented as Polars expressions in `features/technical.py`. No TA-Lib, no pandas-ta, no external indicator library.**

A single function `compute_indicators(df: pl.DataFrame) -> pl.DataFrame` returns the input frame augmented with all 9 indicator columns.

## Consequences

**Positive**
- Every indicator's math is visible in ~5 lines of code
- Single source of truth: indicator anomalies have exactly one place to look
- Lazy evaluation: indicator pipeline runs in batch on the GIL-free Polars engine
- No version drift (TA-Lib has had subtle math changes between versions)
- Polars-native = same DataFrame type as the rest of the codebase
- Easy to add Helios-specific tweaks (e.g., ATR on adj OHLC, RSI Wilder smoothing)

**Negative**
- We maintain indicator math ourselves. If a new TA-Lib indicator emerges that we want, we re-implement.
- No C-speed for individual indicators (Polars is plenty fast in practice — full universe daily features in <2s)
- Our implementation must be validated against reference (one-time effort; spot-checked vs TradingView for 2330)

**Risks**
- A subtle math bug in our implementation could affect all signals. **Mitigation**: indicator output spot-checked against TradingView at v0.1.11 (zero discrepancy on tested cases).

## Alternatives considered

1. **TA-Lib** — rejected. C compilation friction on Ubuntu; we don't need C speed; adds opacity.
2. **pandas-ta** — rejected. Brings pandas as a second DataFrame system. Slower than Polars for our batch sizes.
3. **vectorbt** — rejected. Whole-framework dependency for what we use indicators only.
4. **Both Polars and TA-Lib (cross-check)** — rejected. Double maintenance for marginal confidence gain.

## Forever-rule

When a new indicator is needed:
1. Add it to `features/technical.py` as a Polars expression
2. Spot-check against a reference (TradingView / a trusted source) for at least 1 symbol over a known period
3. Update tests
4. Never import indicator math from anywhere else
