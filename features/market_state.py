# features/market_state.py
"""Pure, deterministic Security Market State V1 classifier.

This module intentionally has no data-access, calendar, assembly, export, or
strategy dependencies.  Assembly owns canonical-panel construction; this
module validates and classifies the resulting adjusted-OHLC DTO only.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from hashlib import sha256
from typing import Final

# ───────────────────────────────────────────────────────────────────────────
# Domain vocabulary
# ───────────────────────────────────────────────────────────────────────────


class MarketState(Enum):
    """Classifier-owned positive Market State vocabulary."""

    CONFIRMED_RECLAIM = "confirmed_reclaim"
    FAILED_RECLAIM = "failed_reclaim"


class ClassificationStatus(Enum):
    """Classifier-owned outcome status."""

    OK = "ok"
    INDETERMINATE = "indeterminate"
    INSUFFICIENT_HISTORY = "insufficient_history"


class ClassifierReasonCode(Enum):
    """Classifier-owned explanation for a non-OK outcome."""

    NO_RULE_MATCH = "no_rule_match"
    REQUIRED_HISTORY_NOT_MET = "required_history_not_met"


class Availability(Enum):
    """Assembly-owned public-envelope availability vocabulary."""

    AVAILABLE = "available"
    OPERATIONAL_FAILURE = "operational_failure"


class HistoryDiagnosticCode(Enum):
    """Assembly-owned explanation for insufficient eligible history."""

    NATURAL_HISTORY_SHORTFALL = "natural_history_shortfall"
    DATA_GAP = "data_gap"
    DIAGNOSIS_UNAVAILABLE = "diagnosis_unavailable"
    ZERO_VOLUME_BAR_EXCLUDED = "zero_volume_bar_excluded"


class OperationalDiagnosticCode(Enum):
    """Assembly-owned explanation for an operational-failure envelope."""

    AS_OF_BAR_MISSING = "as_of_bar_missing"
    AS_OF_BAR_INVALID = "as_of_bar_invalid"
    AS_OF_BAR_ZERO_VOLUME = "as_of_bar_zero_volume"
    REFERENCE_BASIS_UNAVAILABLE = "reference_basis_unavailable"
    UNCLASSIFIED_ASSEMBLY_FAILURE = "unclassified_assembly_failure"


class LimitStatusCoverage(Enum):
    """Assembly-owned capability marker; never a classifier input."""

    OFFICIAL_STATUS_UNAVAILABLE = "official_status_unavailable"


class ComparisonOperator(Enum):
    """Internal exact relational operators for declarative V1 rule predicates."""

    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"


class MarketStateContractViolation(ValueError):  # noqa: N818
    """Raised when a DTO is structurally malformed at the classifier boundary."""


# ───────────────────────────────────────────────────────────────────────────
# Classifier DTO and immutable configuration
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AdjustedOhlcBar:
    """One adjusted OHLC observation supplied by canonical assembly."""

    session: date
    adj_open: float
    adj_high: float
    adj_low: float
    adj_close: float


@dataclass(frozen=True, slots=True)
class SecurityMarketStateInput:
    """Canonical classifier DTO for one security and close-inclusive as_of."""

    security_id: str
    as_of: date
    bars: Sequence[AdjustedOhlcBar]

    def __post_init__(self) -> None:
        """Freeze a caller-provided sequence without deciding its validity."""
        object.__setattr__(self, "bars", tuple(self.bars))


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Pure classifier result; assembly/export fields are intentionally absent."""

    status: ClassificationStatus
    state: MarketState | None
    matched_rule_id: str | None
    reason_code: ClassifierReasonCode | None
    classifier_version: str
    rule_set_hash: str
    as_of: date


@dataclass(frozen=True, slots=True)
class NumericPolicy:
    """Locked numeric and validation semantics that contribute to rule identity."""

    representation: str = "ieee754_binary64"
    comparison_policy: str = "exact_relational"
    epsilon_relative: float = 1e-10
    required_prices: str = "finite_positive"
    missing_nonfinite_policy: str = "structural_contract_violation"


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """Declarative fixed V1 rule metadata used for evaluation and hashing."""

    rule_id: str
    state: MarketState
    lookback: int
    sessions: int
    template: str
    comparison_operators: tuple[ComparisonOperator, ...]
    transform_group: str = "PRICE_SCALE"
    deadband_policy: str = "relative_epsilon_excluded_in_property_tests_only"
    source_fields: tuple[str, ...] = (
        "adj_open",
        "adj_high",
        "adj_low",
        "adj_close",
    )
    adjustment_basis: str = "canonical_adjusted_ohlc"

    @property
    def required_history_sessions(self) -> int:
        """Return L + K - 1 for the rule's SMA_L K-session template."""
        return self.lookback + self.sessions - 1


FAILED_RECLAIM_MA50: Final = RuleSpec(
    rule_id="failed_reclaim_ma50",
    state=MarketState.FAILED_RECLAIM,
    lookback=50,
    sessions=3,
    template="failed_reclaim_t_minus_2_lt_t_minus_1_gte_t_lt_sma",
    comparison_operators=(
        ComparisonOperator.LESS_THAN,
        ComparisonOperator.GREATER_THAN_OR_EQUAL,
        ComparisonOperator.LESS_THAN,
    ),
)
FAILED_RECLAIM_MA20: Final = RuleSpec(
    rule_id="failed_reclaim_ma20",
    state=MarketState.FAILED_RECLAIM,
    lookback=20,
    sessions=3,
    template="failed_reclaim_t_minus_2_lt_t_minus_1_gte_t_lt_sma",
    comparison_operators=(
        ComparisonOperator.LESS_THAN,
        ComparisonOperator.GREATER_THAN_OR_EQUAL,
        ComparisonOperator.LESS_THAN,
    ),
)
CONFIRMED_RECLAIM_MA50: Final = RuleSpec(
    rule_id="confirmed_reclaim_ma50_k3",
    state=MarketState.CONFIRMED_RECLAIM,
    lookback=50,
    sessions=3,
    template="confirmed_reclaim_three_consecutive_gt_sma",
    comparison_operators=(ComparisonOperator.GREATER_THAN,) * 3,
)
CONFIRMED_RECLAIM_MA20: Final = RuleSpec(
    rule_id="confirmed_reclaim_ma20_k3",
    state=MarketState.CONFIRMED_RECLAIM,
    lookback=20,
    sessions=3,
    template="confirmed_reclaim_three_consecutive_gt_sma",
    comparison_operators=(ComparisonOperator.GREATER_THAN,) * 3,
)


@dataclass(frozen=True, slots=True)
class MarketStateClassifierConfig:
    """Immutable, fully declared configuration for the fixed V1 classifier."""

    classifier_version: str
    rules: tuple[RuleSpec, ...]
    numeric_policy: NumericPolicy = NumericPolicy()
    rule_set_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate V1's closed rule set and derive its deterministic digest."""
        if not self.classifier_version:
            raise ValueError("classifier_version must be non-empty")
        expected = (
            FAILED_RECLAIM_MA50.rule_id,
            FAILED_RECLAIM_MA20.rule_id,
            CONFIRMED_RECLAIM_MA50.rule_id,
            CONFIRMED_RECLAIM_MA20.rule_id,
        )
        actual = tuple(rule.rule_id for rule in self.rules)
        if actual != expected:
            raise ValueError("V1 rules must be the declared total precedence order")
        if any(rule.sessions != 3 for rule in self.rules):
            raise ValueError("V1 rules must use the locked three-session template")
        if any(len(rule.comparison_operators) != rule.sessions for rule in self.rules):
            raise ValueError("rule comparison operators must match the declared session count")
        object.__setattr__(self, "rule_set_hash", _rule_set_hash(self.rules, self.numeric_policy))

    @property
    def required_history_sessions(self) -> int:
        """Return the classifier-owned maximum required history scalar."""
        return max(rule.required_history_sessions for rule in self.rules)


def _canonical_rule_payload(
    rules: tuple[RuleSpec, ...], numeric_policy: NumericPolicy
) -> dict[str, object]:
    """Return the explicitly versioned canonical payload for SHA-256 identity."""
    return {
        "canonicalization_version": 1,
        "vocabulary": [member.value for member in MarketState],
        "rules": [
            {
                "adjustment_basis": rule.adjustment_basis,
                "comparison_operators": [
                    comparison.value for comparison in rule.comparison_operators
                ],
                "deadband_policy": rule.deadband_policy,
                "lookback": rule.lookback,
                "required_history_sessions": rule.required_history_sessions,
                "rule_id": rule.rule_id,
                "sessions": rule.sessions,
                "source_fields": list(rule.source_fields),
                "state": rule.state.value,
                "template": rule.template,
                "transform_group": rule.transform_group,
            }
            for rule in rules
        ],
        "numeric_policy": {
            "comparison_policy": numeric_policy.comparison_policy,
            "epsilon_relative": numeric_policy.epsilon_relative,
            "missing_nonfinite_policy": numeric_policy.missing_nonfinite_policy,
            "representation": numeric_policy.representation,
            "required_prices": numeric_policy.required_prices,
        },
    }


def _rule_set_hash(rules: tuple[RuleSpec, ...], numeric_policy: NumericPolicy) -> str:
    """Digest canonical UTF-8 JSON without runtime state or timestamps."""
    payload = _canonical_rule_payload(rules, numeric_policy)
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return sha256(encoded).hexdigest()


DEFAULT_CONFIG: Final = MarketStateClassifierConfig(
    classifier_version="1.0.0",
    rules=(
        FAILED_RECLAIM_MA50,
        FAILED_RECLAIM_MA20,
        CONFIRMED_RECLAIM_MA50,
        CONFIRMED_RECLAIM_MA20,
    ),
)


# ─────────────────────────────────────────────────────────────
# Public classifier API
# ─────────────────────────────────────────────────────────────


def classify(
    dto: SecurityMarketStateInput,
    config: MarketStateClassifierConfig = DEFAULT_CONFIG,
) -> ClassificationResult:
    """Classify one structural-valid DTO using no I/O or hidden state.

    Args:
        dto: Canonical adjusted-OHLC input ending at its close-inclusive as_of.
        config: Immutable classifier configuration. Defaults to the locked V1 set.

    Returns:
        A deterministic classifier result. Short but structural-valid history
        returns INSUFFICIENT_HISTORY; it is not a validation error.

    Raises:
        MarketStateContractViolation: If dto is structurally malformed.
    """
    _validate_dto(dto)
    if len(dto.bars) < config.required_history_sessions:
        return _insufficient_history_result(dto, config)

    matches: list[RuleSpec] = []
    for rule in config.rules:
        rule_bars = dto.bars[-rule.required_history_sessions :]
        if _rule_matches(rule, rule_bars):
            matches.append(rule)

    if not matches:
        return ClassificationResult(
            status=ClassificationStatus.INDETERMINATE,
            state=None,
            matched_rule_id=None,
            reason_code=ClassifierReasonCode.NO_RULE_MATCH,
            classifier_version=config.classifier_version,
            rule_set_hash=config.rule_set_hash,
            as_of=dto.as_of,
        )

    selected = matches[0]
    return ClassificationResult(
        status=ClassificationStatus.OK,
        state=selected.state,
        matched_rule_id=selected.rule_id,
        reason_code=None,
        classifier_version=config.classifier_version,
        rule_set_hash=config.rule_set_hash,
        as_of=dto.as_of,
    )


def batch_classify(
    dtos: Sequence[SecurityMarketStateInput],
    config: MarketStateClassifierConfig = DEFAULT_CONFIG,
) -> list[ClassificationResult]:
    """Classify an all-valid batch; malformed input fails the entire call.

    Args:
        dtos: Inputs to validate before any history or rule evaluation occurs.
        config: Immutable classifier configuration shared by every batch item.

    Returns:
        Results in the same order as dtos, or an empty list for an empty batch.

    Raises:
        MarketStateContractViolation: If any item is structurally malformed.
    """
    materialized = tuple(dtos)
    for dto in materialized:
        _validate_dto(dto)
    return [classify(dto, config) for dto in materialized]


# ─────────────────────────────────────────────────────────────
# Structural validation and deterministic rule evaluation
# ─────────────────────────────────────────────────────────────


def _validate_dto(dto: SecurityMarketStateInput) -> None:
    """Raise only for structural DTO violations, never for short history."""
    if not isinstance(dto, SecurityMarketStateInput):
        raise MarketStateContractViolation("dto must be SecurityMarketStateInput")
    if not isinstance(dto.security_id, str) or not dto.security_id:
        raise MarketStateContractViolation("security_id must be a non-empty string")
    if type(dto.as_of) is not date:
        raise MarketStateContractViolation("as_of must be a date without a time component")
    if not dto.bars:
        raise MarketStateContractViolation("bars must be non-empty")

    previous_session: date | None = None
    for bar in dto.bars:
        if not isinstance(bar, AdjustedOhlcBar):
            raise MarketStateContractViolation("bars must contain AdjustedOhlcBar values")
        if type(bar.session) is not date:
            raise MarketStateContractViolation(
                "bar session must be a date without a time component"
            )
        if previous_session is not None and bar.session <= previous_session:
            raise MarketStateContractViolation("bar sessions must be strictly ascending")
        previous_session = bar.session
        _validate_bar_prices(bar)

    if dto.bars[-1].session != dto.as_of:
        raise MarketStateContractViolation("last bar session must equal as_of")


def _validate_bar_prices(bar: AdjustedOhlcBar) -> None:
    """Validate finite positive binary64 operands and OHLC ordering."""
    prices = (bar.adj_open, bar.adj_high, bar.adj_low, bar.adj_close)
    if any(type(price) is not float or not math.isfinite(price) or price <= 0 for price in prices):
        raise MarketStateContractViolation("adjusted OHLC prices must be finite positive floats")
    if not (
        bar.adj_low <= min(bar.adj_open, bar.adj_close)
        and max(bar.adj_open, bar.adj_close) <= bar.adj_high
    ):
        raise MarketStateContractViolation("adjusted OHLC ordering is invalid")


def _insufficient_history_result(
    dto: SecurityMarketStateInput, config: MarketStateClassifierConfig
) -> ClassificationResult:
    """Return the classifier-owned short-history result before rule evaluation."""
    return ClassificationResult(
        status=ClassificationStatus.INSUFFICIENT_HISTORY,
        state=None,
        matched_rule_id=None,
        reason_code=ClassifierReasonCode.REQUIRED_HISTORY_NOT_MET,
        classifier_version=config.classifier_version,
        rule_set_hash=config.rule_set_hash,
        as_of=dto.as_of,
    )


def _rule_matches(rule: RuleSpec, bars: Sequence[AdjustedOhlcBar]) -> bool:
    """Evaluate exactly one rule from only its contractually trailing panel."""
    closes = tuple(bar.adj_close for bar in bars)
    sma_values = _template_smas(closes, rule.lookback, rule.sessions)
    trailing_closes = closes[-rule.sessions :]
    return _comparison_template_matches(
        trailing_closes,
        sma_values,
        rule.comparison_operators,
    )


def _template_smas(
    closes: Sequence[float], lookback: int, sessions: int
) -> tuple[float, ...]:
    """Compute one SMA_L value for each position in a K-session template."""
    required = lookback + sessions - 1
    if len(closes) != required:
        raise ValueError("rule bars must have exactly L + K - 1 observations")
    return tuple(
        math.fsum(closes[offset : offset + lookback]) / lookback
        for offset in range(sessions)
    )


def _comparison_template_matches(
    closes: Sequence[float],
    smas: Sequence[float],
    operators: Sequence[ComparisonOperator],
) -> bool:
    """Apply declared exact operators; no template semantics live outside rule data."""
    if not (len(closes) == len(smas) == len(operators)):
        raise ValueError("comparison template operands must have equal lengths")
    return all(
        _compare(close, sma, operator)
        for close, sma, operator in zip(closes, smas, operators, strict=True)
    )


def _compare(left: float, right: float, operator: ComparisonOperator) -> bool:
    """Evaluate one exact binary64 relational operator declared by a rule."""
    if operator is ComparisonOperator.GREATER_THAN:
        return left > right
    if operator is ComparisonOperator.GREATER_THAN_OR_EQUAL:
        return left >= right
    if operator is ComparisonOperator.LESS_THAN:
        return left < right
    raise ValueError(f"unsupported comparison operator: {operator}")
