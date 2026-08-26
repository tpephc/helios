# features/market_state_assembly.py
"""Read-only canonical-panel assembly for Security Market State V1.

This module is the composed boundary.  It may read DuckDB and the governed
calendar, but it never changes classifier semantics or writes repository state.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Final

from data.database import connect
from features.market_state import (
    DEFAULT_CONFIG,
    AdjustedOhlcBar,
    Availability,
    ClassificationResult,
    ClassificationStatus,
    HistoryDiagnosticCode,
    LimitStatusCoverage,
    MarketStateClassifierConfig,
    OperationalDiagnosticCode,
    SecurityMarketStateInput,
    classify,
)
from market.trading_calendar import is_trading_day
from utils.logger import get_logger

logger = get_logger(__name__)

ASSEMBLY_SCHEMA_VERSION: Final = "pr_ms1_1_assembly_v1"
CALENDAR_BASIS_ID: Final = "market.trading_calendar:v0.2.0"
LIFECYCLE_BASIS_ID: Final = "security_lifecycle:effective_dated_v1"
ADJUSTMENT_METHOD: Final = "backward_multiplicative_future_factors"


@dataclass(frozen=True, slots=True)
class AdjustmentProvenance:
    """Identity of current applied factors; intentionally not C-2 provenance."""

    method: str
    factor_set_hash: str
    source_basis_id: str


@dataclass(frozen=True, slots=True)
class MarketStateExportRecord:
    """Assembly-owned public envelope without duplicate classifier fields."""

    availability: Availability
    classification: ClassificationResult | None
    security_id: str
    panel_snapshot_id: str | None
    adjustment_provenance: AdjustmentProvenance | None
    assembly_schema_version: str
    history_diagnostics: HistoryDiagnosticCode | None
    operational_diagnostics: OperationalDiagnosticCode | None
    decision_available_at: datetime | None
    limit_status_coverage: LimitStatusCoverage

    def __post_init__(self) -> None:
        """Enforce composed-envelope invariants at the producing boundary."""
        available = self.availability is Availability.AVAILABLE
        if (self.classification is not None) != available:
            raise ValueError("classification presence must equal availability")
        if available != (self.operational_diagnostics is None):
            raise ValueError("operational diagnostics must exist only on failure")
        if not available and self.history_diagnostics is not None:
            raise ValueError("operational failure cannot carry history diagnostics")
        if self.classification is not None:
            insufficient = self.classification.status is ClassificationStatus.INSUFFICIENT_HISTORY
            if insufficient != (self.history_diagnostics is not None):
                raise ValueError("history diagnostics must exactly follow insufficient history")
        if available and (
            self.panel_snapshot_id is None
            or self.adjustment_provenance is None
            or self.decision_available_at is None
        ):
            raise ValueError("available records require panel, adjustment, and decision provenance")


@dataclass(frozen=True, slots=True)
class _PanelRow:
    session: date
    adj_open: float | None
    adj_high: float | None
    adj_low: float | None
    adj_close: float | None
    volume: int | None


@dataclass(frozen=True, slots=True)
class _LifecycleBasis:
    available: bool
    listed_from: date | None
    content_identity: str | None = None


def assemble_market_state(
    security_id: str,
    as_of: date,
    *,
    decision_available_at: datetime,
    config: MarketStateClassifierConfig = DEFAULT_CONFIG,
) -> MarketStateExportRecord:
    """Assemble, classify, and envelope one close-inclusive security snapshot.

    The caller supplies ``decision_available_at`` after satisfying the
    close-inclusive upstream timing contract; assembly never invents it from a
    wall clock.
    """
    calendar_cache: dict[date, bool] = {}
    try:
        expected = _cached_calendar(calendar_cache)
        if not expected(as_of):
            return _failure(security_id, OperationalDiagnosticCode.AS_OF_BAR_MISSING)
        rows = _load_panel_rows(security_id, as_of, config.required_history_sessions)
        row_by_session = {row.session: row for row in rows}
        lifecycle = _load_lifecycle_basis(security_id)
        as_of_row = row_by_session.get(as_of)
        if as_of_row is None:
            if not lifecycle.available:
                return _failure(security_id, OperationalDiagnosticCode.REFERENCE_BASIS_UNAVAILABLE)
            return _failure(security_id, OperationalDiagnosticCode.AS_OF_BAR_MISSING)
        as_of_condition = _bar_condition(as_of_row)
        if as_of_condition == "invalid":
            return _failure(security_id, OperationalDiagnosticCode.AS_OF_BAR_INVALID)
        if as_of_condition == "zero_volume":
            return _failure(security_id, OperationalDiagnosticCode.AS_OF_BAR_ZERO_VOLUME)

        bars, barrier = _terminal_bars(
            as_of,
            row_by_session,
            lifecycle,
            expected,
            config.required_history_sessions,
        )
        dto = SecurityMarketStateInput(security_id=security_id, as_of=as_of, bars=tuple(bars))
        result = classify(dto, config)
        history = _history_diagnostic(result, barrier, lifecycle)
        provenance = _adjustment_provenance(security_id, bars)
        snapshot = _panel_snapshot_id(security_id, as_of, bars, lifecycle, provenance)
        return MarketStateExportRecord(
            availability=Availability.AVAILABLE,
            classification=result,
            security_id=security_id,
            panel_snapshot_id=snapshot,
            adjustment_provenance=provenance,
            assembly_schema_version=ASSEMBLY_SCHEMA_VERSION,
            history_diagnostics=history,
            operational_diagnostics=None,
            decision_available_at=decision_available_at,
            limit_status_coverage=LimitStatusCoverage.OFFICIAL_STATUS_UNAVAILABLE,
        )
    except _ReferenceBasisError:
        return _failure(security_id, OperationalDiagnosticCode.REFERENCE_BASIS_UNAVAILABLE)
    except Exception as exc:
        logger.exception(
            "market_state_assembly_unclassified_failure",
            security_id=security_id,
            as_of=str(as_of),
            error=str(exc),
        )
        return _failure(security_id, OperationalDiagnosticCode.UNCLASSIFIED_ASSEMBLY_FAILURE)


def _failure(security_id: str, code: OperationalDiagnosticCode) -> MarketStateExportRecord:
    """Return a no-DTO operational envelope with no partial-panel identity."""
    return MarketStateExportRecord(
        availability=Availability.OPERATIONAL_FAILURE,
        classification=None,
        security_id=security_id,
        panel_snapshot_id=None,
        adjustment_provenance=None,
        assembly_schema_version=ASSEMBLY_SCHEMA_VERSION,
        history_diagnostics=None,
        operational_diagnostics=code,
        decision_available_at=None,
        limit_status_coverage=LimitStatusCoverage.OFFICIAL_STATUS_UNAVAILABLE,
    )


class _ReferenceBasisError(RuntimeError):
    """Raised only when terminal eligible-session construction lacks a basis."""


def _cached_calendar(cache: dict[date, bool]) -> Callable[[date], bool]:
    """Return a single-assembly-call calendar cache; it never survives a call."""
    def expected(session: date) -> bool:
        if session not in cache:
            try:
                cache[session] = is_trading_day(session)
            except Exception as exc:
                raise _ReferenceBasisError(str(exc)) from exc
        return cache[session]
    return expected


def _load_panel_rows(
    security_id: str, as_of: date, fetch_depth: int
) -> tuple[_PanelRow, ...]:
    """Read a scalar-bounded canonical suffix without deciding sufficiency."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT date, adj_open, adj_high, adj_low, adj_close, volume
            FROM listed_market_daily_price_adj
            WHERE stock_id = ? AND date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            [security_id, as_of, fetch_depth],
        ).fetchall()
    return tuple(_PanelRow(*row) for row in reversed(rows))


def _load_lifecycle_basis(security_id: str) -> _LifecycleBasis:
    """Load effective listed-from; no row means governed fully-listed fallback."""
    try:
        with connect(read_only=True) as conn:
            rows = conn.execute(
                """SELECT listed_from, listed_to, market, source_type, source_url
                   FROM security_lifecycle
                   WHERE stock_id = ? AND market IN ('TWSE', 'TPEx')
                   ORDER BY listed_from, market""",
                [security_id],
            ).fetchall()
    except Exception:  # lifecycle may be unavailable after a DTO is possible
        return _LifecycleBasis(available=False, listed_from=None, content_identity=None)
    listed_from = min((row[0] for row in rows), default=None)
    payload = [tuple(str(value) for value in row) for row in rows]
    if not payload:
        payload = [("no_lifecycle_row_assumed_listed_from_1900-01-01",)]
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    return _LifecycleBasis(
        available=True,
        listed_from=listed_from,
        content_identity=sha256(encoded).hexdigest(),
    )


def _bar_condition(row: _PanelRow) -> str | None:
    """Classify validity exhaustively; negative volume is invalid, not zero volume."""
    prices = (row.adj_open, row.adj_high, row.adj_low, row.adj_close)
    if (
        any(
            type(value) is not float or not math.isfinite(value) or value <= 0
            for value in prices
        )
        or row.adj_low is None
        or row.adj_high is None
        or row.adj_open is None
        or row.adj_close is None
        or not (row.adj_low <= min(row.adj_open, row.adj_close) <= max(row.adj_open, row.adj_close) <= row.adj_high)
        or row.volume is None
        or row.volume < 0
    ):
        return "invalid"
    if row.volume == 0:
        return "zero_volume"
    return None


def _terminal_bars(
    as_of: date,
    row_by_session: dict[date, _PanelRow],
    lifecycle: _LifecycleBasis,
    expected: Callable[[date], bool],
    fetch_depth: int,
) -> tuple[list[AdjustedOhlcBar], str | None]:
    """Build the bounded terminal suffix without skipping an observed barrier."""
    collected: list[AdjustedOhlcBar] = []
    session = as_of
    while True:
        if lifecycle.available and lifecycle.listed_from is not None and session < lifecycle.listed_from:
            return list(reversed(collected)), "natural"
        if expected(session):
            row = row_by_session.get(session)
            if row is None:
                return list(reversed(collected)), "gap"
            condition = _bar_condition(row)
            if condition == "invalid":
                return list(reversed(collected)), "gap"
            if condition == "zero_volume":
                return list(reversed(collected)), "zero_volume"
            collected.append(
                AdjustedOhlcBar(session, row.adj_open, row.adj_high, row.adj_low, row.adj_close)  # type: ignore[arg-type]
            )
            if len(collected) == fetch_depth:
                return list(reversed(collected)), None
        session -= timedelta(days=1)


def _history_diagnostic(
    result: ClassificationResult, barrier: str | None, lifecycle: _LifecycleBasis
) -> HistoryDiagnosticCode | None:
    """Assign diagnostics only after classifier-owned insufficient-history output."""
    if result.status is not ClassificationStatus.INSUFFICIENT_HISTORY:
        return None
    if not lifecycle.available:
        return HistoryDiagnosticCode.DIAGNOSIS_UNAVAILABLE
    if barrier == "natural":
        return HistoryDiagnosticCode.NATURAL_HISTORY_SHORTFALL
    if barrier == "zero_volume":
        return HistoryDiagnosticCode.ZERO_VOLUME_BAR_EXCLUDED
    if barrier == "gap":
        return HistoryDiagnosticCode.DATA_GAP
    return HistoryDiagnosticCode.DIAGNOSIS_UNAVAILABLE


def _adjustment_provenance(security_id: str, bars: Sequence[AdjustedOhlcBar]) -> AdjustmentProvenance:
    """Digest current applied factor content; never represent it as immutable C-2 history."""
    first = bars[0].session
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """SELECT date, kind, adjustment_factor, source FROM corporate_actions
               WHERE stock_id = ? AND confirmed = TRUE AND adjustment_factor IS NOT NULL
                 AND date > ? ORDER BY date, kind""",
            [security_id, first],
        ).fetchall()
    payload = json.dumps(
        [tuple(str(value) for value in row) for row in rows],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return AdjustmentProvenance(
        ADJUSTMENT_METHOD,
        sha256(payload.encode()).hexdigest(),
        "corporate_actions:confirmed_factors_v1",
    )


def _panel_snapshot_id(
    security_id: str,
    as_of: date,
    bars: Sequence[AdjustedOhlcBar],
    lifecycle: _LifecycleBasis,
    provenance: AdjustmentProvenance,
) -> str:
    """Return SHA-256 over declared ordered terminal-panel binary64 content."""
    digest = sha256()
    fields = (
        "panel_snapshot_v1",
        ASSEMBLY_SCHEMA_VERSION,
        security_id,
        as_of.isoformat(),
        CALENDAR_BASIS_ID,
        LIFECYCLE_BASIS_ID,
        str(lifecycle.listed_from),
        lifecycle.content_identity or "unavailable",
        provenance.method,
        provenance.factor_set_hash,
        provenance.source_basis_id,
    )
    for text in fields:
        encoded = text.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    digest.update(len(bars).to_bytes(8, "big"))
    for bar in bars:
        digest.update(bar.session.isoformat().encode("ascii"))
        for value in (bar.adj_open, bar.adj_high, bar.adj_low, bar.adj_close):
            digest.update(struct.pack(">d", value))
    return digest.hexdigest()
