# portfolio/selector.py
"""Sector classification and selection helpers — v0.2.0.

Sector is derived dynamically from company_metadata.industry_code via
INDUSTRY_SECTOR_MAP.  The v0.1 hardcoded SECTOR_MAP (15 symbols) is removed;
any stock not found in company_metadata returns 'unknown'.

TWSE industry_code → sector grouping rationale:
  semi        : 24 (semiconductor)
  electronics : 25 (computer/peripherals), 26 (optoelectronics),
                27 (comms/network), 28 (electronic components),
                31 (EMS/ODM)
  financial   : 17 (financial/insurance)
  materials   : 01 (cement/glass), 03 (plastics), 08 (paper), 10 (rubber),
                12 (steel/metals)
  industrials : 05 (electrical mfg), 06 (wire/cable), 21 (other mfg),
                38 (management svc)
  consumer    : 02 (food), 04 (textiles), 11 (auto), 18 (tourism),
                20 (trading/retail), 37 (cultural/media)
  transport   : 15 (shipping/logistics)
  real_estate : 14 (construction)
  healthcare  : 22 (pharma/medical), 35 (biotech)
  tech_svc    : 29 (information svc), 36 (internet/ecomm)
  energy      : 23 (oil/gas)
  foreign     : 91 (DR/foreign listings)

ETFs are identified by is_etf() heuristic (stock_id starts with '0') and
bypass the industry_code path entirely.

Version: v0.2.0 (2026-06-01)
"""
from __future__ import annotations

from functools import lru_cache

# ---------------------------------------------------------------------------
# Industry code → sector mapping
# ---------------------------------------------------------------------------

INDUSTRY_SECTOR_MAP: dict[str, str] = {
    "01": "materials",
    "02": "consumer",
    "03": "materials",
    "04": "consumer",
    "05": "industrials",
    "06": "industrials",
    "08": "materials",
    "10": "materials",
    "11": "consumer",
    "12": "materials",
    "14": "real_estate",
    "15": "transport",
    "17": "financial",
    "18": "consumer",
    "20": "consumer",
    "21": "industrials",
    "22": "healthcare",
    "23": "energy",
    "24": "semi",
    "25": "electronics",
    "26": "electronics",
    "27": "electronics",
    "28": "electronics",
    "29": "tech_svc",
    "31": "electronics",
    "35": "healthcare",
    "36": "tech_svc",
    "37": "consumer",
    "38": "industrials",
    "91": "foreign",
}


# ---------------------------------------------------------------------------
# DB-backed industry_code cache
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _load_industry_code_map() -> dict[str, str]:
    """Load stock_id → industry_code from company_metadata.

    Cached for the lifetime of the process.  Call _load_industry_code_map.cache_clear()
    in tests or after schema changes.
    """
    from data.database import connect  # local import to avoid circular deps

    with connect(read_only=True) as con:
        rows = con.execute(
            "SELECT stock_id, industry_code FROM company_metadata "
            "WHERE industry_code IS NOT NULL"
        ).fetchall()

    return {stock_id: industry_code for stock_id, industry_code in rows}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sector(stock_id: str) -> str:
    """Return sector label for stock_id.

    Resolution order:
      1. ETF heuristic (stock_id starts with '0') → 'etf'
      2. company_metadata.industry_code → INDUSTRY_SECTOR_MAP lookup
      3. Fallback → 'unknown'

    Args:
        stock_id: TWSE/TPEx stock identifier string.

    Returns:
        Sector label string, never None.
    """
    if is_etf(stock_id):
        return "etf"

    code_map = _load_industry_code_map()
    industry_code = code_map.get(stock_id)
    if industry_code is None:
        return "unknown"

    return INDUSTRY_SECTOR_MAP.get(industry_code, "unknown")


def is_etf(stock_id: str) -> bool:
    """Return True if stock_id is an ETF.

    Heuristic: stock_id starts with '0'.  Valid for the full Helios universe.

    Args:
        stock_id: TWSE/TPEx stock identifier string.

    Returns:
        True if the stock is classified as an ETF.
    """
    return stock_id.startswith("0")


def all_sectors() -> set[str]:
    """Return all sector labels defined in INDUSTRY_SECTOR_MAP plus 'etf' and 'unknown'."""
    return set(INDUSTRY_SECTOR_MAP.values()) | {"etf", "unknown"}
