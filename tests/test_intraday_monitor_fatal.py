# tests/test_intraday_monitor_fatal.py
"""Regression tests for P1-OBS — intraday_monitor fatal self-alert (v0.1.16).

Verifies the three acceptance criteria from backlog_P1-OBS:

  AC-1: A fatal exception triggers an immediate Telegram alert within the
        same run (_send_fatal_alert called, push_simple invoked).
  AC-2: A fatal exception writes a sentinel row to intraday_monitor_runs
        with system_alert_sent reflecting actual Telegram delivery status.
  AC-3: A DuckDB lock conflict on connect() is retried up to _DB_RETRY_COUNT
        times before raising (_connect_with_retry retry behaviour).

All tests are unit-level: DB and Telegram are mocked. No live DB or
Telegram credentials are required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

import scripts.intraday_monitor as mon


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def frozen_run_at() -> datetime:
    return datetime(2026, 6, 7, 2, 0, 0, tzinfo=timezone.utc)


# ── AC-1: fatal triggers Telegram alert ──────────────────────────────────────

class TestSendFatalAlert:

    def test_returns_true_on_successful_send(self, frozen_run_at: datetime) -> None:
        mock_bot = MagicMock()
        with (
            patch.object(mon, "_build_bot", return_value=mock_bot),
            patch("communication.telegram.sender.push_simple") as mock_push,
        ):
            result = mon._send_fatal_alert(frozen_run_at, "IOException: lock")
        assert result is True
        mock_push.assert_called_once()

    def test_alert_message_contains_run_at_and_error(self, frozen_run_at: datetime) -> None:
        mock_bot = MagicMock()
        captured: list[str] = []
        with (
            patch.object(mon, "_build_bot", return_value=mock_bot),
            patch(
                "communication.telegram.sender.push_simple",
                side_effect=lambda bot, msg: captured.append(msg),
            ),
        ):
            mon._send_fatal_alert(frozen_run_at, "IOException: helios.duckdb")

        assert len(captured) == 1
        msg = captured[0]
        assert frozen_run_at.isoformat() in msg
        assert "IOException: helios.duckdb" in msg
        assert "FATAL" in msg

    def test_returns_false_when_build_bot_raises(self, frozen_run_at: datetime) -> None:
        with patch.object(mon, "_build_bot", side_effect=RuntimeError("no token")):
            result = mon._send_fatal_alert(frozen_run_at, "some error")
        assert result is False

    def test_returns_false_when_push_simple_raises(self, frozen_run_at: datetime) -> None:
        mock_bot = MagicMock()
        with (
            patch.object(mon, "_build_bot", return_value=mock_bot),
            patch(
                "communication.telegram.sender.push_simple",
                side_effect=ConnectionError("network error"),
            ),
        ):
            result = mon._send_fatal_alert(frozen_run_at, "some error")
        assert result is False


# ── AC-2: fatal writes sentinel DB row ───────────────────────────────────────

class TestWriteFatalRunRow:

    def _make_mock_conn(self) -> MagicMock:
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def test_inserts_row_with_alert_sent_true(self, frozen_run_at: datetime) -> None:
        mock_conn = self._make_mock_conn()
        with patch.object(mon, "connect", return_value=mock_conn):
            mon._write_fatal_run_row(frozen_run_at, "IOException: lock", True)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        params = call_args[0][1]
        # params: [run_id, run_at_iso, system_alert_sent, error_detail]
        assert params[2] == 1  # system_alert_sent = True → 1

    def test_inserts_row_with_alert_sent_false(self, frozen_run_at: datetime) -> None:
        mock_conn = self._make_mock_conn()
        with patch.object(mon, "connect", return_value=mock_conn):
            mon._write_fatal_run_row(frozen_run_at, "IOException: lock", False)

        params = mock_conn.execute.call_args[0][1]
        assert params[2] == 0  # system_alert_sent = False → 0

    def test_system_alert_sent_not_hardcoded(self, frozen_run_at: datetime) -> None:
        """Verify that True and False produce different system_alert_sent values."""
        results: list[int] = []
        for sent in (True, False):
            mock_conn = self._make_mock_conn()
            with patch.object(mon, "connect", return_value=mock_conn):
                mon._write_fatal_run_row(frozen_run_at, "error", sent)
            params = mock_conn.execute.call_args[0][1]
            results.append(params[2])
        assert results == [1, 0]

    def test_error_detail_truncated_to_500(self, frozen_run_at: datetime) -> None:
        mock_conn = self._make_mock_conn()
        long_error = "x" * 600
        with patch.object(mon, "connect", return_value=mock_conn):
            mon._write_fatal_run_row(frozen_run_at, long_error, True)
        params = mock_conn.execute.call_args[0][1]
        assert len(params[3]) == 500

    def test_swallows_db_exception(self, frozen_run_at: datetime) -> None:
        """DB failure in _write_fatal_run_row must not raise — best-effort."""
        with patch.object(mon, "connect", side_effect=Exception("DB unavailable")):
            # Must not raise
            mon._write_fatal_run_row(frozen_run_at, "original error", True)

    def test_run_id_format(self, frozen_run_at: datetime) -> None:
        mock_conn = self._make_mock_conn()
        with patch.object(mon, "connect", return_value=mock_conn):
            mon._write_fatal_run_row(frozen_run_at, "error", True)
        params = mock_conn.execute.call_args[0][1]
        run_id = params[0]
        assert run_id.startswith("imon_20260607_020000_")
        assert len(run_id) == len("imon_20260607_020000_") + 6


# ── AC-3: DuckDB lock retry ───────────────────────────────────────────────────

class TestConnectWithRetry:

    def _make_lock_error(self) -> Exception:
        """Construct a mock IOException that matches _is_duckdb_lock_error."""
        IOException = type("IOException", (Exception,), {})
        return IOException("IO Error: Could not set lock on file \"/tmp/helios.duckdb\"")

    def test_succeeds_on_first_try(self) -> None:
        mock_conn = MagicMock()
        with patch.object(mon, "connect", return_value=mock_conn) as mock_connect:
            result = mon._connect_with_retry()
        assert result is mock_conn
        assert mock_connect.call_count == 1

    def test_retries_on_lock_error_then_succeeds(self) -> None:
        mock_conn = MagicMock()
        lock_err = self._make_lock_error()
        with (
            patch.object(mon, "connect", side_effect=[lock_err, lock_err, mock_conn]),
            patch.object(mon, "time") as mock_time,
        ):
            result = mon._connect_with_retry()
        assert result is mock_conn
        assert mock_time.sleep.call_count == 2
        mock_time.sleep.assert_called_with(mon._DB_RETRY_SLEEP_S)

    def test_raises_after_max_retries_exhausted(self) -> None:
        lock_err = self._make_lock_error()
        side_effects = [lock_err] * (mon._DB_RETRY_COUNT + 1)
        with (
            patch.object(mon, "connect", side_effect=side_effects),
            patch.object(mon, "time"),
        ):
            with pytest.raises(Exception):
                mon._connect_with_retry()

    def test_does_not_retry_non_lock_error(self) -> None:
        non_lock_err = RuntimeError("some other error")
        with patch.object(mon, "connect", side_effect=non_lock_err):
            with pytest.raises(RuntimeError):
                mon._connect_with_retry()

    def test_is_duckdb_lock_error_true(self) -> None:
        exc = self._make_lock_error()
        assert mon._is_duckdb_lock_error(exc) is True

    def test_is_duckdb_lock_error_false_wrong_message(self) -> None:
        exc = type("IOException", (Exception,), {})("some other IO error")
        assert mon._is_duckdb_lock_error(exc) is False

    def test_is_duckdb_lock_error_false_wrong_type(self) -> None:
        exc = RuntimeError("Could not set lock on file")
        assert mon._is_duckdb_lock_error(exc) is False
