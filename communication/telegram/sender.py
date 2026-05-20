# communication/telegram/sender.py
"""High-level Telegram message formatters + push helpers.

Per review #4 (risk preview): entry approval requests must include portfolio
context — current exposure, cash buffer, sector exposure, ATR drift threshold —
so operator can make informed decisions.

Version: v0.1.0 (2026-05-17)
"""
from __future__ import annotations

from communication.telegram.bot import TelegramBot
from portfolio.selector import get_sector, is_etf
from storage.signals import SignalRow
from utils.logger import get_logger

logger = get_logger(__name__)


def format_entry_request(
    sig: SignalRow,
    *,
    target_notional: float,
    cash: float,
    equity: float,
    sector_value: float,
    etf_value: float,
    pos_value: float,
    budget,  # RiskBudget
) -> str:
    """Format a /approve-able entry signal with risk preview.

    Telegram message format (Markdown, Chinese — v0.1.14.3.5):

        🟢 進場訊號 — 2330 (semi)
        訊號 ID: abc12345
        分數: 0.82  /  價: 595.00  /  ATR: 11.20
        策略: trend_breakout_v1  /  市況: bull

        理由:
          • multi-MA aligned (close > SMA50 > SMA200)
          • breakout above 20D high
          • RSI 62 (sweet spot)
          • volume 1.8x average

        核准後的曝險變化:
          整體部位:     29.0% → 47.0%
          現金水位:     71.0% → 53.0%  (下限 10%)
          類股 'semi':   9.0% → 27.0%  (上限 30%)

        漂移門檻: 0.5×ATR = 5.60 (價格偏離超過此值，訊號自動失效)
        請在 09:30:00 之前回覆

        /approve abc123  或  /reject abc123
    """
    sid_short = sig.signal_id[:8]
    sym = sig.symbol
    sector = get_sector(sym)
    is_etf_sym = is_etf(sym)

    # Compose risk preview (avoid div-by-zero)
    cur_exp = (pos_value / equity * 100) if equity > 0 else 0.0
    new_exp = ((pos_value + target_notional) / equity * 100) if equity > 0 else 0.0
    cur_cash = (cash / equity * 100) if equity > 0 else 100.0
    new_cash = ((cash - target_notional) / equity * 100) if equity > 0 else 0.0
    sec_cur = (sector_value / equity * 100) if equity > 0 else 0.0
    sec_new = ((sector_value + target_notional) / equity * 100) if equity > 0 else 0.0

    lines: list[str] = [
        f"🟢 *進場訊號 — {sym}* ({sector})",
        f"訊號 ID: `{sig.signal_id}`",
        f"分數: {sig.score:.2f} / 價: {sig.price:.2f} / ATR: {sig.entry_atr:.2f}"
            if sig.entry_atr else f"分數: {sig.score:.2f} / 價: {sig.price:.2f}",
        f"策略: `{sig.strategy}` / 市況: `{sig.regime or '?'}`",
        "",
        "理由:",
    ]
    for r in (sig.reason or [])[:5]:
        lines.append(f"  • {r}")
    lines.extend([
        "",
        "核准後的曝險變化:",
        f"  整體部位:  {cur_exp:.1f}% → {new_exp:.1f}%",
        f"  現金水位:  {cur_cash:.1f}% → {new_cash:.1f}%  "
        f"(下限 {budget.cash_buffer_pct*100:.0f}%)",
        f"  類股 '{sector}':  {sec_cur:.1f}% → {sec_new:.1f}%  "
        f"(上限 {budget.max_sector_exposure_pct*100:.0f}%)",
    ])
    if is_etf_sym:
        etf_cur = (etf_value / equity * 100) if equity > 0 else 0
        etf_new = ((etf_value + target_notional) / equity * 100) if equity > 0 else 0
        lines.append(
            f"  ETF 總曝險:  {etf_cur:.1f}% → {etf_new:.1f}%  "
            f"(上限 {budget.max_etf_exposure_pct*100:.0f}%)"
        )

    if sig.entry_atr and sig.entry_atr > 0:
        lines.extend([
            "",
            f"漂移門檻: 0.5×ATR = {0.5 * sig.entry_atr:.2f} "
            f"(價格偏離超過此值，訊號自動失效)",
        ])
    if sig.timeout_at:
        lines.append(
            f"請在 {sig.timeout_at:%H:%M:%S} 之前回覆"
        )
    lines.extend([
        "",
        "回覆「同意」或「1」核准 ／「放棄」或「0」拒絕",
        f"(或明確指定:`/approve {sid_short}` 或 `/reject {sid_short}`)",
    ])
    return "\n".join(lines)


def push_entry_request(
    bot: TelegramBot,
    sig: SignalRow,
    *,
    target_notional: float,
    cash: float,
    equity: float,
    sector_value: float,
    etf_value: float,
    pos_value: float,
    budget,
) -> int | None:
    """Format + send. Returns message_id or None on failure."""
    text = format_entry_request(
        sig, target_notional=target_notional, cash=cash, equity=equity,
        sector_value=sector_value, etf_value=etf_value, pos_value=pos_value,
        budget=budget,
    )
    return bot.send_message(text)


def push_exit_notification(
    bot: TelegramBot,
    symbol: str, exit_reason: str, exit_price: float, gross_return_pct: float,
    proceeds_ntd: float,
) -> int | None:
    """Push a notification when an auto-exit fires."""
    emoji = "🟢" if gross_return_pct > 0 else "🔴"
    text = (
        f"{emoji} *已出場 — {symbol}*\n"
        f"原因: `{exit_reason}`\n"
        f"出場價: {exit_price:.2f}\n"
        f"毛報酬: {gross_return_pct:+.2f}%\n"
        f"實收金額: NTD {proceeds_ntd:,.0f}"
    )
    return bot.send_message(text)


def push_simple(bot: TelegramBot, text: str) -> int | None:
    return bot.send_message(text)
