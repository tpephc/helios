# communication/telegram/listener.py
"""Telegram listener — 30-min polling window for /approve /reject /status.

Per ADR-008: polling (not webhook). Per decision-confirmation B1: ephemeral —
listener exits after window, doesn't run as a daemon.

Commands handled (v0.1.14.3.6):
  /approve <signal_id_or_prefix>  → execution.approvals.approve_signal
  /reject  <signal_id_or_prefix>  → execution.approvals.reject_signal
  /status                         → list PENDING signals
  /help                           → command list

  Shortcut (when exactly 1 signal is PENDING — the common case):
    同意 / 1 / yes / y / ok / approve → approve that single signal
    放棄 / 0 / no / n / reject        → reject that single signal
    /approve  (no arg)                → same as 同意
    /reject   (no arg)                → same as 放棄

  Multiple pending: shortcuts return a polite "請用 /approve <id> 指明"
  warning rather than guessing. Zero pending: "目前沒有待處理訊號。"

Unrecognized slash-prefixed messages get a /help hint. Plain text that
doesn't match a shortcut is silently ignored to avoid noisy bot behavior.

v0.1.14.3.7: pre-startup queue drain. On entry to `listen_for_approvals`,
any Telegram updates that arrived before the listener started are
consumed and discarded — without this, a stale "同意" or "Approve" from
a previous session can phantom-approve a fresh signal when a new
listener starts. See `_drain_pre_startup_updates`.

Version: v0.1.2 (2026-05-18 — v0.1.14.3.7 pre-startup drain)
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from communication.telegram.bot import TelegramBot
from execution.approvals import approve_signal, list_pending_for_display, reject_signal
from execution.paper_broker import PaperBroker
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Shortcut alphabet (v0.1.14.3.6)
# ─────────────────────────────────────────────────────────────
# Lowercased; Chinese terms are case-invariant anyway. Operator types
# any one of these tokens and — IF there is exactly one PENDING signal —
# the listener treats it as a command on that signal.
#
# Design intent: cover the operator's natural-language mistake from the
# v0.1.14.3.5 screenshot ("Approve" without slash) AND offer ultra-short
# mobile-friendly forms ("1" / "0" / "同意" / "放棄"). The set is kept
# small to keep the command surface easy to remember / document.
APPROVE_SHORTCUTS: frozenset[str] = frozenset({
    "同意", "approve", "1", "yes", "y", "ok",
})
REJECT_SHORTCUTS: frozenset[str] = frozenset({
    "放棄", "reject", "0", "no", "n",
})


# ─────────────────────────────────────────────────────────────
# Pure command classifier (v0.1.14.3.6 — extracted for unit testability)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CommandAction:
    """Outcome of parsing a single operator message.

    `kind` enumerates what the dispatcher should do next:
      "help"      — send help text
      "status"    — send current pending list
      "approve"   — call approve_signal with .sig_ref
      "reject"    — call reject_signal with .sig_ref
      "warn"      — operator-facing warning (no DB action); .message is the text
      "unknown"   — unrecognized slash command; bot replies with .message
      "noop"      — plain text not matching anything; silently ignored
    """
    kind: str
    sig_ref: str | None = None
    message: str | None = None


def classify_command(text: str, pending: list[Any]) -> CommandAction:
    """Parse an operator message into a CommandAction. Pure function.

    `pending` is a list of objects with `.signal_id` and `.symbol` attributes
    (typically `SignalRow`s) — the current PENDING signals at message-receipt
    time. Used for single-pending resolution and ambiguity warnings.

    No side effects. No DB / network access. Fully unit-testable.
    """
    parts = text.strip().split()
    if not parts:
        return CommandAction(kind="noop")
    cmd = parts[0].lower()
    args = parts[1:]

    # Pure-info commands
    if cmd == "/help":
        return CommandAction(kind="help")
    if cmd == "/status":
        return CommandAction(kind="status")

    # Determine intent (approve vs reject) and whether an explicit sig_ref was given
    explicit_ref: str | None = None
    intent: str | None = None
    if cmd == "/approve":
        intent = "approve"
        explicit_ref = args[0] if args else None
    elif cmd == "/reject":
        intent = "reject"
        explicit_ref = args[0] if args else None
    elif cmd in APPROVE_SHORTCUTS:
        intent = "approve"
    elif cmd in REJECT_SHORTCUTS:
        intent = "reject"

    if intent is None:
        # Doesn't match any known command
        if cmd.startswith("/"):
            return CommandAction(
                kind="unknown",
                message=f"未知指令 `{cmd}`。請傳 `/help` 看可用指令。",
            )
        return CommandAction(kind="noop")

    # Explicit sig_ref always wins (lets operator override single-pending fallback)
    if explicit_ref:
        return CommandAction(kind=intent, sig_ref=explicit_ref)

    # Implicit form: must resolve to exactly one PENDING signal
    if not pending:
        return CommandAction(
            kind="warn", message="目前沒有待處理訊號。",
        )
    if len(pending) > 1:
        listing = ", ".join(f"{s.symbol}(`{s.signal_id[:8]}`)" for s in pending)
        sample = pending[0].signal_id[:8]
        return CommandAction(
            kind="warn",
            message=(
                f"目前有 {len(pending)} 筆待處理:{listing}\n"
                f"請用 `/{intent} <id>` 指明,例如 `/{intent} {sample}`"
            ),
        )
    return CommandAction(kind=intent, sig_ref=pending[0].signal_id)


# ─────────────────────────────────────────────────────────────
# Listener main loop
# ─────────────────────────────────────────────────────────────


def _drain_pre_startup_updates(bot: TelegramBot) -> int:
    """Consume Telegram updates that arrived before this listener started.

    Returns the offset to use for the main loop's first poll (= one past the
    last drained update_id, or 0 if the queue was empty).

    Why this exists (v0.1.14.3.7): a real bug observed on 2026-05-18 day-1
    deployment. Operator's prior-session 'Approve' message (which the 3.5
    listener could not classify and never confirmed) sat in the Telegram
    queue. When a new listener started with offset=0, that stale message
    came back through getUpdates and the 3.6 classifier resolved it onto
    the freshly-pushed DEV-TEST-003 signal — phantom approval the operator
    never sent.

    Mechanism: Telegram's getUpdates with offset=-1 returns the LAST pending
    update (1 item) without confirming. We then call getUpdates with
    offset=last_update_id+1 (timeout=0, return-immediately) which Telegram
    treats as 'confirm everything up to this id', dropping them from the
    queue. The main loop then enters with offset already past any
    pre-startup messages.

    Edge cases:
      - Empty queue: offset=-1 returns []; we return 0 and the main loop
        starts fresh.
      - One pending: offset=-1 returns the single item; we confirm at
        last_id+1; loop starts at last_id+1.
    """
    batch = bot.get_updates(offset=-1, timeout=0)
    if not batch:
        return 0
    last_id = batch[-1].get("update_id", 0)
    # Confirm-and-discard everything up to and including last_id
    bot.get_updates(offset=last_id + 1, timeout=0)
    logger.info(
        "listener_drained_pre_startup",
        last_update_id=last_id, drained_count=len(batch),
    )
    return last_id + 1


def listen_for_approvals(
    bot: TelegramBot,
    broker: PaperBroker,
    *,
    fill_date: date_type,
    target_notional_for: Callable[[str], float],
    account_id: str,
    duration_seconds: int = 1800,
    poll_timeout: int = 25,
) -> dict:
    """Listen for /approve and /reject commands for `duration_seconds`.

    v0.1.18: account_id required — passed to approve_signal for
    multi-account position isolation.

    Returns summary dict:
        approved: list of (signal_id, position_id)
        rejected: list of signal_ids
        ignored:  list of (text, reason)
        polls:    int total getUpdates calls (main-loop polls only;
                  pre-startup drain not counted)
    """
    end_at = time.time() + duration_seconds
    # v0.1.14.3.7: drain any stale updates BEFORE entering the main loop
    offset = _drain_pre_startup_updates(bot)
    summary: dict = {"approved": [], "rejected": [], "ignored": [], "polls": 0}

    # Initial banner
    pending = list_pending_for_display()
    if pending:
        symbols = ", ".join(s.symbol for s in pending[:5])
        if len(pending) == 1:
            hint = "回覆「同意」或「1」核准,「放棄」或「0」拒絕"
        else:
            hint = "請用 `/approve <id>` 指明訊號"
        bot.send_message(
            f"🤖 Helios 監聽中({duration_seconds // 60} 分鐘)。\n"
            f"目前 {len(pending)} 筆待處理:{symbols}\n"
            f"{hint}"
        )

    while time.time() < end_at:
        remaining = int(end_at - time.time())
        timeout = min(poll_timeout, max(1, remaining))
        updates = bot.get_updates(offset=offset, timeout=timeout)
        summary["polls"] += 1

        for upd in updates:
            offset = max(offset, upd.get("update_id", 0) + 1)
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            if not text:
                continue

            # P0-1 security gate: only the configured operator chat may issue commands.
            # Without this, any user who guesses the bot username can /approve trades.
            chat = msg.get("chat") or {}
            incoming_chat_id = str(chat.get("id", ""))
            if incoming_chat_id != str(bot.config.chat_id):
                logger.warning(
                    "telegram_unauthorized_chat",
                    incoming_chat_id=incoming_chat_id,
                    expected_chat_id=bot.config.chat_id,
                    text_preview=text[:50],
                )
                summary["ignored"].append((text, f"unauthorized_chat:{incoming_chat_id}"))
                continue

            _handle_command(text, bot, broker, fill_date, target_notional_for, summary)

        if not list_pending_for_display():
            # All done — early exit
            logger.info("listener_no_more_pending_early_exit")
            bot.send_message("✅ 所有待處理訊號都處理完了,提早結束監聽。")
            break

    if time.time() >= end_at:
        bot.send_message(
            f"⏱️ 監聽時間結束。"
            f"已核准:{len(summary['approved'])} 筆,"
            f"已拒絕:{len(summary['rejected'])} 筆。"
            f"剩餘待處理訊號將在下一次 daily_run 失效。"
        )

    return summary


# ─────────────────────────────────────────────────────────────
# Command dispatch — thin wrapper around classify_command's result
# ─────────────────────────────────────────────────────────────


def _handle_command(
    text: str,
    bot: TelegramBot,
    broker: PaperBroker,
    fill_date: date_type,
    target_notional_for: Callable[[str], float],
    summary: dict,
) -> None:
    """Parse + dispatch a single message. Side effects via bot.send_message."""
    action = classify_command(text, list_pending_for_display())

    if action.kind == "help":
        _send_help(bot)
    elif action.kind == "status":
        _send_status(bot)
    elif action.kind == "warn":
        bot.send_message(action.message or "")
    elif action.kind == "approve":
        assert action.sig_ref is not None
        _do_approve(
            action.sig_ref, bot, broker, fill_date,
            target_notional_for, summary,
            account_id=account_id,
        )
    elif action.kind == "reject":
        assert action.sig_ref is not None
        _do_reject(action.sig_ref, bot, summary)
    elif action.kind == "unknown":
        bot.send_message(action.message or "")
        summary["ignored"].append((text, "unknown_command"))
    else:  # noop
        summary["ignored"].append((text, "noop"))


def _send_help(bot: TelegramBot) -> None:
    bot.send_message(
        "Helios 監聽指令:\n"
        "\n"
        "單筆待處理時最快:\n"
        "  `同意` / `1` / `yes` — 核准\n"
        "  `放棄` / `0` / `no`  — 拒絕\n"
        "\n"
        "多筆待處理時:\n"
        "  `/approve <訊號 id 或前綴>` — 核准\n"
        "  `/reject <訊號 id 或前綴>` — 拒絕\n"
        "\n"
        "其他:\n"
        "  `/status` — 列出待處理訊號\n"
        "  `/help` — 顯示這則訊息"
    )


def _send_status(bot: TelegramBot) -> None:
    pending = list_pending_for_display()
    if not pending:
        bot.send_message("目前沒有待處理訊號。")
        return
    lines = ["待處理訊號:"]
    for s in pending:
        lines.append(
            f"  `{s.signal_id[:8]}` {s.symbol} 分數={s.score:.2f} "
            f"價={s.price:.2f}"
        )
    bot.send_message("\n".join(lines))


def _do_approve(
    sig_ref: str,
    bot: TelegramBot,
    broker: PaperBroker,
    fill_date: date_type,
    target_notional_for: Callable[[str], float],
    summary: dict,
    *,
    account_id: str,
) -> None:
    notional = target_notional_for(sig_ref)
    if notional <= 0:
        bot.send_message(f"❌ 無法計算 `{sig_ref}` 的部位金額(訊號不存在?)")
        return
    ok, msg, pos_id = approve_signal(
        sig_ref, target_notional=notional, fill_date=fill_date,
        broker=broker, account_id=account_id, approved_by="telegram",
    )
    bot.send_message(("✅ " if ok else "❌ ") + msg)
    if ok:
        summary["approved"].append((sig_ref, pos_id))


def _do_reject(
    sig_ref: str,
    bot: TelegramBot,
    summary: dict,
) -> None:
    ok, msg = reject_signal(sig_ref, rejected_by="telegram")
    bot.send_message(("✅ " if ok else "❌ ") + msg)
    if ok:
        summary["rejected"].append(sig_ref)
