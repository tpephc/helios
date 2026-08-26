"""Assembly-boundary contract tests for PR-MS1.1 Market State."""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from features import market_state_assembly as assembly
from features.market_state import (
    Availability,
    ClassificationStatus,
    HistoryDiagnosticCode,
    OperationalDiagnosticCode,
)

AS_OF = date(2026, 1, 2)
DECIDED_AT = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)


def _row(session: date, *, volume: int = 1, close: float = 100.0) -> assembly._PanelRow:
    return assembly._PanelRow(session, close, close, close, close, volume)


def _rows(n: int) -> tuple[assembly._PanelRow, ...]:
    return tuple(_row(date.fromordinal(AS_OF.toordinal() - offset)) for offset in range(n - 1, -1, -1))


@pytest.fixture
def patches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembly, "is_trading_day", lambda _: True)
    monkeypatch.setattr(
        assembly, "_load_lifecycle_basis", lambda _: assembly._LifecycleBasis(True, date(1900, 1, 1))
    )
    monkeypatch.setattr(
        assembly,
        "_adjustment_provenance",
        lambda *_: assembly.AdjustmentProvenance("test", "f" * 64, "test"),
    )


def _assemble() -> assembly.MarketStateExportRecord:
    return assembly.assemble_market_state("0050", AS_OF, decision_available_at=DECIDED_AT)


def test_available_record_has_complete_envelope(patches: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: _rows(52))

    record = _assemble()

    assert record.availability is Availability.AVAILABLE
    assert record.classification is not None
    assert record.classification.status is ClassificationStatus.INDETERMINATE
    assert record.panel_snapshot_id is not None
    assert record.adjustment_provenance is not None
    assert record.decision_available_at == DECIDED_AT
    assert record.history_diagnostics is None


def test_panel_loader_uses_only_lifecycle_filtered_adjusted_view() -> None:
    source = inspect.getsource(assembly._load_panel_rows)
    assert "FROM listed_market_daily_price_adj" in source
    assert "FROM daily_price_adj" not in source


def test_decision_available_at_is_required(patches: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: _rows(52))
    with pytest.raises(TypeError):
        assembly.assemble_market_state("0050", AS_OF)  # type: ignore[call-arg]


def test_duckdb_loader_materializes_binary64_prices(tmp_db: Path) -> None:
    from data.database import connect

    with connect() as conn:
        conn.execute(
            """INSERT INTO daily_price_adj
               (stock_id, date, adj_open, adj_high, adj_low, adj_close,
                raw_close, cum_factor, volume)
               VALUES ('0050', ?, 100.0, 101.0, 99.0, 100.5, 100.5, 1.0, 1)""",
            [AS_OF],
        )

    row = assembly._load_panel_rows("0050", AS_OF, fetch_depth=52)[0]
    assert tuple(type(value) for value in (row.adj_open, row.adj_high, row.adj_low, row.adj_close)) == (
        float,
        float,
        float,
        float,
    )


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ((), OperationalDiagnosticCode.AS_OF_BAR_MISSING),
        ((_row(AS_OF, volume=0),), OperationalDiagnosticCode.AS_OF_BAR_ZERO_VOLUME),
        ((_row(AS_OF, volume=-1),), OperationalDiagnosticCode.AS_OF_BAR_INVALID),
        ((_row(AS_OF, volume=-1, close=-1.0),), OperationalDiagnosticCode.AS_OF_BAR_INVALID),
    ],
)
def test_as_of_failures_are_typed_and_do_not_classify(
    patches: None,
    monkeypatch: pytest.MonkeyPatch,
    rows: tuple[assembly._PanelRow, ...],
    code: OperationalDiagnosticCode,
) -> None:
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: rows)
    monkeypatch.setattr(assembly, "classify", lambda *_: pytest.fail("classifier must not run"))

    record = _assemble()

    assert record.availability is Availability.OPERATIONAL_FAILURE
    assert record.operational_diagnostics is code
    assert record.classification is None
    assert record.panel_snapshot_id is None


def test_zero_volume_terminal_bar_is_distinct_insufficient_history_diagnostic(
    patches: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = (*_rows(2), _row(date.fromordinal(AS_OF.toordinal() - 2), volume=0))
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: rows)

    record = _assemble()

    assert record.availability is Availability.AVAILABLE
    assert record.classification is not None
    assert record.classification.status is ClassificationStatus.INSUFFICIENT_HISTORY
    assert record.history_diagnostics is HistoryDiagnosticCode.ZERO_VOLUME_BAR_EXCLUDED


def test_calendar_session_does_not_prove_bar_exists(patches: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: ())
    record = _assemble()
    assert record.operational_diagnostics is OperationalDiagnosticCode.AS_OF_BAR_MISSING


def test_bar_on_non_session_is_not_eligible(patches: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembly, "is_trading_day", lambda _: False)
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: (_row(AS_OF),))
    record = _assemble()
    assert record.operational_diagnostics is OperationalDiagnosticCode.AS_OF_BAR_MISSING


def test_reference_failure_prevents_dto_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_: date) -> bool:
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(assembly, "is_trading_day", unavailable)
    monkeypatch.setattr(assembly, "classify", lambda *_: pytest.fail("classifier must not run"))
    record = _assemble()
    assert record.operational_diagnostics is OperationalDiagnosticCode.REFERENCE_BASIS_UNAVAILABLE


def test_lifecycle_diagnostic_failure_remains_reachable_after_classifier(
    patches: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assembly, "_load_panel_rows", lambda *_: (_row(AS_OF),))
    monkeypatch.setattr(assembly, "_load_lifecycle_basis", lambda _: assembly._LifecycleBasis(False, None))

    record = _assemble()

    assert record.classification is not None
    assert record.classification.status is ClassificationStatus.INSUFFICIENT_HISTORY
    assert record.history_diagnostics is HistoryDiagnosticCode.DIAGNOSIS_UNAVAILABLE


def test_unclassified_failure_has_explicit_fallback(patches: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def unknown(_: str, __: date, ___: int) -> tuple[assembly._PanelRow, ...]:
        raise RuntimeError("unexpected decode failure")

    monkeypatch.setattr(assembly, "_load_panel_rows", unknown)
    record = _assemble()
    assert record.operational_diagnostics is OperationalDiagnosticCode.UNCLASSIFIED_ASSEMBLY_FAILURE
