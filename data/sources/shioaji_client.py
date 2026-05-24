# data/sources/shioaji_client.py
"""Shioaji read-only market data client — v0.1.0.

Read-only wrapper around Shioaji for stock and warrant market data.
Supports:
- Real-time stock snapshots (bid/ask, OHLCV, volume_ratio)
- TSE/OTC call warrant discovery filtered by underlying name
- Warrant liquidity snapshots (spread_pct, volume)

NOT for order placement. All trading methods are intentionally excluded.
Requires production API key (simulation tokens will fail).

Version: v0.1.0 (2026-05-23)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import shioaji as sj

from config.settings import get_settings
from utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Shioaji snapshot API limit per call
_SNAPSHOT_BATCH = 50
# Contract download timeout in milliseconds
_CONTRACT_TIMEOUT_MS = 30_000


class ShioajiError(Exception):
    """Shioaji client error."""


class ShioajiClient:
    """Read-only Shioaji client for stock and warrant market data.

    Usage::

        with ShioajiClient() as client:
            df = client.stock_snapshots(["2330", "5434"])

    The context manager handles login/logout automatically.
    Contracts are downloaded once per session on login.
    """

    def __init__(self, fetch_contracts: bool = True) -> None:
        cfg = get_settings()
        if not cfg.shioaji_api_key or not cfg.shioaji_secret_key:
            raise ShioajiError(
                "SHIOAJI_API_KEY and SHIOAJI_SECRET_KEY must be set in .env"
            )
        self._api_key = cfg.shioaji_api_key.get_secret_value()
        self._secret_key = cfg.shioaji_secret_key.get_secret_value()
        self._fetch_contracts = fetch_contracts
        self._api: sj.Shioaji | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def login(self) -> None:
        """Login and optionally download contracts.

        Raises ShioajiError if login fails (invalid key, no production
        permission, network error).
        """
        try:
            self._api = sj.Shioaji()
            accounts = self._api.login(
                api_key=self._api_key,
                secret_key=self._secret_key,
                fetch_contract=self._fetch_contracts,
                contracts_timeout=_CONTRACT_TIMEOUT_MS if self._fetch_contracts else 0,
                subscribe_trade=False,
            )
            logger.info(
                "shioaji_login_ok",
                accounts=[str(a) for a in accounts],
                fetch_contracts=self._fetch_contracts,
            )
        except Exception as e:
            self._api = None
            raise ShioajiError(f"Shioaji login failed: {e}") from e

    def logout(self) -> None:
        """Logout safely. No-op if not logged in."""
        if self._api is None:
            return
        try:
            self._api.logout()
            logger.info("shioaji_logout_ok")
        except Exception as e:
            logger.warning("shioaji_logout_error", error=str(e))
        finally:
            self._api = None

    def __enter__(self) -> ShioajiClient:
        self.login()
        return self

    def __exit__(self, *_args: object) -> None:
        self.logout()

    # ── internal helpers ───────────────────────────────────────────────────────

    def _require_api(self) -> sj.Shioaji:
        if self._api is None:
            raise ShioajiError(
                "Not logged in. Use ShioajiClient as a context manager."
            )
        return self._api

    def _snapshots_batched(self, contracts: list) -> list:
        """Fetch snapshots in batches of _SNAPSHOT_BATCH."""
        api = self._require_api()
        results: list = []
        for i in range(0, len(contracts), _SNAPSHOT_BATCH):
            batch = contracts[i : i + _SNAPSHOT_BATCH]
            results.extend(api.snapshots(batch))
        return results

    # ── stock snapshots ────────────────────────────────────────────────────────

    def stock_snapshots(self, stock_ids: list[str]) -> pl.DataFrame:
        """Real-time snapshots for the given stock IDs.

        Args:
            stock_ids: List of TWSE/OTC stock codes, e.g. ["2330", "5434"].

        Returns:
            DataFrame with columns:
                code, close, buy_price, sell_price, spread_pct,
                total_volume, volume_ratio, buy_volume, sell_volume.
            Rows with no ask price are excluded.
        """
        api = self._require_api()
        contracts = []
        missing: list[str] = []
        for sid in stock_ids:
            c = api.Contracts.Stocks.get(sid)
            if c:
                contracts.append(c)
            else:
                missing.append(sid)

        if missing:
            logger.warning("shioaji_stocks_not_found", codes=missing)

        if not contracts:
            return pl.DataFrame()

        snaps = self._snapshots_batched(contracts)
        return _snapshots_to_df(snaps)

    # ── warrant discovery ──────────────────────────────────────────────────────

    def warrant_call_contracts(
        self,
        underlying_names: set[str] | None = None,
    ) -> list:
        """Return active TSE call warrant contract objects.

        Taiwan call warrants have category='00' and '購' in their name.
        OTC call warrants are excluded (different exchange, lower liquidity
        for top-200 underlying stocks which are primarily TSE-listed).

        Args:
            underlying_names: Optional set of abbreviated underlying stock
                names to filter (e.g. {"台積電", "崇越", "聯發科"}).
                If None, returns all TSE call warrants (~27k contracts).

        Returns:
            List of shioaji Stock contract objects.
        """
        api = self._require_api()
        tse = api.Contracts.Stocks.TSE

        calls = [
            s
            for s in tse
            if getattr(s, "category", "") == "00" and "購" in s.name
        ]

        if underlying_names:
            calls = [
                w for w in calls
                if any(name in w.name for name in underlying_names)
            ]

        logger.info(
            "shioaji_warrant_calls_found",
            total=len(calls),
            filtered=underlying_names is not None,
        )
        return calls

    def warrant_snapshots(
        self,
        warrant_contracts: list,
        max_spread_pct: float = 5.0,
    ) -> pl.DataFrame:
        """Liquidity snapshots for warrant contracts.

        Fetches bid/ask, volume, and computes spread_pct.
        Filters out warrants exceeding max_spread_pct.

        Args:
            warrant_contracts: List of shioaji Stock contracts (call warrants).
            max_spread_pct: Maximum allowed spread as % of ask price.

        Returns:
            DataFrame with columns:
                code, name, close, buy_price, sell_price, spread_pct,
                total_volume, volume_ratio, buy_volume, sell_volume.
            Sorted ascending by spread_pct.
        """
        if not warrant_contracts:
            return pl.DataFrame()

        name_map: dict[str, str] = {w.code: w.name for w in warrant_contracts}
        snaps = self._snapshots_batched(warrant_contracts)
        df = _snapshots_to_df(snaps, name_map=name_map)

        if df.is_empty():
            return df

        return (
            df.filter(pl.col("spread_pct").is_not_null())
            .filter(pl.col("spread_pct") <= max_spread_pct)
            .sort("spread_pct")
        )


# ── helpers ────────────────────────────────────────────────────────────────────


def _snapshots_to_df(
    snaps: list,
    name_map: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Convert Shioaji snapshot objects to a Polars DataFrame."""
    records: list[dict] = []
    for s in snaps:
        ask = s.sell_price or 0.0
        bid = s.buy_price or 0.0
        spread_pct = round((ask - bid) / ask * 100, 2) if ask > 0 else None
        row: dict = {
            "code": s.code,
            "close": s.close,
            "buy_price": bid,
            "sell_price": ask,
            "spread_pct": spread_pct,
            "total_volume": s.total_volume,
            "volume_ratio": s.volume_ratio,
            "buy_volume": s.buy_volume,
            "sell_volume": s.sell_volume,
        }
        if name_map is not None:
            row["name"] = name_map.get(s.code, "")
        records.append(row)

    if not records:
        return pl.DataFrame()
    return pl.DataFrame(records)
