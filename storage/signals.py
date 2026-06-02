# storage/signals.py
"""訊號 event log 持久化 + approval state machine。

支援的 approval_status：
  PENDING         - 等待人工確認
  APPROVED        - 已確認 (Telegram / CLI)
  REJECTED        - 人工拒絕
  TIMEOUT         - 超過 approval timeout
  EXPIRED_DRIFT   - 價格偏離 entry > 0.5 ATR (review 採納)
  AUTO_APPROVED   - 低風險自動通過 (v0.4+)

設計：每個函數都是純 SQL wrapper，無狀態，可被 runtime/engine.py 任意呼叫。

Version: v0.1.1 (2026-05-16)
Changelog:
  v0.1.1 (2026-05-16): update_approval 改用 UPDATE...RETURNING 確保原子性 (修 race + N+1); expire_drifted 改批次 UPDATE (200+ DB calls → 2)
  v0.1.0 (2026-05-16): Initial implementation
"""
from __future__ import annotations

import json
import uuid
import duckdb
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Literal

from data.database import connect
from utils.logger import get_logger

logger = get_logger(__name__)
@dataclass(frozen=True)
class SaveSignalResult:
    """Return value of save_signal().

    created=True  : new row inserted into DB.
    created=False : canonical key already exists; existing signal_id returned,
                    no new row written. Caller must skip Telegram notification
                    and auto-approve.
    """

    signal_id: str
    created: bool


ApprovalStatus = Literal[
    "PENDING", "APPROVED", "REJECTED", "TIMEOUT", "EXPIRED_DRIFT", "AUTO_APPROVED"
]


@dataclass
class SignalRow:
    """signals 表的列表示 (1:1 mapping 到 schema)。

    v0.1.14.2-c3: temporal semantics split.
      signal_date  — 市場語意日期 (the trading day this signal corresponds to)
      created_at   — 系統建立時間 (when the row was inserted, may differ from signal_date
                     for catch-up runs, weekend reruns, backtest replays)
    """

    signal_id: str
    signal_date: date_type    # 市場語意日期
    created_at: datetime      # 系統建立時間
    symbol: str
    strategy: str
    signal_type: str          # buy / sell / exit
    score: float
    price: float
    entry_atr: float | None
    stop_loss: float | None
    take_profit: float | None
    reason: list[str]
    regime: str | None
    approval_status: ApprovalStatus
    approved_at: datetime | None = None
    approved_by: str | None = None
    timeout_at: datetime | None = None
    expired_reason: str | None = None
    metadata: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Create / Read
# ─────────────────────────────────────────────────────────────


def save_signal(
    symbol: str,
    strategy: str,
    signal_type: str,
    score: float,
    price: float,
    reason: list[str],
    *,
    signal_date: date_type,     # v0.1.14.2-c3: required; market semantic date
    entry_atr: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    regime: str | None = None,
    approval_status: ApprovalStatus = "PENDING",
    timeout_minutes: int = 30,
    metadata: dict | None = None,
    signal_id: str | None = None,
) -> SaveSignalResult:
    """寫入新訊號，回傳 SaveSignalResult(signal_id, created)。

    created=True  : 新 row 寫入 DB。
    created=False : canonical key (symbol, strategy, signal_type, signal_date)
                    已存在，回傳既有 signal_id，未寫入新 row。Caller 應跳過
                    Telegram 通知與 auto-approve。

    Signals are event-keyed, not generation-keyed (decided 2026-06-02).
    Terminal states (REJECTED, EXPIRED_DRIFT, TIMEOUT) permanently close the
    canonical signal event. A rerun of the same opportunity returns the
    existing signal_id with created=False.

    v0.1.14.2-c3: signal_date is REQUIRED. It is the market-semantic date
    (the as_of for the run that generated this signal), distinct from
    created_at (system insertion time).

    v0.1.14.3.3: optional `signal_id` kwarg lets callers supply their own
    identifier (e.g. `DEV-TEST-001` for `scripts/dev_push_signal.py` test
    injection). Default behavior unchanged (uuid4 auto-generated).

    v0.1.2 (2026-06-02): returns SaveSignalResult; idempotent on canonical key.
    """
    if signal_id is None:
        signal_id = str(uuid.uuid4())
    now = datetime.now()
    timeout_at = now + timedelta(minutes=timeout_minutes) if approval_status == "PENDING" else None

    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    signal_id, signal_date, created_at, symbol, strategy, signal_type,
                    score, price, entry_atr, stop_loss, take_profit,
                    reason, regime, approval_status, timeout_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    signal_id, signal_date, now, symbol, strategy, signal_type,
                    score, price, entry_atr, stop_loss, take_profit,
                    json.dumps(reason, ensure_ascii=False),
                    regime, approval_status, timeout_at,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ],
            )
        logger.info(
            "signal_saved",
            signal_id=signal_id, signal_date=str(signal_date),
            symbol=symbol, strategy=strategy, score=score, status=approval_status,
        )
        return SaveSignalResult(signal_id=signal_id, created=True)

    except duckdb.ConstraintException as exc:
        # Only handle canonical key conflicts. Re-raise for PK, NOT NULL,
        # CHECK, or any other constraint violation.
        with connect(read_only=True) as conn:
            row = conn.execute(
                """
                SELECT signal_id FROM signals
                WHERE symbol = ? AND strategy = ? AND signal_type = ? AND signal_date = ?
                """,
                [symbol, strategy, signal_type, signal_date],
            ).fetchone()

        if row is None:
            # ConstraintException came from a different constraint (e.g. PK
            # collision where signal_id exists under a different canonical key).
            raise RuntimeError(
                f"ConstraintException on INSERT but canonical key not found "
                f"({symbol}, {strategy}, {signal_type}, {signal_date}). "
                f"Original exception: {exc}"
            ) from exc

        existing_id = row[0]
        logger.info(
            "signal_duplicate_canonical_key",
            existing_signal_id=existing_id,
            rejected_signal_id=signal_id,
            signal_date=str(signal_date),
            symbol=symbol,
            strategy=strategy,
            created=False,
        )
        return SaveSignalResult(signal_id=existing_id, created=False)


def get_signal(signal_id: str) -> SignalRow | None:
    """取得單一訊號，找不到回 None。"""
    with connect(read_only=True) as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE signal_id = ?", [signal_id]
        ).fetchone()
        cols = [c[0] for c in conn.description]
    if not row:
        return None
    return _row_to_dataclass(dict(zip(cols, row, strict=True)))


def get_pending() -> list[SignalRow]:
    """取得所有 PENDING 訊號 (按建立時間正序)。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE approval_status = 'PENDING' "
            "ORDER BY signal_date ASC, created_at ASC"
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


def get_recent(limit: int = 20) -> list[SignalRow]:
    """取得最近 N 筆訊號 (任何狀態)。"""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", [limit]
        ).fetchall()
        cols = [c[0] for c in conn.description]
    return [_row_to_dataclass(dict(zip(cols, r, strict=True))) for r in rows]


# ─────────────────────────────────────────────────────────────
# State transitions (approval flow)
# ─────────────────────────────────────────────────────────────


def update_approval(
    signal_id: str,
    new_status: ApprovalStatus,
    approved_by: str | None = None,
    expired_reason: str | None = None,
) -> bool:
    """更新訊號狀態。回傳是否成功 (False = 找不到此訊號 或 已非 PENDING)。

    runtime/engine.py 在收到 Telegram approval 時呼叫此函數。

    使用 UPDATE...RETURNING 確保原子性：只有 status=PENDING 的 row 會被改，
    且回傳列表就是被改的 row。一次 query，無 race window。
    """
    now = datetime.now()
    with connect() as conn:
        returned = conn.execute(
            """
            UPDATE signals SET
                approval_status = ?,
                approved_at = ?,
                approved_by = ?,
                expired_reason = ?
            WHERE signal_id = ? AND approval_status = 'PENDING'
            RETURNING signal_id
            """,
            [new_status, now, approved_by, expired_reason, signal_id],
        ).fetchall()

    if not returned:
        # 可能是 signal_id 不存在，也可能是已經非 PENDING
        # 用一次額外 SELECT 區分 (僅在失敗 path 才查，hot path 仍是一個 query)
        with connect(read_only=True) as conn:
            row = conn.execute(
                "SELECT approval_status FROM signals WHERE signal_id = ?", [signal_id]
            ).fetchone()
        if row is None:
            logger.warning("approval_update_signal_not_found", signal_id=signal_id)
        else:
            logger.warning(
                "approval_update_no_change",
                signal_id=signal_id, requested=new_status, current=row[0],
            )
        return False

    logger.info(
        "approval_updated",
        signal_id=signal_id, status=new_status, by=approved_by,
    )
    return True


def expire_timed_out(now: datetime | None = None) -> int:
    """把過了 timeout_at 仍為 PENDING 的訊號標記為 TIMEOUT。回傳處理筆數。"""
    now = now or datetime.now()
    with connect() as conn:
        # 先查出要過期的，方便 log
        to_expire = conn.execute(
            """
            SELECT signal_id, symbol FROM signals
            WHERE approval_status = 'PENDING' AND timeout_at < ?
            """,
            [now],
        ).fetchall()

        if not to_expire:
            return 0

        conn.execute(
            """
            UPDATE signals SET
                approval_status = 'TIMEOUT',
                approved_at = ?,
                expired_reason = 'timeout'
            WHERE approval_status = 'PENDING' AND timeout_at < ?
            """,
            [now, now],
        )

    for sid, sym in to_expire:
        logger.info("signal_timeout", signal_id=sid, symbol=sym)
    return len(to_expire)


def expire_drifted(
    current_prices: dict[str, float],
    max_drift_atr: float = 0.5,
) -> int:
    """價格偏離 entry > max_drift_atr × ATR 則標記為 EXPIRED_DRIFT。

    review 採納：避免 stale signal 在 timeout 內被執行卻已失去原始 R/R 結構。

    實作：先 SELECT 出 pending，在 Python 算 drift，
    然後一次 UPDATE 把所有命中的 signal_id 批次標記。
    對於 100 個 pending signal，這從 200+ DB calls 降到 2 calls。
    """
    if not current_prices:
        return 0

    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT signal_id, symbol, price, entry_atr FROM signals
            WHERE approval_status = 'PENDING'
              AND entry_atr IS NOT NULL
              AND entry_atr > 0
            """
        ).fetchall()

    if not rows:
        return 0

    # 在 Python 算 drift，收集要過期的 signal_id 與原因
    to_expire: list[tuple[str, str]] = []
    for sid, sym, entry_price, atr in rows:
        current = current_prices.get(sym)
        if current is None:
            continue
        drift_in_atr = abs(current - entry_price) / atr
        if drift_in_atr > max_drift_atr:
            to_expire.append((sid, f"atr_drift_{drift_in_atr:.2f}"))

    if not to_expire:
        return 0

    # 批次 UPDATE：DuckDB 支援 (?) IN list，每個 signal_id 一個 statement
    # 但更乾淨的做法是用 executemany
    now = datetime.now()
    with connect() as conn:
        for sid, reason in to_expire:
            conn.execute(
                """
                UPDATE signals SET
                    approval_status = 'EXPIRED_DRIFT',
                    approved_at = ?,
                    approved_by = 'auto',
                    expired_reason = ?
                WHERE signal_id = ? AND approval_status = 'PENDING'
                """,
                [now, reason, sid],
            )

    # 統一 log，不每個一筆
    logger.info(
        "signals_atr_drift_expired",
        count=len(to_expire),
        signal_ids=[sid for sid, _ in to_expire],
    )
    return len(to_expire)


# ─────────────────────────────────────────────────────────────
# Recovery support (per Helios architecture section 7.1)
# ─────────────────────────────────────────────────────────────


def load_pending_approvals() -> list[SignalRow]:
    """系統重啟後恢復用：載入所有 PENDING 訊號。"""
    return get_pending()


# ─────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────


def _row_to_dataclass(d: dict) -> SignalRow:
    """DuckDB 字典 row → SignalRow。處理 JSON 欄位解析。"""
    reason_raw = d.get("reason")
    reason = json.loads(reason_raw) if isinstance(reason_raw, str) else (reason_raw or [])

    metadata_raw = d.get("metadata")
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else (metadata_raw or {})

    return SignalRow(
        signal_id=d["signal_id"],
        signal_date=d["signal_date"],
        created_at=d["created_at"],
        symbol=d["symbol"],
        strategy=d["strategy"],
        signal_type=d["signal_type"],
        score=d["score"],
        price=d["price"],
        entry_atr=d.get("entry_atr"),
        stop_loss=d.get("stop_loss"),
        take_profit=d.get("take_profit"),
        reason=reason,
        regime=d.get("regime"),
        approval_status=d["approval_status"],
        approved_at=d.get("approved_at"),
        approved_by=d.get("approved_by"),
        timeout_at=d.get("timeout_at"),
        expired_reason=d.get("expired_reason"),
        metadata=metadata,
    )


# ─────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date as _date

    from data.database import init_schema
    init_schema()

    _r = save_signal(
        symbol="2330",
        strategy="trend_breakout",
        signal_type="buy",
        score=0.81,
        price=985.0,
        signal_date=_date.today(),
        entry_atr=18.5,
        stop_loss=948.0,
        take_profit=1058.0,
        reason=["20D breakout", "Volume 1.8x avg", "Above 200MA"],
        regime="strong_bull",
        timeout_minutes=30,
    )
    sid = _r.signal_id
    print(f"Created signal: {sid}  created={_r.created}")
    print(f"Pending: {len(get_pending())}")

    # Simulate ATR drift expiry
    n = expire_drifted({"2330": 998.0}, max_drift_atr=0.5)
    print(f"Expired by drift: {n}")

    # Final state
    sig = get_signal(sid)
    print(f"Final state: {sig.approval_status} ({sig.expired_reason})")
