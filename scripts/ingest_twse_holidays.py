#!/usr/bin/env python3
# scripts/ingest_twse_holidays.py
"""Ingest TWSE official holiday schedule into twse_holidays — v1.0.0.

Fetches the TWSE /holidaySchedule/holidaySchedule endpoint (current ROC year
only) and upserts results into the twse_holidays table.

Limitations (documented, not defects):
  - The TWSE OpenAPI endpoint returns only the current ROC year.
    Historical years are not available via this endpoint.
  - The `year` query parameter is silently ignored by the API; do not
    pass it expecting historical data.
  - Weekend make-up trading sessions are NOT tracked here. The calendar
    model treats Saturday/Sunday as closed by policy (see trading_calendar.py).

Usage:
    # Ingest current year (normal annual run, typically in January):
    uv run python scripts/ingest_twse_holidays.py

    # Dry-run (print parsed rows, no DB write):
    uv run python scripts/ingest_twse_holidays.py --dry-run

    # Override ROC year for manual backfill (data must already be available):
    uv run python scripts/ingest_twse_holidays.py --year-roc 114
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from typing import NamedTuple

import requests

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)

_TWSE_HOLIDAY_URL = (
    "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
)
_REQUEST_TIMEOUT_S = 15

# Names indicating a trading-day announcement, not a market closure.
# The TWSE holiday schedule includes informational notices for the first
# and last trading days of holiday periods; these must not be ingested
# as holidays.
_TRADING_DAY_NOTICE_KEYWORDS: tuple[str, ...] = ("交易日",)
_ROC_YEAR_OFFSET = 1911  # ROC year + 1911 = Gregorian year


class HolidayRow(NamedTuple):
    holiday_date: date
    holiday_name: str
    source: str
    year_roc: int


def _roc_date_to_gregorian(roc_date_str: str) -> date:
    """Convert a ROC date string (e.g. '1150101') to a Gregorian date.

    Format: YYYMMDD where YYY is the ROC year (3 digits, zero-padded).

    Args:
        roc_date_str: ROC date in YYYMMDD format.

    Returns:
        Gregorian date.

    Raises:
        ValueError: If the string does not match the expected format or
                    produces an invalid calendar date.
    """
    if len(roc_date_str) != 7 or not roc_date_str.isdigit():
        raise ValueError(
            f"Unexpected ROC date format: {roc_date_str!r}. "
            "Expected 7-digit YYYMMDD."
        )
    roc_year = int(roc_date_str[:3])
    month = int(roc_date_str[3:5])
    day = int(roc_date_str[5:7])
    gregorian_year = roc_year + _ROC_YEAR_OFFSET
    return date(gregorian_year, month, day)


def fetch_holiday_rows(year_roc: int | None = None) -> list[HolidayRow]:
    """Fetch and parse TWSE holiday schedule.

    Args:
        year_roc: ROC year to tag the rows with. If None, inferred from
                  the first row returned by the API. The API itself does
                  not filter by year; this parameter is metadata only.

    Returns:
        List of HolidayRow instances, one per non-trading day announced.

    Raises:
        requests.RequestException: On network or HTTP error.
        ValueError: If the API response is malformed.
    """
    logger.info("twse_holiday_fetch_start", url=_TWSE_HOLIDAY_URL)

    resp = requests.get(_TWSE_HOLIDAY_URL, timeout=_REQUEST_TIMEOUT_S)
    resp.raise_for_status()

    raw: list[dict] = resp.json()
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            f"Unexpected API response shape: {type(raw)}, len={len(raw) if isinstance(raw, list) else 'N/A'}"
        )

    rows: list[HolidayRow] = []
    parse_errors: list[str] = []

    for item in raw:
        roc_str = item.get("Date", "")
        name = item.get("Name", "").strip()

        if not roc_str or not name:
            parse_errors.append(f"missing fields in item: {item!r}")
            continue

        if any(kw in name for kw in _TRADING_DAY_NOTICE_KEYWORDS):
            logger.info(
                "twse_holiday_skipped_trading_notice",
                date=roc_str,
                name=name,
            )
            continue

        try:
            holiday_date = _roc_date_to_gregorian(roc_str)
        except ValueError as exc:
            parse_errors.append(str(exc))
            continue

        # Infer year_roc from API data if not explicitly provided
        inferred_year = int(roc_str[:3])
        effective_year = year_roc if year_roc is not None else inferred_year

        rows.append(
            HolidayRow(
                holiday_date=holiday_date,
                holiday_name=name,
                source="TWSE_API",
                year_roc=effective_year,
            )
        )

    if parse_errors:
        logger.warning(
            "twse_holiday_parse_errors",
            count=len(parse_errors),
            errors=parse_errors[:5],  # truncate for log readability
        )

    logger.info(
        "twse_holiday_fetch_complete",
        raw_items=len(raw),
        parsed_rows=len(rows),
        parse_errors=len(parse_errors),
    )
    return rows


def upsert_holidays(rows: list[HolidayRow]) -> dict[str, int]:
    """Upsert holiday rows into the twse_holidays table.

    Uses INSERT OR REPLACE semantics (DuckDB: INSERT OR REPLACE INTO).
    Existing rows with the same holiday_date are overwritten; ingested_at
    is refreshed on update.

    Args:
        rows: Parsed holiday rows from fetch_holiday_rows().

    Returns:
        Dict with keys 'upserted' and 'total_after'.
    """
    if not rows:
        logger.warning("twse_holiday_upsert_empty_input")
        return {"upserted": 0, "total_after": 0}

    now = datetime.now(timezone.utc)
    upsert_sql = """
        INSERT OR REPLACE INTO twse_holidays
            (holiday_date, holiday_name, source, year_roc, ingested_at)
        VALUES (?, ?, ?, ?, ?)
    """

    with connect() as conn:
        for row in rows:
            conn.execute(
                upsert_sql,
                [row.holiday_date, row.holiday_name, row.source, row.year_roc, now],
            )

        total = conn.execute(
            "SELECT COUNT(*) FROM twse_holidays"
        ).fetchone()[0]

    logger.info(
        "twse_holiday_upsert_complete",
        upserted=len(rows),
        total_after=total,
    )
    return {"upserted": len(rows), "total_after": total}


def print_rows(rows: list[HolidayRow]) -> None:
    """Print parsed rows to stdout for dry-run inspection."""
    print(f"{'Date':<12} {'Year ROC':>8}  {'Source':<10}  Name")
    print("-" * 70)
    for r in sorted(rows, key=lambda x: x.holiday_date):
        print(
            f"{r.holiday_date!s:<12} {r.year_roc:>8}  {r.source:<10}  {r.holiday_name}"
        )
    print(f"\nTotal: {len(rows)} rows")


def main(dry_run: bool = False, year_roc: int | None = None) -> None:
    """Run the ingestion pipeline.

    Args:
        dry_run: If True, fetch and parse but do not write to DB.
        year_roc: Override ROC year metadata tag. Normally inferred from API.
    """
    try:
        rows = fetch_holiday_rows(year_roc=year_roc)
    except requests.RequestException as exc:
        logger.error("twse_holiday_fetch_failed", error=str(exc))
        print(f"[ERROR] Network error fetching TWSE holidays: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        logger.error("twse_holiday_parse_failed", error=str(exc))
        print(f"[ERROR] Parse error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("[WARN] No holiday rows parsed from API response.", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("[DRY RUN] Parsed rows (not written to DB):\n")
        print_rows(rows)
        return

    result = upsert_holidays(rows)
    print(
        f"[OK] Upserted {result['upserted']} holiday rows. "
        f"Total in twse_holidays: {result['total_after']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest TWSE holiday schedule into twse_holidays table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print rows without writing to the database.",
    )
    parser.add_argument(
        "--year-roc",
        type=int,
        default=None,
        metavar="YYY",
        help=(
            "Override ROC year metadata tag (e.g. 114 for 2025). "
            "Normally inferred from the API response. "
            "The API itself does not support year filtering."
        ),
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, year_roc=args.year_roc)
