# strategies/trend_breakout.py
"""TrendBreakout v1 — Conservative deterministic Donchian breakout (reviewer-curated).

設計理念 (reviewer):
- Helios 真正 edge 不在 entry alpha, 而在「不在爛市場交易」
- 所以 regime gate 是第一道防線
- Breakout 條件刻意 conservative (避免台股常見 fake breakout)
- 所有條件用 AND, 寧少而精

Signal 條件 (全部 AND, 都成立才觸發):
  Regime gate:
    1. market_regime == 'bull'

  Trend alignment:
    2. close > sma_50 > sma_200        (價格 + 短期 MA + 長期 MA 三線多頭)
    3. sma_50 > sma_50.shift(5)         (Slope filter — 趨勢還活著, 不是衰退中)

  Conservative breakout:
    4. close > donchian_20_high.shift(1)
       (今天收盤 > 「不含今天」的前 20 日最高 — 不是 touching, 而是真實突破)

  Volume confirmation:
    5. rel_volume_20 >= 1.5             (台股 breakout 沒量 = 危險, reviewer §35)

  Momentum:
    6. RSI in [50, 75]                  (有動能但不過熱)

Score (0.5 ~ 1.0 baseline):
  +0.10 if rel_vol >= 2.0
  +0.10 if rel_vol >= 3.0
  +0.10 if RSI in [55, 65] (sweet spot)
  +0.10 if ROC20 > 5%       (近期漲幅顯著)

不做 (v0.1 cohesion):
  - portfolio sizing / position weighting
  - exit signal generation (待 v0.1.13)
  - parameter optimization

Version: v0.1.0 (2026-05-17)
Changelog:
  v0.1.0 (2026-05-17): Initial — conservative trend-following breakout
"""
from __future__ import annotations

from datetime import date as date_type
from typing import Any

import polars as pl

from data.database import connect
from strategies.base import Signal, Strategy

# ─────────────────────────────────────────────────────────────
# Strategy parameters (named, not magic — easy to tweak in v0.1.13 backtest)
# ─────────────────────────────────────────────────────────────

REL_VOL_MIN = 1.5            # volume confirmation threshold
SMA_SLOPE_LOOKBACK = 5       # sma_50 must be higher than 5 days ago
RSI_MIN = 50.0               # momentum floor
RSI_MAX = 75.0               # overbought ceiling

# Score bonuses (附加分項目)
RSI_SWEETSPOT = (55.0, 65.0)
ROC_THRESHOLD = 5.0


class TrendBreakoutStrategy(Strategy):
    name = "trend_breakout_v1"

    def generate_signals(
        self,
        as_of: date_type,
        symbols: list[str] | None = None,
    ) -> list[Signal]:
        # 1. Regime gate
        regime_data = self._load_market_regime(as_of)
        if regime_data is None or regime_data["regime"] != "bull":
            return []

        # 2. Load features with history
        df = self._load_features_with_history(as_of, symbols)
        if df.is_empty():
            return []

        # 3. Check each symbol
        signals: list[Signal] = []
        for row in df.iter_rows(named=True):
            sig = self._check_symbol(row, regime_data)
            if sig is not None:
                signals.append(sig)
        return signals

    # ── helpers ────────────────────────────────────────────────

    def _load_market_regime(self, as_of: date_type) -> dict[str, Any] | None:
        with connect(read_only=True) as conn:
            row = conn.execute(
                """
                SELECT date, taiex_close, sma_200, vol_20, regime
                FROM market_regime WHERE date <= ?
                ORDER BY date DESC LIMIT 1
                """,
                [as_of],
            ).fetchone()
        if not row:
            return None
        return {
            "date": row[0], "taiex_close": row[1], "sma_200": row[2],
            "vol_20": row[3], "regime": row[4],
        }

    def _load_features_with_history(
        self, as_of: date_type, symbols: list[str] | None
    ) -> pl.DataFrame:
        """以 SQL 一次 join 出 today + 5d-ago sma_50 + 1d-ago donchian_high.

        Window functions (LAG over date) 對單一 symbol 的時間軸做 shift.
        """
        symbol_filter = ""
        params: list[Any] = [as_of]
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            symbol_filter = f" AND stock_id IN ({placeholders})"
            params.extend(symbols)

        sql = f"""
        WITH lagged AS (
            SELECT
                stock_id, date,
                sma_20, sma_50, sma_200, ema_20,
                rsi_14, roc_20, atr_14,
                donchian_20_high, donchian_20_low,
                volume_ma_20, rel_volume_20,
                LAG(donchian_20_high, 1) OVER (PARTITION BY stock_id ORDER BY date)
                    AS prior_donchian_high,
                LAG(sma_50, {SMA_SLOPE_LOOKBACK}) OVER (PARTITION BY stock_id ORDER BY date)
                    AS sma_50_lookback,
                ROW_NUMBER() OVER (PARTITION BY stock_id ORDER BY date DESC) AS rn
            FROM daily_features
            WHERE date <= ?{symbol_filter}
        )
        SELECT
            l.stock_id, l.date,
            l.sma_20, l.sma_50, l.sma_200, l.ema_20,
            l.rsi_14, l.roc_20, l.atr_14,
            l.donchian_20_high, l.donchian_20_low,
            l.volume_ma_20, l.rel_volume_20,
            l.prior_donchian_high,
            l.sma_50_lookback,
            a.adj_close
        FROM lagged l
        JOIN daily_price_adj a
          ON a.stock_id = l.stock_id AND a.date = l.date
        WHERE l.rn = 1
        ORDER BY l.stock_id
        """
        with connect(read_only=True) as conn:
            arrow = conn.execute(sql, params).to_arrow_table()
        return pl.from_arrow(arrow)

    def _check_symbol(
        self, row: dict[str, Any], regime_data: dict[str, Any]
    ) -> Signal | None:
        # 必要欄位 not-null check
        required = [
            "sma_50", "sma_200", "rsi_14", "atr_14", "rel_volume_20",
            "adj_close", "prior_donchian_high", "sma_50_lookback",
        ]
        for k in required:
            if row.get(k) is None:
                return None

        close = row["adj_close"]
        sma_50 = row["sma_50"]
        sma_200 = row["sma_200"]
        sma_50_back = row["sma_50_lookback"]
        rsi = row["rsi_14"]
        atr = row["atr_14"]
        rel_vol = row["rel_volume_20"]
        prior_dch_high = row["prior_donchian_high"]
        roc = row.get("roc_20")

        # Filters (全 AND)
        if not (close > sma_50 > sma_200):
            return None
        if not (sma_50 > sma_50_back):
            return None
        if close <= prior_dch_high:
            return None
        if rel_vol < REL_VOL_MIN:
            return None
        if not (RSI_MIN <= rsi <= RSI_MAX):
            return None

        # Conviction score
        score = 0.5
        if rel_vol >= 2.0:
            score += 0.10
        if rel_vol >= 3.0:
            score += 0.10
        if RSI_SWEETSPOT[0] <= rsi <= RSI_SWEETSPOT[1]:
            score += 0.10
        if roc is not None and roc > ROC_THRESHOLD:
            score += 0.10
        score = min(score, 1.0)

        # Decision context
        gap_200 = (close / sma_200 - 1) * 100
        slope_pct = (sma_50 / sma_50_back - 1) * 100
        breakout_strength = (close / prior_dch_high - 1) * 100

        reason: list[str] = [
            f"regime={regime_data['regime']} (gate passed)",
            f"close>{sma_50:.2f}=SMA50>SMA200={sma_200:.2f} (gap +{gap_200:.1f}%)",
            f"SMA50 slope +{slope_pct:.2f}% over {SMA_SLOPE_LOOKBACK}d (alive)",
            f"Donchian breakout: close {close:.2f} > prev 20d high {prior_dch_high:.2f} (+{breakout_strength:.2f}%)",
            f"rel_volume {rel_vol:.2f}x (threshold {REL_VOL_MIN}x)",
            f"RSI {rsi:.1f} in [{RSI_MIN:.0f},{RSI_MAX:.0f}]",
        ]
        if roc is not None:
            reason.append(f"ROC20 {roc:+.2f}%")

        metadata = {
            "as_of": str(row["date"]),
            "close": close,
            "sma_20": row.get("sma_20"),
            "sma_50": sma_50,
            "sma_200": sma_200,
            "ema_20": row.get("ema_20"),
            "atr_14": atr,
            "rsi_14": rsi,
            "roc_20": roc,
            "rel_volume_20": rel_vol,
            "volume_ma_20": row.get("volume_ma_20"),
            "donchian_high_prev": prior_dch_high,
            "donchian_low": row.get("donchian_20_low"),
            "sma_50_5d_ago": sma_50_back,
            "taiex_close": regime_data["taiex_close"],
            "taiex_sma_200": regime_data["sma_200"],
            "taiex_vol_20": regime_data["vol_20"],
            "breakout_strength_pct": breakout_strength,
            "slope_pct_5d": slope_pct,
            "gap_to_sma200_pct": gap_200,
        }

        return Signal(
            stock_id=row["stock_id"],
            signal_date=row["date"],
            strategy=self.name,
            side="buy",
            entry_price=close,
            entry_atr=atr,
            regime=regime_data["regime"],
            score=score,
            reason=reason,
            metadata=metadata,
        )
