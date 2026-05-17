# backtest/__init__.py
"""Backtest module — full deterministic trade lifecycle simulation.

v0.1.13.2: round_trip.py — entry → exit lifecycle (unconstrained)
v0.1.14.1: portfolio_simulator.py — adds capital + risk budget constraints
"""
from backtest.portfolio_simulator import (
    EquitySnapshot,
    PortfolioBacktest,
    PortfolioMetrics,
    PortfolioPosition,
    SignalDecision,
    compute_portfolio_metrics,
)
from backtest.round_trip import (
    NO_COSTS,
    RoundTripBacktest,
    RoundTripMetrics,
    TransactionCosts,
    compute_metrics,
    partition_by_date,
)

__all__ = [
    "NO_COSTS",
    "EquitySnapshot",
    "PortfolioBacktest",
    "PortfolioMetrics",
    "PortfolioPosition",
    "RoundTripBacktest",
    "RoundTripMetrics",
    "SignalDecision",
    "TransactionCosts",
    "compute_metrics",
    "compute_portfolio_metrics",
    "partition_by_date",
]
