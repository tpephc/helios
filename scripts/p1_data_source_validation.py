#!/usr/bin/env python3
# scripts/p1_data_source_validation.py
"""P1-DATA Phase 0 Source Validation — v0.2.0.

Fetches TWSE/TPEx official listing dates for the 18 known pre-listing
contamination symbols and compares against company_metadata.listing_date
and daily_price_adj.first_price_date.

Output: data/_storage/p1_data_source_validation.csv + printed verdict table.
Run: uv run python scripts/p1_data_source_validation.py
"""

import time
from io import StringIO
from pathlib import Path

import duckdb
import pandas as pd
import requests

DB_PATH = Path("data/_storage/helios.duckdb")
OUT_PATH = Path("data/_storage/p1_data_source_validation.csv")

AFFECTED_STOCK_IDS = [
    "2645", "2646", "4583", "6446", "6472", "6526",
    "6691", "6770", "6789", "6805", "6831", "6919",
    "6944", "7610", "7750", "7769", "7799", "7822",
]

ISIN_URL = "https://isin.twse.com.tw/isin/C_public.jsp"
HEADERS = {"User-Agent": "Mozilla/5.0 (research audit script; read-only)"}

# strMode: 2=TWSE listed, 4=TPEx listed, 5=Emerging board
ISIN_MODES = {
    "TWSE_listed": 2,
    "TPEx_listed": 4,
    "emerging": 5,
}


def fetch_db_dates(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return first_price_date and listing_date for affected stock_ids."""
    ids_sql = ", ".join(f"'{s}'" for s in AFFECTED_STOCK_IDS)
    fp = con.execute(f"""
        SELECT stock_id,
               MIN(date) AS first_price_date
        FROM   daily_price_adj
        WHERE  stock_id IN ({ids_sql})
        GROUP  BY stock_id
    """).df()
    meta = con.execute(f"""
        SELECT stock_id,
               listing_date
        FROM   company_metadata
        WHERE  stock_id IN ({ids_sql})
    """).df()
    return fp.merge(meta, on="stock_id", how="outer")


def fetch_isin_table(mode: int, label: str) -> pd.DataFrame:
    """Fetch and parse ISIN table from TWSE portal for a given strMode."""
    resp = requests.get(
        ISIN_URL,
        params={"strMode": str(mode)},
        headers=HEADERS,
        timeout=30,
    )
    html_text = resp.content.decode("cp950")
    try:
        tables = pd.read_html(StringIO(html_text), header=0)
    except ValueError:
        print(f"  [{label}] WARNING: no tables found")
        return pd.DataFrame()

    if not tables:
        return pd.DataFrame()

    df = tables[0].copy()
    # Row 0 is a duplicate header row — drop it
    if df.iloc[0].astype(str).str.contains("股票|代號|有價").any():
        df = df.iloc[1:].reset_index(drop=True)

    print(f"  [{label}] shape={df.shape}, columns={df.columns.tolist()}")
    return df


def extract_stock_id_and_date(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Extract stock_id and listing date from parsed ISIN table."""
    if df.empty:
        return pd.DataFrame(columns=["stock_id", "listing_date_src", "source"])

    cols = df.columns.tolist()
    name_col = cols[0]  # "有價證券代號及名稱"
    date_col = next(
        (c for c in cols if "上市" in str(c) or "掛牌" in str(c) or "上櫃" in str(c)),
        None,
    )
    if date_col is None:
        print(f"  [{label}] WARNING: no listing date column found")
        return pd.DataFrame(columns=["stock_id", "listing_date_src", "source"])

    out = pd.DataFrame()
    # stock_id: leading 4-6 digits before whitespace
    out["stock_id"] = (
        df[name_col].astype(str).str.extract(r"^(\d{4,6})\s")[0]
    )
    out["listing_date_src"] = pd.to_datetime(
        df[date_col].astype(str), format="%Y/%m/%d", errors="coerce"
    )
    out["source"] = label
    return out.dropna(subset=["stock_id", "listing_date_src"])


def classify(row: pd.Series) -> str:
    """Classify source reliability for one stock_id row."""
    fpd = row.get("first_price_date")
    lmd = row.get("listing_date")
    tld = row.get("listing_date_src")

    if pd.isna(tld):
        return "NOT_FOUND"
    if pd.isna(fpd):
        return "NO_PRICE_DATA"

    tld = pd.Timestamp(tld)
    fpd = pd.Timestamp(fpd)
    lmd = pd.Timestamp(lmd) if not pd.isna(lmd) else None

    if lmd is not None and tld.date() == lmd.date():
        return "SAME_AS_META_SUSPECT"
    if tld <= fpd:
        return "EARLIER_OR_EQUAL_PROMISING"
    return "LATER_THAN_PRICE_UNUSABLE"


def main() -> None:
    """Run Phase 0 source validation and emit verdict table."""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("=== P1-DATA Phase 0 Source Validation v0.2.0 ===\n")

    # 1. DB dates
    print("[1/4] Fetching DB dates...")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    db_df = fetch_db_dates(con)
    con.close()
    print(db_df.to_string(index=False))
    print()

    # 2-4. Fetch all three ISIN modes
    all_src_parts = []
    for label, mode in ISIN_MODES.items():
        print(f"[fetching {label} strMode={mode}]...")
        time.sleep(1)
        raw = fetch_isin_table(mode, label)
        parsed = extract_stock_id_and_date(raw, label)
        print(f"  [{label}] parsed {len(parsed)} rows with valid stock_id+date")
        all_src_parts.append(parsed)

    all_src = pd.concat(all_src_parts, ignore_index=True)

    # Per stock_id: keep earliest listing_date_src across all sources
    best_src = (
        all_src[all_src["stock_id"].isin(AFFECTED_STOCK_IDS)]
        .sort_values("listing_date_src")
        .groupby("stock_id", as_index=False)
        .first()
    )

    # Merge with DB dates
    merged = db_df.merge(
        best_src[["stock_id", "listing_date_src", "source"]],
        on="stock_id",
        how="left",
    )
    merged["verdict"] = merged.apply(classify, axis=1)

    # Verdict table
    print("\n=== VERDICT TABLE ===")
    cols = ["stock_id", "first_price_date", "listing_date",
            "listing_date_src", "source", "verdict"]
    print(merged[cols].to_string(index=False))

    # Summary
    print("\n=== SUMMARY ===")
    print(merged["verdict"].value_counts().to_string())

    promising  = (merged["verdict"] == "EARLIER_OR_EQUAL_PROMISING").sum()
    suspect    = (merged["verdict"] == "SAME_AS_META_SUSPECT").sum()
    not_found  = (merged["verdict"] == "NOT_FOUND").sum()
    unusable   = (merged["verdict"] == "LATER_THAN_PRICE_UNUSABLE").sum()
    total      = len(merged)

    print(f"\nEARLIER_OR_EQUAL_PROMISING : {promising}/{total}")
    print(f"SAME_AS_META_SUSPECT       : {suspect}/{total}")
    print(f"LATER_THAN_PRICE_UNUSABLE  : {unusable}/{total}")
    print(f"NOT_FOUND                  : {not_found}/{total}")

    if promising == total:
        verdict, note = "PASS", "TWSE/TPEx source resolves IF-1 for all 18 symbols. Proceed to SPEC Phase 1."
    elif promising >= int(total * 0.8):
        verdict, note = "PARTIAL_PASS", "TWSE/TPEx resolves majority. Manual review required for remaining symbols."
    elif promising > 0:
        verdict, note = "PARTIAL_FAIL", "TWSE/TPEx resolves minority only. Escalate to FinMind evaluation."
    else:
        verdict, note = "FAIL", "TWSE/TPEx source does not resolve IF-1. Escalate to FinMind or TEJ."

    print(f"\nPHASE 0 VERDICT: {verdict}")
    print(f"Note: {note}")

    merged.to_csv(OUT_PATH, index=False)
    print(f"\nOutput saved: {OUT_PATH}")


if __name__ == "__main__":
    main()
