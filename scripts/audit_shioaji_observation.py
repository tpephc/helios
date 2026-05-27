#!/usr/bin/env python3
# scripts/audit_shioaji_observation.py
"""Post-cron audit: extract P-obs-1 observation events from logs — v0.1.0.

Reads Helios log files, extracts shioaji_raw_*_observation events, runs
consistency checks, and outputs an evidence summary suitable for direct
append to shioaji_semantic_observation_2026_05_26.md §3.

Usage:
    uv run python scripts/audit_shioaji_observation.py
    uv run python scripts/audit_shioaji_observation.py --log-dir logs
    uv run python scripts/audit_shioaji_observation.py --log-file logs/daily_run_cron.log
    uv run python scripts/audit_shioaji_observation.py --json  # machine-readable output

Design decisions:
  - Grep-first: filters lines containing 'shioaji_raw_' before attempting
    JSON parse. Works with both structlog JSONRenderer and ConsoleRenderer.
  - Fault-tolerant: non-JSON lines are reported but don't crash the script.
  - No dependencies beyond stdlib — runs on any Helios-configured Python.
  - Output is Markdown-formatted for direct paste into SSOT §3 entries.

Lifecycle: tied to P-obs-1 observation window. Remove when P-obs-1
instrumentation is removed from live_broker.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Constants ─────────────────────────────────────────────────────────────

EVENT_PREFIX = "shioaji_raw_"

KNOWN_EVENTS = {
    "shioaji_raw_submit_observation",
    "shioaji_raw_fetch_trades_observation",
    "shioaji_raw_fetch_holdings_observation",
}

# Fields that must exist in each event for a valid observation
REQUIRED_FIELDS: dict[str, list[str]] = {
    "shioaji_raw_submit_observation": [
        "order_id",
        "trade_type",
        "status_type",
        "status_deals_count",
        "trade_deals_count",
        "deals_paths_agree",
    ],
    "shioaji_raw_fetch_trades_observation": [
        "trades_count",
        "trades_sample",
    ],
    "shioaji_raw_fetch_holdings_observation": [
        "positions_count",
        "positions_raw",
    ],
}


# ── Log parsing ───────────────────────────────────────────────────────────


def find_log_files(log_dir: Path) -> list[Path]:
    """Find all plausible log files in the directory.

    Checks both daily_run_cron.log and helios.log (structlog may write
    to either depending on handler configuration).
    """
    candidates = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Also check rotated logs like helios.log.1, daily_run_cron.log.1
    candidates.extend(sorted(log_dir.glob("*.log.*"), key=lambda p: p.stat().st_mtime, reverse=True))
    return candidates


def extract_observation_lines(filepath: Path) -> list[tuple[int, str]]:
    """Extract lines containing observation events from a log file.

    Returns (line_number, raw_line) tuples.
    """
    results: list[tuple[int, str]] = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, start=1):
                if EVENT_PREFIX in line:
                    results.append((lineno, line.rstrip()))
    except OSError as exc:
        print(f"  ⚠ Cannot read {filepath}: {exc}", file=sys.stderr)
    return results


def try_parse_json(raw_line: str) -> dict[str, Any] | None:
    """Attempt to parse a log line as JSON.

    structlog JSONRenderer outputs one JSON object per line.
    ConsoleRenderer outputs key=value pairs — not JSON-parseable, but we
    still extract what we can.

    Returns parsed dict or None.
    """
    # Try direct JSON parse first (JSONRenderer)
    try:
        return json.loads(raw_line)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to find JSON embedded in a larger line (e.g. after timestamp prefix)
    # Common pattern: "2026-05-26 16:00:05 {...}"
    brace_start = raw_line.find("{")
    if brace_start >= 0:
        try:
            return json.loads(raw_line[brace_start:])
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ── Consistency checks ────────────────────────────────────────────────────


def check_event(event_name: str, data: dict[str, Any]) -> list[str]:
    """Run consistency checks on a parsed observation event.

    Returns list of issues (empty = all good).
    """
    issues: list[str] = []

    # Check required fields
    required = REQUIRED_FIELDS.get(event_name, [])
    for field in required:
        if field not in data:
            issues.append(f"MISSING FIELD: {field}")

    # Event-specific checks
    if event_name == "shioaji_raw_submit_observation":
        # deals_paths_agree should be True (status.deals == trade.deals)
        if "deals_paths_agree" in data and not data["deals_paths_agree"]:
            issues.append(
                "DIVERGENCE: deals_paths_agree=False — "
                "trade.status.deals and trade.deals differ in count. "
                "HIGH-VALUE EVIDENCE — capture full payload for SSOT §4."
            )

        # Check deal-level dual-logging presence
        deals_raw = data.get("status_deals_raw", [])
        for i, deal in enumerate(deals_raw):
            if not isinstance(deal, dict):
                issues.append(f"status_deals_raw[{i}]: not a dict")
                continue
            # Verify dual-log fields exist
            for field_prefix in ("price", "quantity", "ts"):
                raw_key = f"{field_prefix}_raw"
                type_key = f"{field_prefix}_type"
                if raw_key not in deal:
                    issues.append(f"deal[{i}]: MISSING {raw_key}")
                if type_key not in deal:
                    issues.append(f"deal[{i}]: MISSING {type_key}")

            # quantity_type should be int or float (not Decimal, not SDK wrapper)
            qty_type = deal.get("quantity_type", "")
            if qty_type and qty_type not in ("int", "float", "int64", "int32"):
                issues.append(
                    f"deal[{i}]: quantity_type={qty_type!r} — "
                    f"unexpected type, verify boundary normalization"
                )

    elif event_name == "shioaji_raw_fetch_trades_observation":
        sample = data.get("trades_sample", [])
        for i, trade in enumerate(sample):
            if not isinstance(trade, dict):
                continue
            qty_types = trade.get("deal_qty_types", [])
            for j, qt in enumerate(qty_types):
                if qt and qt not in ("int", "float", "int64", "int32"):
                    issues.append(
                        f"trade[{i}].deal_qty_types[{j}]={qt!r} — "
                        f"unexpected type"
                    )

    elif event_name == "shioaji_raw_fetch_holdings_observation":
        positions = data.get("positions_raw", [])
        for i, pos in enumerate(positions):
            if not isinstance(pos, dict):
                continue
            qty_type = pos.get("quantity_type", "")
            if qty_type and qty_type not in ("int", "float", "int64", "int32"):
                issues.append(
                    f"position[{i}]: quantity_type={qty_type!r} — "
                    f"unexpected type"
                )

    return issues


# ── Output formatting ─────────────────────────────────────────────────────


def format_markdown_entry(
    event_name: str,
    data: dict[str, Any],
    source_file: str,
    line_number: int,
    issues: list[str],
) -> str:
    """Format a single observation event as a Markdown entry for SSOT §3."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M %Z")
    status = "PASS" if not issues else "ISSUES FOUND"

    lines = [
        f"### Observation: {event_name}",
        f"**Date:**           {now}",
        f"**Env:**            (check broker_tag in surrounding log context)",
        f"**Tag:**            [OBSERVED]",
        f"**Source:**          {source_file}:{line_number}",
        f"**Invariant check:** {status}",
    ]

    if event_name == "shioaji_raw_submit_observation":
        lines.extend([
            f"**Order ref:**      order_id={data.get('order_id', 'N/A')} "
            f"/ broker_order_id={data.get('broker_order_id', 'N/A')}",
            f"**trade_type:**     {data.get('trade_type', 'N/A')}",
            f"**status_type:**    {data.get('status_type', 'N/A')}",
            f"**status_status_type:** {data.get('status_status_type', 'N/A')}",
            f"**deals_paths_agree:** {data.get('deals_paths_agree', 'N/A')}",
            f"**status_deals_count:** {data.get('status_deals_count', 'N/A')}",
            f"**trade_deals_count:** {data.get('trade_deals_count', 'N/A')}",
        ])
        deals_raw = data.get("status_deals_raw", [])
        if deals_raw:
            lines.append("**Deal-level observations:**")
            for i, deal in enumerate(deals_raw):
                if not isinstance(deal, dict):
                    continue
                lines.append(
                    f"  - deal[{i}]: "
                    f"price_raw={deal.get('price_raw')} "
                    f"({deal.get('price_type', '?')}), "
                    f"quantity_raw={deal.get('quantity_raw')} "
                    f"({deal.get('quantity_type', '?')}), "
                    f"ts_type={deal.get('ts_type', '?')}"
                )

    elif event_name == "shioaji_raw_fetch_trades_observation":
        lines.extend([
            f"**as_of:**          {data.get('as_of', 'N/A')}",
            f"**trades_count:**   {data.get('trades_count', 'N/A')}",
            f"**truncated:**      {data.get('trades_truncated', 'N/A')}",
        ])
        sample = data.get("trades_sample", [])
        if sample:
            lines.append("**Sample trade shapes:**")
            for i, t in enumerate(sample):
                if not isinstance(t, dict):
                    continue
                lines.append(
                    f"  - trade[{i}]: "
                    f"order_id={t.get('order_id')}, "
                    f"deals={t.get('status_deals_count', '?')}, "
                    f"qty_types={t.get('deal_qty_types', [])}"
                )

    elif event_name == "shioaji_raw_fetch_holdings_observation":
        lines.extend([
            f"**positions_count:** {data.get('positions_count', 'N/A')}",
            f"**truncated:**       {data.get('positions_truncated', 'N/A')}",
        ])
        positions = data.get("positions_raw", [])
        if positions:
            lines.append("**Position-level observations:**")
            for i, p in enumerate(positions):
                if not isinstance(p, dict):
                    continue
                lines.append(
                    f"  - pos[{i}]: "
                    f"code={p.get('code')}, "
                    f"quantity_raw={p.get('quantity_raw')} "
                    f"({p.get('quantity_type', '?')}), "
                    f"price_raw={p.get('price_raw')} "
                    f"({p.get('price_type', '?')})"
                )

    if issues:
        lines.append("**Issues:**")
        for issue in issues:
            lines.append(f"  - ⚠ {issue}")

    lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P-obs-1 post-cron audit: extract and validate "
        "shioaji_raw_* observation events from Helios logs.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory containing log files (default: logs/)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Specific log file to audit (overrides --log-dir)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output machine-readable JSON instead of Markdown",
    )
    args = parser.parse_args()

    # Determine which files to scan
    if args.log_file:
        if not args.log_file.exists():
            print(f"ERROR: {args.log_file} does not exist", file=sys.stderr)
            return 1
        files_to_scan = [args.log_file]
    else:
        if not args.log_dir.exists():
            print(f"ERROR: {args.log_dir}/ does not exist", file=sys.stderr)
            return 1
        files_to_scan = find_log_files(args.log_dir)
        if not files_to_scan:
            print(f"WARNING: no .log files found in {args.log_dir}/", file=sys.stderr)
            return 1

    # Scan all files
    all_observations: list[dict[str, Any]] = []
    parse_failures: list[tuple[str, int, str]] = []

    print(f"Scanning {len(files_to_scan)} log file(s)...", file=sys.stderr)

    for filepath in files_to_scan:
        raw_lines = extract_observation_lines(filepath)
        if not raw_lines:
            continue
        print(f"  {filepath.name}: {len(raw_lines)} observation line(s)", file=sys.stderr)

        for lineno, raw_line in raw_lines:
            parsed = try_parse_json(raw_line)
            if parsed is None:
                parse_failures.append((str(filepath), lineno, raw_line[:200]))
                continue

            # Determine event name — structlog uses 'event' key
            event_name = parsed.get("event", "")
            if event_name not in KNOWN_EVENTS:
                # Might be ConsoleRenderer format — try to extract from line
                for known in KNOWN_EVENTS:
                    if known in raw_line:
                        event_name = known
                        break
                else:
                    parse_failures.append((str(filepath), lineno, f"unknown event: {raw_line[:200]}"))
                    continue

            issues = check_event(event_name, parsed)
            all_observations.append({
                "event": event_name,
                "data": parsed,
                "source": str(filepath),
                "line": lineno,
                "issues": issues,
            })

    # ── Summary ───────────────────────────────────────────────────────────

    if not all_observations and not parse_failures:
        print("\n" + "=" * 60, file=sys.stderr)
        print("NO OBSERVATION EVENTS FOUND", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(
            "\nPossible causes:\n"
            "  1. Cron has not run yet\n"
            "  2. Logger level filters out info (check structlog config)\n"
            "  3. P-obs-1 patch not deployed\n"
            "  4. Wrong --log-dir / --log-file path\n",
            file=sys.stderr,
        )
        return 2

    # JSON output mode
    if args.json_output:
        output = {
            "scan_time": datetime.now().isoformat(),
            "files_scanned": len(files_to_scan),
            "observations": all_observations,
            "parse_failures": [
                {"file": f, "line": l, "preview": p}
                for f, l, p in parse_failures
            ],
        }
        print(json.dumps(output, indent=2, default=str))
        return 0

    # Markdown output mode
    print("\n" + "=" * 60)
    print("P-obs-1 OBSERVATION AUDIT")
    print(f"Scan time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Files scanned: {len(files_to_scan)}")
    print(f"Observations found: {len(all_observations)}")
    print(f"Parse failures: {len(parse_failures)}")
    print("=" * 60)

    # Group by event type
    by_event: dict[str, list[dict]] = {}
    for obs in all_observations:
        by_event.setdefault(obs["event"], []).append(obs)

    # Coverage check — which events did we see?
    print("\n## Coverage")
    for event in sorted(KNOWN_EVENTS):
        count = len(by_event.get(event, []))
        status = "✅" if count > 0 else "❌ NOT OBSERVED"
        print(f"  {status} {event}: {count} occurrence(s)")

    # Issues summary
    all_issues = [
        (obs["event"], obs["source"], obs["line"], issue)
        for obs in all_observations
        for issue in obs["issues"]
    ]
    if all_issues:
        print(f"\n## Issues ({len(all_issues)} total)")
        for event, source, line, issue in all_issues:
            print(f"  ⚠ {event} ({Path(source).name}:{line}): {issue}")
    else:
        print("\n## Issues: NONE ✅")

    # Parse failures
    if parse_failures:
        print(f"\n## Parse failures ({len(parse_failures)})")
        for source, line, preview in parse_failures:
            print(f"  ⚠ {Path(source).name}:{line}: {preview}")

    # Detailed Markdown entries (for SSOT §3 append)
    print("\n" + "=" * 60)
    print("SSOT §3 ENTRIES (copy-paste below into observation doc)")
    print("=" * 60 + "\n")

    for obs in all_observations:
        md = format_markdown_entry(
            event_name=obs["event"],
            data=obs["data"],
            source_file=obs["source"],
            line_number=obs["line"],
            issues=obs["issues"],
        )
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
