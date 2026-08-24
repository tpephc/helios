"""Contract tests for the pure PR-MS1.1 Market State classifier."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta

import pytest

from features import market_state
from features.market_state import (
    DEFAULT_CONFIG,
    AdjustedOhlcBar,
    ClassificationStatus,
    ClassifierReasonCode,
    ComparisonOperator,
    HistoryDiagnosticCode,
    MarketState,
    MarketStateClassifierConfig,
    MarketStateContractViolation,
    OperationalDiagnosticCode,
    SecurityMarketStateInput,
    batch_classify,
    classify,
)

# ───────────────────────────────────────────────────────────────────────────
# Synthetic canonical DTO fixtures
# ───────────────────────────────────────────────────────────────────────────


def _dto(closes: list[float], security_id: str = "0050") -> SecurityMarketStateInput:
    start = date(2026, 1, 2)
    bars = tuple(
        AdjustedOhlcBar(
            session=start + timedelta(days=index),
            adj_open=close,
            adj_high=close,
            adj_low=close,
            adj_close=close,
        )
        for index, close in enumerate(closes)
    )
    return SecurityMarketStateInput(security_id=security_id, as_of=bars[-1].session, bars=bars)


def _confirmed_closes() -> list[float]:
    return [100.0] * 49 + [101.0, 101.0, 101.0]


def _failed_closes() -> list[float]:
    return [100.0] * 49 + [99.0, 101.0, 99.0]


# ───────────────────────────────────────────────────────────────────────────
# Classifier result and structural-validation contract
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("closes", "expected_state", "expected_rule"),
    [
        (_confirmed_closes(), MarketState.CONFIRMED_RECLAIM, "confirmed_reclaim_ma50_k3"),
        (_failed_closes(), MarketState.FAILED_RECLAIM, "failed_reclaim_ma50"),
    ],
)
def test_positive_market_states(
    closes: list[float], expected_state: MarketState, expected_rule: str
) -> None:
    result = classify(_dto(closes))

    assert result.status is ClassificationStatus.OK
    assert result.state is expected_state
    assert result.matched_rule_id == expected_rule
    assert result.reason_code is None


def test_sufficient_non_match_has_locked_reason_and_nullability() -> None:
    result = classify(_dto([100.0] * 52))

    assert result.status is ClassificationStatus.INDETERMINATE
    assert result.state is None
    assert result.matched_rule_id is None
    assert result.reason_code is ClassifierReasonCode.NO_RULE_MATCH


def test_short_structural_valid_dto_returns_insufficient_history_without_rule_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_: object) -> bool:
        raise AssertionError("rules must not be evaluated for insufficient history")

    monkeypatch.setattr(market_state, "_rule_matches", fail_if_called)
    result = classify(_dto([100.0] * 51))

    assert result.status is ClassificationStatus.INSUFFICIENT_HISTORY
    assert result.state is None
    assert result.matched_rule_id is None
    assert result.reason_code is ClassifierReasonCode.REQUIRED_HISTORY_NOT_MET


@pytest.mark.parametrize(
    "builder",
    [
        lambda: SecurityMarketStateInput("0050", date(2026, 1, 2), ()),
        lambda: SecurityMarketStateInput("", date(2026, 1, 2), _dto([100.0]).bars),
        lambda: SecurityMarketStateInput("0050", date(2026, 1, 3), _dto([100.0]).bars),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (AdjustedOhlcBar(date(2026, 1, 2), 100.0, 100.0, 100.0, math.nan),),
        ),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (AdjustedOhlcBar(date(2026, 1, 2), 100.0, 99.0, 101.0, 100.0),),
        ),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (
                AdjustedOhlcBar(date(2026, 1, 2), 100.0, 100.0, 100.0, 100.0),
                AdjustedOhlcBar(date(2026, 1, 2), 100.0, 100.0, 100.0, 100.0),
            ),
        ),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (AdjustedOhlcBar(date(2026, 1, 2), -1.0, -1.0, -1.0, -1.0),),
        ),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (AdjustedOhlcBar(date(2026, 1, 2), 0.0, 0.0, 0.0, 0.0),),
        ),
        lambda: SecurityMarketStateInput(
            "0050",
            date(2026, 1, 2),
            (AdjustedOhlcBar(date(2026, 1, 2), math.inf, math.inf, math.inf, math.inf),),
        ),
    ],
)
def test_malformed_dto_raises_typed_exception(
    builder: Callable[[], SecurityMarketStateInput],
) -> None:
    with pytest.raises(MarketStateContractViolation):
        classify(builder())


def test_precedence_evaluates_all_rules_before_selecting_first_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def all_positive(rule: market_state.RuleSpec, _: object) -> bool:
        observed.append(rule.rule_id)
        return True

    monkeypatch.setattr(market_state, "_rule_matches", all_positive)
    result = classify(_dto([100.0] * 52))

    assert observed == [rule.rule_id for rule in DEFAULT_CONFIG.rules]
    assert result.status is ClassificationStatus.OK
    assert result.matched_rule_id == "failed_reclaim_ma50"


# ─────────────────────────────────────────────────────────────
# Equality, deadband, and transform contract
# ─────────────────────────────────────────────────────────────


def test_exact_equality_never_satisfies_confirmed_reclaim() -> None:
    boundary = 100.0
    assert not market_state._comparison_template_matches(
        (boundary, boundary, boundary),
        (boundary, boundary, boundary),
        (ComparisonOperator.GREATER_THAN,) * 3,
    )


def test_immediately_above_and_below_confirmed_boundary() -> None:
    boundary = 100.0
    above = math.nextafter(boundary, math.inf)
    below = math.nextafter(boundary, -math.inf)
    smas = (boundary, boundary, boundary)

    operators = (ComparisonOperator.GREATER_THAN,) * 3
    assert market_state._comparison_template_matches((above, above, above), smas, operators)
    assert not market_state._comparison_template_matches((below, above, above), smas, operators)


def test_failed_reclaim_equality_is_allowed_only_at_middle_comparison() -> None:
    boundary = 100.0
    below = math.nextafter(boundary, -math.inf)
    above = math.nextafter(boundary, math.inf)
    smas = (boundary, boundary, boundary)
    operators = (
        ComparisonOperator.LESS_THAN,
        ComparisonOperator.GREATER_THAN_OR_EQUAL,
        ComparisonOperator.LESS_THAN,
    )

    assert market_state._comparison_template_matches((below, boundary, below), smas, operators)
    assert market_state._comparison_template_matches((below, above, below), smas, operators)
    assert not market_state._comparison_template_matches((above, above, below), smas, operators)
    assert not market_state._comparison_template_matches((boundary, above, below), smas, operators)
    assert not market_state._comparison_template_matches((below, below, below), smas, operators)
    assert not market_state._comparison_template_matches((below, above, boundary), smas, operators)
    assert not market_state._comparison_template_matches((below, above, above), smas, operators)


def test_price_scale_invariance_outside_declared_deadband() -> None:
    original = _dto(_failed_closes())
    baseline = classify(original)
    rule_bars = original.bars[-52:]
    smas = market_state._template_smas(
        tuple(bar.adj_close for bar in rule_bars),
        lookback=50,
        sessions=3,
    )
    for close, sma in zip(tuple(bar.adj_close for bar in rule_bars[-3:]), smas, strict=True):
        assert abs(close - sma) / max(abs(close), abs(sma)) > 1e-10

    for factor in (0.01, 0.5, 2.0, 100.0):
        scaled = _dto([close * factor for close in _failed_closes()])
        assert classify(scaled).status is baseline.status
        assert classify(scaled).state is baseline.state
        assert classify(scaled).matched_rule_id == baseline.matched_rule_id


def test_batch_is_order_preserving_and_equivalent_to_scalar_calls() -> None:
    inputs = [_dto(_confirmed_closes(), "A"), _dto(_failed_closes(), "B"), _dto([100.0] * 52, "C")]

    assert batch_classify(inputs) == [classify(dto) for dto in inputs]


# ─────────────────────────────────────────────────────────────
# Batch, enum, and immutable-configuration contract
# ─────────────────────────────────────────────────────────────


def test_batch_with_malformed_item_fails_the_entire_call() -> None:
    valid = _dto(_confirmed_closes())
    malformed = SecurityMarketStateInput("0050", date(2026, 1, 2), ())

    with pytest.raises(MarketStateContractViolation):
        batch_classify([valid, malformed])


def test_empty_batch_is_empty() -> None:
    assert batch_classify([]) == []


def test_reason_and_diagnostic_value_spaces_are_disjoint() -> None:
    classifier_values = {member.value for member in ClassifierReasonCode}
    history_values = {member.value for member in HistoryDiagnosticCode}
    operational_values = {member.value for member in OperationalDiagnosticCode}

    assert classifier_values.isdisjoint(history_values)
    assert classifier_values.isdisjoint(operational_values)
    assert history_values.isdisjoint(operational_values)


def test_default_config_is_immutable_and_stable_across_calls() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_CONFIG.classifier_version = "mutated"  # type: ignore[misc]

    first = classify(_dto(_confirmed_closes()))
    second = classify(_dto(_confirmed_closes()))
    assert first == second
    assert first.classifier_version == "1.0.0"
    assert re.fullmatch(r"[0-9a-f]{64}", first.rule_set_hash)
    assert first.rule_set_hash == DEFAULT_CONFIG.rule_set_hash


def test_hash_and_evaluation_change_with_declared_comparison_operator() -> None:
    changed_confirmed = replace(
        DEFAULT_CONFIG.rules[2],
        comparison_operators=(ComparisonOperator.GREATER_THAN_OR_EQUAL,) * 3,
    )
    changed_config = MarketStateClassifierConfig(
        classifier_version=DEFAULT_CONFIG.classifier_version,
        rules=(
            DEFAULT_CONFIG.rules[0],
            DEFAULT_CONFIG.rules[1],
            changed_confirmed,
            DEFAULT_CONFIG.rules[3],
        ),
    )

    assert changed_config.rule_set_hash != DEFAULT_CONFIG.rule_set_hash
    changed_result = classify(_dto([100.0] * 52), changed_config)
    assert changed_result.status is ClassificationStatus.OK
    assert changed_result.matched_rule_id == "confirmed_reclaim_ma50_k3"


def test_config_rejects_non_v1_session_template() -> None:
    invalid_rule = replace(DEFAULT_CONFIG.rules[0], sessions=2)
    with pytest.raises(ValueError, match="three-session"):
        MarketStateClassifierConfig(
            classifier_version=DEFAULT_CONFIG.classifier_version,
            rules=(
                invalid_rule,
                DEFAULT_CONFIG.rules[1],
                DEFAULT_CONFIG.rules[2],
                DEFAULT_CONFIG.rules[3],
            ),
        )


def test_default_rule_set_hash_has_a_golden_value() -> None:
    expected_hash = "036abf8965b6ed8a011903f89aa29f9c05b192f8c37c1c06d99a30fc6e2428d2"
    assert DEFAULT_CONFIG.rule_set_hash == expected_hash
