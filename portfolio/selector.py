# portfolio/selector.py
"""Sector classification + selection helpers.

Sector map is hardcoded for Helios v0.1 universe (15 symbols).
未來 (v0.2+) 應該從 company_metadata.industry_code 動態 build,
但 v0.1.14 hardcoded 更透明且 unit-testable.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# Sector classification (Helios v0.1 universe)
# ─────────────────────────────────────────────────────────────

SECTOR_MAP: dict[str, str] = {
    # ETFs (共 5 檔)
    "0050": "etf", "0056": "etf", "006208": "etf", "00878": "etf", "00919": "etf",

    # 半導體 (pure semi, 共 3 檔)
    "2303": "semi", "2330": "semi", "2454": "semi",

    # 電子相關 (台達電 / 鴻海 / 日月光投控, 共 3 檔)
    # 台達電是電源/電子零組件, 鴻海是 EMS, 日月光是 IC 封測
    # 都跟半導體景氣高度相關 — 但分一個 group 避免跟 semi 重疊計算
    "2308": "electronics", "2317": "electronics", "3711": "electronics",

    # 金融保險 (共 3 檔)
    "2881": "financial", "2882": "financial", "2891": "financial",

    # 電信 (共 1 檔)
    "2412": "telecom",
}


def get_sector(stock_id: str) -> str:
    """Return sector for given stock_id; 'unknown' if not in v0.1 universe."""
    return SECTOR_MAP.get(stock_id, "unknown")


def is_etf(stock_id: str) -> bool:
    """ETF heuristic: 4-6 碼以 0 開頭 (Helios v0.1 universe 100% 適用)."""
    return stock_id.startswith("0")


def all_sectors() -> set[str]:
    """All sectors present in v0.1 universe."""
    return set(SECTOR_MAP.values())
