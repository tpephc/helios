#!/usr/bin/env python3
# tests/test_order_transitions_v0_1_17.py
"""Invariant tests for v0.1.17 order state machine.

Pre-registered invariants:
  INV-EXEC-1: same order_id cannot be submitted twice
  INV-EXEC-3: READY_FOR_SUBMISSION → only {SUBMITTED, EXPIRED, FAILED}
  INV-EXEC-4: execution_submitter is rerun-safe (idempotent)
  INV-2: backtest gap filter == live limit price ceiling (deferred to Phase 6)

Version: v0.1.17 (2026-05-27)
"""
from __future__ import annotations

import pytest
from execution.order_types import OrderStatus


class TestReadyForSubmissionTransitions:
    """INV-EXEC-3: READY_FOR_SUBMISSION can only reach allowed states."""

    def test_allowed_transitions(self) -> None:
        from storage.order_journal import _LEGITIMATE_TRANSITIONS

        allowed = _LEGITIMATE_TRANSITIONS[OrderStatus.READY_FOR_SUBMISSION]
        assert allowed == frozenset({
            OrderStatus.SUBMITTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        })

    @pytest.mark.parametrize("bad_target", [
        OrderStatus.FILLED,
        OrderStatus.PARTIAL,
        OrderStatus.CANCELLED,
        OrderStatus.INTENT,
        OrderStatus.READY_FOR_SUBMISSION,
    ])
    def test_illegal_transitions_rejected(self, bad_target: OrderStatus) -> None:
        from storage.order_journal import _validate_transition, InvalidTransition

        with pytest.raises(InvalidTransition):
            _validate_transition(OrderStatus.READY_FOR_SUBMISSION, bad_target)


class TestIntentToReadyTransition:
    """INTENT can now transition to READY_FOR_SUBMISSION."""

    def test_intent_to_ready_allowed(self) -> None:
        from storage.order_journal import _validate_transition
        _validate_transition(OrderStatus.INTENT, OrderStatus.READY_FOR_SUBMISSION)

    def test_intent_to_submitted_still_allowed(self) -> None:
        """Legacy direct-submit path preserved."""
        from storage.order_journal import _validate_transition
        _validate_transition(OrderStatus.INTENT, OrderStatus.SUBMITTED)

    def test_intent_to_failed_still_allowed(self) -> None:
        from storage.order_journal import _validate_transition
        _validate_transition(OrderStatus.INTENT, OrderStatus.FAILED)


class TestOrderStatusProperties:
    """READY_FOR_SUBMISSION has correct property values."""

    def test_not_terminal(self) -> None:
        assert not OrderStatus.READY_FOR_SUBMISSION.is_terminal

    def test_is_in_flight(self) -> None:
        assert OrderStatus.READY_FOR_SUBMISSION.is_in_flight

    def test_all_terminals_unchanged(self) -> None:
        for s in (OrderStatus.FILLED, OrderStatus.PARTIAL, OrderStatus.FAILED,
                  OrderStatus.CANCELLED, OrderStatus.EXPIRED):
            assert s.is_terminal, f"{s.value} should be terminal"

    def test_all_in_flight_states(self) -> None:
        for s in (OrderStatus.INTENT, OrderStatus.READY_FOR_SUBMISSION,
                  OrderStatus.SUBMITTED):
            assert s.is_in_flight, f"{s.value} should be in_flight"


class TestTransitionMapClosure:
    """Every OrderStatus value must appear in the transition map."""

    def test_all_statuses_in_map(self) -> None:
        from storage.order_journal import _LEGITIMATE_TRANSITIONS
        for status in OrderStatus:
            assert status in _LEGITIMATE_TRANSITIONS, (
                f"{status.value} missing from _LEGITIMATE_TRANSITIONS"
            )

    def test_terminal_states_empty(self) -> None:
        from storage.order_journal import _LEGITIMATE_TRANSITIONS
        for status in OrderStatus:
            if status.is_terminal:
                assert _LEGITIMATE_TRANSITIONS[status] == frozenset(), (
                    f"Terminal {status.value} should have no transitions"
                )
