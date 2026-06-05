# data/eligible_universe.py
"""Panel eligibility predicate — v1.1.0.

Provides the SQL predicate that enforces listed-market panel eligibility.

Helios research panel scope is TWSE / TPEx listed-market only.
EMERGING-period rows (otc_first_date <= date < mainboard_date) reflect a
different market microstructure (no price limits, different liquidity
regime) and are excluded from the research panel.

The predicate retains the COALESCE pass-through so stocks without any
lifecycle record are unaffected.

For the 18 v1 seed stocks the predicate is equivalent to:
    date >= mainboard_date

For stocks without a lifecycle record:
    no filter applied (DATE '1900-01-01' sentinel)

Confirmed contamination: 7331 EMERGING-period rows across 18 stocks
in daily_price_adj.  Source: research/P1-DATA_panel_integrity_assessment.md

Changelog:
    v1.0.0 (2026-06-05): Initial — used otc_first_date (date >= MIN(listed_from))
    v1.1.0 (2026-06-05): Corrected to listed-market predicate (date >= mainboard_date)
                         Filter: market IN ('TWSE', 'TPEx')

Authority: SPEC-P1-DATA-REMEDIATION-v1 § 6

Note: compute_bullish_features.py and compute_bearish_features.py apply
this predicate defensively during Phase 2 remediation.  Once daily_features
is rebuilt from the remediated panel, the predicate should be removed from
those scripts and daily_features treated as the single source of truth.

Future cleanup (Phase 3+): rename to panel_start_date_predicate() to
reflect that this is a start-date gate, not a full lifecycle eligibility
check (no listed_to / suspension / delisting filtering).
"""


def eligible_date_predicate(alias: str) -> str:
    """Return SQL WHERE fragment enforcing listed-market panel eligibility.

    Stocks with a security_lifecycle record are filtered to dates on or
    after their earliest TWSE/TPEx listed_from (i.e. mainboard_date for
    transfer-board stocks).  EMERGING-period rows are excluded.

    Stocks without any lifecycle record are passed through via COALESCE
    to DATE '1900-01-01' (no filter applied).

    Parameters
    ----------
    alias:
        Table alias for the price/feature table (e.g. ``'p'`` for
        ``daily_price_adj p``).  Must match the alias used in the
        surrounding query.

    Returns
    -------
    str
        SQL fragment suitable for use in a WHERE clause.  Does not
        include the leading ``AND`` keyword.

    Examples
    --------
    >>> eligible_date_predicate('p')
    "p.date >= COALESCE(\\n    (SELECT MIN(l.listed_from) ..."
    """
    return f"""{alias}.date >= COALESCE(
    (
        SELECT MIN(l.listed_from)
        FROM   security_lifecycle l
        WHERE  l.stock_id = {alias}.stock_id
          AND  l.market IN ('TWSE', 'TPEx')
    ),
    DATE '1900-01-01'
)"""
