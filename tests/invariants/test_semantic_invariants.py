# tests/invariants/test_semantic_invariants.py
"""Semantic invariant tests — v0.1.14.3.1 onward.

These tests don't verify "is feature X correct?". They verify "is the system's
internal world view consistent?". A regression in this file means two layers
have drifted in their semantics — even if each layer individually still passes
its own unit tests.

Why a separate file (and directory): the maintenance cost of an invariant is
different from the maintenance cost of a feature test. When a feature changes,
its unit test changes with it. When a system semantic changes, it changes
*deliberately* — and the invariant test should be the explicit gate that
forces that change to be intentional. Mixing the two in one file makes it too
easy to "fix" an invariant test by mirroring whatever the implementation now
does, which silently approves the semantic drift.

Convention: each invariant test states the contract in its docstring as a
single-sentence assertion, in addition to the in-code assert message.
"""
from __future__ import annotations

from datetime import date

from tests.conftest import seed_price

# ─────────────────────────────────────────────────────────────
# Execution / approval price-source consistency
# ─────────────────────────────────────────────────────────────


def test_fill_and_drift_gate_share_same_price_source(tmp_db, seed_calendar):
    """Invariant: the column the drift gate compares against MUST be the same
    column the broker fills at. If they diverge, an approval can pass on one
    price reference and execute at another — the trade gets done at a price
    the drift gate would have rejected, or rejected when it should have passed.

    Constructed scenario (signal price 140.0, entry_atr 2.0, threshold 1.0):
      - adj_open  = 140.5  → drift 0.5 → PASS under adj_open semantic
      - adj_close = 142.0  → drift 2.0 → FAIL under adj_close semantic

    Both layers must consult adj_open: approval passes (drift 0.5), broker
    fills at 140.5. If drift gate read adj_close (the pre-v0.1.14.3 bug),
    approval would have failed at drift 2.0 — no fill, no position.

    Concretely: after a successful approval, the resulting position's
    entry_price must be derivable from adj_open=140.5 (plus default slippage),
    not from adj_close=142.0. The assertion pins the two layers together so a
    future change to either alone breaks this test before it ships.
    """
    from execution.approvals import approve_signal
    from execution.paper_broker import PaperBroker
    from storage.positions import get_open_positions
    from storage.signals import save_signal

    fill_date = seed_calendar[1]
    # adj_open ≠ adj_close — the gap is the test signal.
    seed_price("0050", fill_date, close=142.0, open_price=140.5, atr_14=2.0)

    sid = save_signal(
        symbol="0050", strategy="trend_breakout_v1", signal_type="buy",
        score=0.9, price=140.0, reason=["invariant"],
        signal_date=seed_calendar[0],
        entry_atr=2.0, regime="bull",
    )

    broker = PaperBroker()
    ok, msg, _ = approve_signal(
        sid, target_notional=50_000, fill_date=fill_date,
        broker=broker, approved_by="invariant-test",
    )
    assert ok, (
        f"INVARIANT VIOLATED: approval should pass when drift gate consults "
        f"adj_open=140.5 (drift 0.5 < threshold 1.0). If approval fails, the "
        f"drift gate is reading a different column than the broker. msg={msg}"
    )

    pos = get_open_positions(symbol="0050")[0]
    # Fill price = adj_open × (1 + slippage). Default slippage 0.001.
    expected_fill_from_adj_open = 140.5 * 1.001            # ≈ 140.6405
    forbidden_fill_from_adj_close = 142.0 * 1.001          # ≈ 142.142
    assert abs(pos.entry_price - expected_fill_from_adj_open) < 0.01, (
        f"INVARIANT VIOLATED: broker fill entry_price={pos.entry_price:.4f}; "
        f"expected ≈{expected_fill_from_adj_open:.4f} (derived from adj_open=140.5). "
        f"If close to {forbidden_fill_from_adj_close:.4f}, broker is reading "
        f"adj_close — the drift gate and the broker have drifted apart."
    )


# ─────────────────────────────────────────────────────────────
# Operational metadata invariants
# ─────────────────────────────────────────────────────────────


def test_fill_result_carries_execution_reason_on_success(tmp_db):
    """Invariant: every successful FillResult sets execution_reason='filled'.

    The string-only `error` field is None on success — that's necessary but
    not sufficient for machine-readable analytics. `execution_reason` MUST
    be a positive identifier of what happened, not the absence of failure.
    """
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    seed_price("0050", fill_date, close=100.0, open_price=100.0, volume=1_000_000)
    result = PaperBroker().submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert result.success
    assert result.execution_reason == "filled", (
        f"successful fills must set execution_reason='filled', got "
        f"{result.execution_reason!r}"
    )


def test_fill_result_carries_execution_reason_on_failure(tmp_db):
    """Invariant: failed FillResult's execution_reason matches its error code.

    Operationally, this means run_summary can group rejections by
    execution_reason without parsing free-text error strings.
    """
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    # Tiny volume → liquidity breach
    seed_price("0050", fill_date, close=1.0, open_price=1.0, volume=10_000)
    result = PaperBroker().submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert not result.success
    assert result.execution_reason == "insufficient_liquidity"
    assert result.execution_reason == result.error, (
        f"execution_reason and error must agree on failure code "
        f"(reason={result.execution_reason!r}, error={result.error!r})"
    )


def test_fill_result_carries_participation_rate_on_liquidity_breach(tmp_db):
    """Invariant: when liquidity is the rejection cause, participation_rate
    MUST be populated so run_summary can aggregate breach distributions.

    Operationally: an operator hitting "5-day median rejected participation"
    in run_summary depends on this field being there for EVERY liquidity-
    rejected fill, not just sometimes.
    """
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    seed_price("0050", fill_date, close=1.0, open_price=1.0, volume=10_000)
    result = PaperBroker().submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert result.execution_reason == "insufficient_liquidity"
    assert result.participation_rate is not None, (
        "participation_rate must be populated on liquidity rejection so "
        "run_summary can build the breach distribution"
    )
    # Sanity: rate should be well above the 0.5% threshold
    assert result.participation_rate > 0.005


def test_fill_result_carries_participation_rate_on_success(tmp_db):
    """Invariant: successful fills also report participation_rate, so
    "how close was this to breaching" can be analyzed across all fills,
    not just rejected ones."""
    from execution.paper_broker import PaperBroker

    fill_date = date(2026, 5, 4)
    seed_price("0050", fill_date, close=100.0, open_price=100.0, volume=1_000_000)
    result = PaperBroker().submit_buy(
        symbol="0050", target_notional=50_000, fill_date=fill_date,
    )
    assert result.success
    assert result.participation_rate is not None
    # ≈ 500 shares / 1M = 0.05%
    assert abs(result.participation_rate - result.shares / 1_000_000) < 1e-9


# ─────────────────────────────────────────────────────────────
# Run-ledger invariants
# ─────────────────────────────────────────────────────────────


def test_run_id_persists_across_marker_and_history(tmp_db, isolated_marker):
    """Invariant: the run_id written into the marker file MUST equal the
    run_id appended to the history log for the same run.

    A mismatch means cross-log correlation (crash investigation, retry chain
    analysis) is broken — the same run would appear as two different ledger
    entries from different vantage points.
    """
    from execution.shutdown import read_history, read_marker, shutdown_guard

    with shutdown_guard(date(2026, 5, 4)) as g:
        g.set_summary({"exits": 0})
    marker = read_marker()
    history = read_history(n=5)
    assert marker is not None
    assert len(history) == 1
    assert "run_id" in marker, "marker payload must carry run_id"
    assert "run_id" in history[0], "history entry must carry run_id"
    assert marker["run_id"] == history[0]["run_id"], (
        f"INVARIANT VIOLATED: marker run_id={marker['run_id']!r} ≠ "
        f"history run_id={history[0]['run_id']!r}. The two ledgers have "
        f"drifted — same run, different identities."
    )


def test_run_id_unique_per_run(tmp_db, isolated_marker):
    """Invariant: two consecutive runs MUST get distinct run_ids. Otherwise
    "did we re-run this as_of?" cannot be distinguished from "this is the
    same run we already saw"."""
    from execution.shutdown import read_history, shutdown_guard

    with shutdown_guard(date(2026, 5, 4)) as g:
        g.set_summary({"exits": 0})
    with shutdown_guard(date(2026, 5, 5)) as g:
        g.set_summary({"exits": 0})

    history = read_history(n=5)
    assert len(history) == 2
    assert history[0]["run_id"] != history[1]["run_id"], (
        f"INVARIANT VIOLATED: two distinct runs share run_id "
        f"{history[0]['run_id']!r}. Run identity is not unique."
    )


# ─────────────────────────────────────────────────────────────
# Producer-consumer plumbing invariants (v0.1.14.3.2)
# ─────────────────────────────────────────────────────────────


def test_scan_and_exit_aggregates_reach_marker_payload(
    tmp_db, seed_calendar, isolated_marker, monkeypatch,
):
    """Invariant: every observability field that `scan_and_exit` produces in
    its summary MUST reach the marker payload's `summary` dict via daily_run's
    forwarding step.

    Background — v0.1.14.3.1 nexus smoke test discovered marker missing
    `avg_position_days` / `max_position_days` even though scan_and_exit
    computed them correctly. Root cause: `daily_run.main` forwards a hardcoded
    tuple of keys from exit_summary into `guard.set_summary`; the tuple was
    not updated when the aggregates were added in the same patch.

    Why this is a distinct invariant class:
      - Unit tests on scan_and_exit pass (producer side correct)
      - daily_run runs to "ok" (no exception, no log alarm)
      - The field is silently dropped between producer and persistence
    Operationally indistinguishable from "field never existed", so without
    this contract the only signal is an operator squinting at marker JSON.

    Strategy: monkeypatch `scan_and_exit` to return a sentinel summary with
    distinguishable values for every observability field, drive `daily_run.main`
    end-to-end via argv, then assert each sentinel value reaches the marker.
    Future additions to scan_and_exit's observability surface must extend
    `required` here too — that is the contract.
    """
    import json
    import sys

    import scripts.process_entries as _pe
    from execution.shutdown import MARKER_PATH
    from scripts import daily_run as _dr

    as_of_str = str(seed_calendar[3])

    # Sentinel summary — distinguishable values for every observability field
    # we expect to land in the marker.
    sentinel = {
        "as_of": as_of_str,
        "fill_date": str(seed_calendar[4]),
        "open_positions_scanned": 1,
        "updated_stats": 0,
        "exits_fired": 0,
        "exits_failed": 17,
        "skipped_no_data": 3,
        "exits": [],
        "open_position_days": [
            {"position_id": "pos_sentinel", "symbol": "0050", "age_days": 42},
        ],
        "exits_failed_symbols": ["2330", "0050"],
        "skipped_no_data_symbols": ["1234"],
        "avg_position_days": 42.0,
        "max_position_days": 42,
    }

    # Stub scan_and_exit (the producer) and generate_pending_signals (the
    # entry pipeline — irrelevant for this contract, just needs to not
    # crash). Keep all other daily_run preflight steps real so the path
    # being exercised matches production.
    monkeypatch.setattr(_dr, "scan_and_exit", lambda **_kw: sentinel)
    monkeypatch.setattr(_pe, "generate_pending_signals", lambda **_kw: ([], {}))

    monkeypatch.setattr(sys, "argv", [
        "daily_run.py", "--as-of", as_of_str, "--no-listener",
    ])

    exit_code = _dr.main()
    assert exit_code == 0, f"daily_run did not exit cleanly (code={exit_code})"

    marker = json.loads(MARKER_PATH.read_text())
    assert marker["status"] == "ok"
    summary = marker["summary"]

    # The CONTRACT: each of these keys, with sentinel values, must reach
    # marker.summary. Add new observability fields here when scan_and_exit
    # grows them.
    required = {
        "exits_failed": 17,
        "exits_failed_symbols": ["2330", "0050"],
        "skipped_no_data": 3,
        "skipped_no_data_symbols": ["1234"],
        "open_position_days": [
            {"position_id": "pos_sentinel", "symbol": "0050", "age_days": 42},
        ],
        "avg_position_days": 42.0,
        "max_position_days": 42,
    }
    missing = [k for k in required if k not in summary]
    assert not missing, (
        f"INVARIANT VIOLATED: marker.summary is missing keys {missing!r} that "
        f"scan_and_exit produced. Producer→marker plumbing broken (likely "
        f"`daily_run.main`'s set_summary forwarding tuple is out of date). "
        f"Marker summary keys present: {sorted(summary.keys())}"
    )
    for key, expected in required.items():
        assert summary[key] == expected, (
            f"plumbing carried key {key!r} but corrupted its value: "
            f"expected {expected!r}, got {summary[key]!r}"
        )


# ─────────────────────────────────────────────────────────────
# Configuration / secrets invariants (v0.1.14.3.4)
# ─────────────────────────────────────────────────────────────


def test_telegram_config_loads_from_canonical_dotenv_keys(tmp_path, monkeypatch):
    """Invariant: TelegramConfig.from_env must consume `TELEGRAM_BOT_TOKEN`
    and `TELEGRAM_CHAT_ID` (no prefix) — matching .env.example contract.

    v0.1.14.3.4 trigger: pre-v0.1.14.3.4 the code read `HELIOS_TELEGRAM_*`
    via raw `os.environ.get`. Operators following .env.example correctly
    set `TELEGRAM_BOT_TOKEN`, but `from_env()` silently returned None —
    daily_run perpetually printed `listener skipped (no_telegram)`. The
    bug was operator-invisible because two code paths read different env
    vars for the same conceptual config.

    This test pins the canonical contract: .env.example IS the schema, and
    `from_env()` MUST read what .env.example documents.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test_canonical_token\n"
        "TELEGRAM_CHAT_ID=test_canonical_chat\n",
    )
    # Clear any os.environ pollution that would shadow .env values
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "HELIOS_TELEGRAM_BOT_TOKEN", "HELIOS_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)

    import config.settings as cs
    from config.settings import Settings
    test_settings = Settings(_env_file=str(env_file))
    monkeypatch.setattr(cs, "_settings", test_settings)

    from communication.telegram import TelegramConfig
    result = TelegramConfig.from_env()
    assert result is not None, (
        "INVARIANT VIOLATED: canonical .env with TELEGRAM_BOT_TOKEN failed "
        "to populate from_env(). Has bot.py reverted to HELIOS_-prefixed "
        "or some other non-canonical name?"
    )
    assert result.bot_token == "test_canonical_token"
    assert result.chat_id == "test_canonical_chat"


def test_telegram_config_does_not_read_helios_prefix(tmp_path, monkeypatch):
    """Invariant: HELIOS_-prefixed env vars MUST NOT populate from_env().

    This is the negative half of the canonical-keys invariant. Catches the
    specific pre-v0.1.14.3.4 bug if anyone re-introduces raw
    `os.environ.get("HELIOS_...")` in bot.py.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setenv("HELIOS_TELEGRAM_BOT_TOKEN", "old_helios_path_token")
    monkeypatch.setenv("HELIOS_TELEGRAM_CHAT_ID", "old_helios_path_chat")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    import config.settings as cs
    from config.settings import Settings
    test_settings = Settings(_env_file=str(env_file))
    monkeypatch.setattr(cs, "_settings", test_settings)

    from communication.telegram import TelegramConfig
    result = TelegramConfig.from_env()
    assert result is None, (
        f"INVARIANT VIOLATED: HELIOS_-prefixed env populated from_env() = "
        f"{result!r}. The pre-v0.1.14.3.4 buggy code path has resurfaced — "
        f"check whether bot.py uses raw os.environ.get with HELIOS_ prefix."
    )


def test_finmind_url_redaction_strips_token():
    """Invariant: _redact_url must strip `token=` query value before any
    URL string reaches a log handler.

    v0.1.14.3.4 trigger: helios.log.2026-05-16 contained dozens of
    download_unexpected_error events whose `exception` field carried the
    full FinMind URL — including `?token=<JWT>` — because httpx.HTTPStatusError
    formats the URL into its message and structlog's exc_info traceback
    captured it verbatim.
    """
    from data.sources.finmind_client import _redact_url

    url = (
        "https://api.finmindtrade.com/api/v4/data?"
        "data_id=0050&dataset=TaiwanStockPriceAdj&"
        "token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.SECRET_PAYLOAD.SIGNATURE_PART"
    )
    safe = _redact_url(url)
    for leaked_substring in ("eyJ0eXAi", "SECRET_PAYLOAD", "SIGNATURE_PART"):
        assert leaked_substring not in safe, (
            f"INVARIANT VIOLATED: '{leaked_substring}' leaked into safe URL: {safe}"
        )
    assert "token=***REDACTED***" in safe
    # Diagnostic context preserved
    assert "data_id=0050" in safe
    assert "dataset=TaiwanStockPriceAdj" in safe


def test_finmind_url_redaction_catches_multiple_secret_param_names():
    """_redact_url must also redact api_key, apikey, secret, password —
    not just `token`. Defensive: future endpoints may use any of these."""
    from data.sources.finmind_client import _redact_url

    url = "https://api/x?token=AAA&api_key=BBB&apikey=CCC&secret=DDD&password=EEE&data_id=Y"
    safe = _redact_url(url)
    for leak in ("AAA", "BBB", "CCC", "DDD", "EEE"):
        assert leak not in safe, f"INVARIANT VIOLATED: {leak!r} leaked: {safe}"
    assert "data_id=Y" in safe


def test_finmind_url_redaction_passthrough_when_no_secrets():
    """_redact_url returns input unchanged when no sensitive params present —
    avoids spurious modification of clean URLs."""
    from data.sources.finmind_client import _redact_url

    url = "https://api.finmindtrade.com/api/v4/data?dataset=X&data_id=Y&start_date=2026-01-01"
    assert _redact_url(url) == url


def test_finmind_http_error_propagated_exception_does_not_leak_token():
    """Invariant: an HTTPStatusError converted via _raise_finmind_http_error
    must produce a FinMindError whose string repr contains NO original token,
    AND whose context-chain (`__suppress_context__`) prevents the original
    exception from displaying in tracebacks.

    Pins the actual call-site wiring (not just _redact_url in isolation).
    Catches the specific failure mode that leaked tokens in
    helios.log.2026-05-16.
    """
    import httpx
    import pytest as _pytest

    from data.sources.finmind_client import (
        FinMindError,
        _raise_finmind_http_error,
    )

    request = httpx.Request(
        "GET",
        "https://api.finmindtrade.com/api/v4/data?"
        "data_id=0050&dataset=TaiwanStockPriceAdj&token=BEARER_SECRET_VALUE",
    )
    response = httpx.Response(400, request=request)
    original = httpx.HTTPStatusError(
        "Client error '400 Bad Request' for url 'https://api/x?token=BEARER_SECRET_VALUE'",
        request=request, response=response,
    )

    with _pytest.raises(FinMindError) as exc_info:
        _raise_finmind_http_error(original)

    msg = str(exc_info.value)
    assert "BEARER_SECRET_VALUE" not in msg, (
        f"INVARIANT VIOLATED: token leaked into FinMindError message: {msg}"
    )
    assert "***REDACTED***" in msg
    # Status code preserved for debugging
    assert "400" in msg
    # `from None` semantics: __cause__ cleared, __suppress_context__ set
    assert exc_info.value.__cause__ is None, (
        "raise ... from None must clear __cause__ to break the chained-"
        "traceback path that leaked tokens in v0.1.14.3.3 and earlier."
    )
    assert exc_info.value.__suppress_context__ is True, (
        "raise ... from None must set __suppress_context__=True so Python's "
        "'During handling of the above exception' chain does NOT print the "
        "original (un-redacted) HTTPStatusError message."
    )


# ─────────────────────────────────────────────────────────────
# Telegram listener: pre-startup queue isolation (v0.1.14.3.7)
# ─────────────────────────────────────────────────────────────


def test_listener_does_not_consume_pre_startup_telegram_updates(tmp_db, seed_calendar):
    """Invariant: messages that arrived in the Telegram queue BEFORE
    `listen_for_approvals` started must NOT influence signal state.

    Scar (2026-05-18): a stale "Approve" message left in Telegram's
    queue by a prior session (the 3.5 listener silently ignored it and
    never confirmed it back to Telegram) came back through getUpdates
    when a fresh 3.6 listener started with offset=0. classify_command
    resolved it onto the freshly-pushed DEV-TEST-003 signal — phantom
    approval the operator never sent. With ATR drift validation then
    failing because EOD prices weren't synced yet, the signal landed at
    EXPIRED_DRIFT 3 seconds after creation, before the operator had a
    chance to interact.

    Fix (`_drain_pre_startup_updates`): on listener entry, drain the
    Telegram queue via getUpdates(offset=-1) + getUpdates(offset=last+1)
    so the main loop starts after any pre-existing updates. This test
    pins that behavior: a stale "同意" planted in the queue before
    listener start must not transition any signal and must not remain in
    the queue (else it'd come back on the next listener too).
    """
    from communication.telegram.listener import listen_for_approvals
    from execution.paper_broker import PaperBroker
    from storage.signals import get_signal, save_signal
    from tests.conftest import MockTelegramBot

    cal = seed_calendar
    sid = save_signal(
        symbol="0050", strategy="invariant_test", signal_type="entry",
        score=0.9, price=140.0, reason=["test"],
        signal_date=cal[0], entry_atr=2.0,
    )

    bot = MockTelegramBot(chat_id="TEST_CHAT")
    # Plant a stale message as if it had been sitting in Telegram's queue
    # from a previous session (operator typed "同意" while a different
    # listener was running, or never running at all).
    bot.enqueue_text("同意")
    assert len(bot.update_queue) == 1, "test setup precondition"

    summary = listen_for_approvals(
        bot=bot, broker=PaperBroker(),
        fill_date=cal[1],
        target_notional_for=lambda _: 100000.0,
        duration_seconds=1, poll_timeout=1,
    )

    # INVARIANT 1: the stale message must NOT have triggered approve_signal
    assert summary["approved"] == [], (
        f"INVARIANT VIOLATED: pre-startup '同意' was consumed by the "
        f"listener and phantom-approved a signal. summary={summary}"
    )

    # INVARIANT 2: the signal must NOT have transitioned out of PENDING
    final = get_signal(sid)
    assert final is not None
    assert final.approval_status == "PENDING", (
        f"INVARIANT VIOLATED: signal transitioned to "
        f"{final.approval_status} from a stale pre-startup message. "
        f"This is exactly the 2026-05-18 phantom-approve scar."
    )

    # INVARIANT 3: the pre-startup queue must have been actually drained
    # (not merely ignored — if it just sat in the queue, it would come
    # back on the next listener startup and re-trigger the bug)
    assert bot.update_queue == [], (
        f"INVARIANT VIOLATED: pre-startup messages remain in queue and "
        f"will resurrect on the next listener startup: {bot.update_queue}"
    )


# ─────────────────────────────────────────────────────────────
# Approval drift check: symmetric "cannot verify" paths (v0.1.14.3.7)
# ─────────────────────────────────────────────────────────────


def test_check_atr_drift_returns_true_when_no_price_data_for_fill_date(tmp_db):
    """Invariant: `_check_atr_drift` must return `(True, ...skip...)` when
    no `daily_price_adj` row exists for `fill_date` — symmetric with the
    no-ATR branch (line 187-188) which also returns True/skip.

    Scar (2026-05-18): the function used to return `(False, "...無法驗證
    漂移")` when prices were missing. The caller in `approve_signal` then
    issued `update_approval(..., "EXPIRED_DRIFT")`, killing every approval
    attempted before that day's EOD price sync had run — i.e., every
    intraday approval on every trading day. The asymmetry: the SAME
    function returns True/skip when ATR is missing (also "cannot
    verify"), and the companion `execution.expiry.expire_by_drift`
    returns [] / does nothing when current_prices is empty (also "cannot
    verify"). Three layers, three handlings of the same condition — the
    one that bailed-with-block was the dangerous outlier.

    This invariant pins: every "cannot verify" exit must be permissive.
    Tests both the no-ATR and no-price paths in lockstep so a future
    cannot-verify branch added that returns False would break this test
    before shipping.
    """
    from types import SimpleNamespace

    from execution.approvals import _check_atr_drift

    # Case 1: no ATR — the pre-existing permissive branch (regression guard)
    sig_no_atr = SimpleNamespace(
        signal_id="invariant-no-atr",
        symbol="0050",
        price=140.0,
        entry_atr=0.0,
    )
    ok_no_atr, msg_no_atr = _check_atr_drift(sig_no_atr, date(2026, 5, 1), 0.5)
    assert ok_no_atr is True, (
        f"INVARIANT VIOLATED (regression in no-ATR path): expected True, "
        f"got ({ok_no_atr}, {msg_no_atr!r})"
    )
    assert "跳過" in msg_no_atr, (
        f"no-ATR skip message lost its '跳過' marker: {msg_no_atr!r}"
    )

    # Case 2: no price data for fill_date — the path fixed in v0.1.14.3.7.
    # ATR > 0 routes past the no-ATR branch and into the DB-query branch
    # where the bug lived. tmp_db is fresh; no daily_price_adj row for
    # this symbol/date exists.
    sig_no_price = SimpleNamespace(
        signal_id="invariant-no-price",
        symbol="UNSEEDED_SYMBOL",
        price=950.0,
        entry_atr=10.0,
    )
    ok_no_price, msg_no_price = _check_atr_drift(
        sig_no_price, date(2026, 5, 18), 0.5,
    )
    assert ok_no_price is True, (
        f"INVARIANT VIOLATED: no-price-data path returned False — this "
        f"is the asymmetry that caused the 2026-05-18 phantom "
        f"EXPIRED_DRIFT scar. msg={msg_no_price!r}. Must return True/skip "
        f"to match the no-ATR path's semantic."
    )
    assert "跳過" in msg_no_price, (
        f"no-price skip message must signal '跳過' for symmetry with "
        f"no-ATR path. Got: {msg_no_price!r}"
    )
