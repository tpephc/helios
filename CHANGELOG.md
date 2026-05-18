# Helios Changelog

專案層級的變更紀錄。檔案層級的細節版號在各檔案 docstring 內。

格式：[Keep a Changelog](https://keepachangelog.com/) + [Semantic Versioning](https://semver.org/)。

## [Unreleased]

### Planned for v0.1.15 — Real broker integration prep
- Shioaji read-only integration
- `execution/reconciliation.py` real implementation (replace v0.1.14.2-b stub)
- Graduated daily-loss circuit breakers
- `scripts/run_exit_scan.py` modularization (>200 lines — deferred from v0.1.14.3
  to keep that diff focused on fill realism + observability)
- Approval result dataclass refactor (replace `tuple[bool, str, str | None]`
  with structured drift / fill metadata return — deferred from v0.1.14.3.1
  because it ripples through Telegram listener, summaries, and notifications)

### Planned for v0.2.0 — TWT49U + corporate_actions confidence engine

---

## [v0.1.14.3.6] — 2026-05-17 — Telegram shortcut commands (mobile UX)

### Trigger
v0.1.14.3.5 first end-to-end Telegram test surfaced an operator UX scar.
Screenshot showed operator typing `Approve` (no slash, no signal_id) and
the listener silently ignoring it because it didn't match `/approve <id>`.
Three messages (`Approve`, `1`, `2`) all marked ✓✓ delivered to nexus,
all silently dropped on the floor.

Root cause was strict command parsing: only `/approve <signal_id_or_prefix>`
and `/reject <signal_id_or_prefix>` were recognized. On mobile, typing
that exact form is awkward — autocaps fights the slash prefix, the signal
ID needs context-switching to read off the entry card, and there's no
keyboard shortcut for `/`.

For the common case — exactly one PENDING signal awaiting decision — the
explicit signal_id is information the listener already has. Operator
should be able to just say "yes" / "no" / "同意" / "放棄" / "1" / "0".

### Added
- **`APPROVE_SHORTCUTS` / `REJECT_SHORTCUTS`** (module-level frozensets
  in `communication/telegram/listener.py`):
  - Approve: `同意`, `approve`, `1`, `yes`, `y`, `ok`
  - Reject: `放棄`, `reject`, `0`, `no`, `n`
  - Lowercased for matching; Chinese is case-invariant; English variants
    cover the natural-language mistake from the screenshot
- **`classify_command(text, pending) → CommandAction`** — pure function
  extracted from the old `_handle_command`. Zero side effects, fully
  unit-testable without DB / network / mocks. Returns a tagged action:
  - `"approve"` / `"reject"` with resolved `sig_ref`
  - `"warn"` with operator-facing message (zero or multi-pending ambiguity)
  - `"help"` / `"status"` (info commands)
  - `"unknown"` (slash-prefixed but unrecognized — bot replies with hint)
  - `"noop"` (plain text that doesn't match anything — silently ignored)
- **Single-pending fallback for slash commands**: `/approve` and `/reject`
  with no argument now also resolve to the only PENDING signal (was
  previously "Usage: /approve <signal_id_or_prefix>"). This unifies the
  shortcut and slash command behaviors, and means BotFather's
  `/setcommands` autofill (which produces just `/approve`) works directly.

### Changed
- **`_handle_command` refactored to a thin dispatcher** on `CommandAction.kind`.
  Each branch is one line. The classification logic — the part that's
  easy to get wrong — moved to `classify_command` where it can be tested
  exhaustively.
- **Entry-request card hint updated** (`sender.py::format_entry_request`):
  - Was: `` `/approve DEV-TEST` 或 `/reject DEV-TEST` ``
  - Now:
    ```
    回覆「同意」或「1」核准 ／「放棄」或「0」拒絕
    (或明確指定:`/approve DEV-TEST` 或 `/reject DEV-TEST`)
    ```
- **`/help` rewritten** to teach the shortcut form first, then the
  explicit form. Hierarchy: most-common → less-common.
- **Listener banner** now adapts to pending count: 1 pending → show
  shortcut hint; multiple → tell operator to use `/approve <id>`.

### Tests (24 new in `tests/test_state_machine.py`)
Pure function tests of `classify_command` — fast, no DB / fixtures, just
duck-typed `SimpleNamespace` stand-ins for `SignalRow`:
- `test_classify_approve_shortcut_with_single_pending` (parametrized over
  9 forms: 同意 / Approve / approve / 1 / yes / YES / y / ok / OK)
- `test_classify_reject_shortcut_with_single_pending` (parametrized over
  7 forms: 放棄 / Reject / reject / 0 / no / NO / n)
- `test_classify_shortcut_with_zero_pending_warns` — `同意` with empty
  pending → `kind="warn"`, message contains "沒有待處理訊號"
- `test_classify_shortcut_with_multiple_pending_warns_with_ids` — `1`
  with two pendings → warn surfaces both symbol-id pairs + sample
  `/approve` form; `sig_ref` is None (no guess)
- `test_classify_explicit_slash_command_with_arg_wins_over_pending_count`
  — explicit ref always honored even with 0 or many pending
- `test_classify_slash_approve_without_arg_falls_back_to_single_pending` —
  `/approve` (BotFather autofill case) behaves like `同意`
- `test_classify_unknown_slash_command_returns_unknown_with_message` —
  `/foobar` → unknown kind, hint message contains the offending cmd
- `test_classify_plain_unrecognized_text_is_noop` — random chat noise
  doesn't trigger bot replies (over 6 sample inputs)
- `test_classify_help_and_status_independent_of_pending` — info commands
  classify regardless of pending count
- `test_classify_whitespace_and_case_robust` — `  同意  ` / `APPROVE` /
  `/Approve myid` all classify correctly

### Non-changes
- DB schema, signal lifecycle, state machine: unchanged
- `approve_signal` / `reject_signal` in `execution/approvals.py`: unchanged
  (still accept `signal_id_or_prefix`, the listener just resolves earlier)
- Authorization gate (chat_id check): unchanged — runs *before* the new
  classifier
- Existing tests: unchanged behavior, all green

### Operator notes
After deploying v0.1.14.3.6, the operator typing `Approve` from the
screenshot scenario WOULD have worked (case-insensitive match against
`approve` shortcut). For new flows:

```
[手機] 收到 entry-request 卡片 → 回 同意 (或 1, yes, approve)
[bot]  ✅ 訊號 DEV-TEST 已核准 → 部位 ... 已開倉
[bot]  ✅ 所有待處理訊號都處理完了,提早結束監聽。
[終端] script 退出, [3] listener returned: approved=1 rejected=0 polls=N
```

Or just go full minimal:
```
[手機] 1
[bot]  ✅ ...
```

Recommended one-time setup (operator-side, BotFather):
```
@BotFather → /setcommands → pick the bot → paste:
approve - 核准目前的待處理訊號（單筆時可省略 id）
reject - 拒絕目前的待處理訊號
status - 列出待處理訊號
help - 顯示指令說明
```
Once registered, the Telegram client shows a `/` menu near the input box
that autofills these — no typing slashes needed.

### Validation
```
ruff check .                              All checks passed
pytest tests/                             71 passed (47 prior + 24 new)
wc -l communication/telegram/listener.py  280  (was 189 — +91 for
                                                 classify_command,
                                                 CommandAction, extracted
                                                 helpers, docstrings)
```

### Deploy (additive — no DB / config / behavior regression)
```bash
scp ~/Downloads/helios-v0.1.14.3.6.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.6.zip && cd helios && uv sync

# Smoke — the DEV-TEST-001 from the v0.1.14.3.5 screenshot is probably
# still PENDING or TIMEOUT by now. Check state, then either retry or push fresh:
uv run python -c "
from storage.signals import get_signal
sig = get_signal('DEV-TEST-001')
print(f'status={sig.approval_status if sig else \"N/A\"}')
"

# Fresh end-to-end:
uv run python scripts/dev_push_signal.py --ticker 2330 --price 950
# 手機收到 entry card (中文 + 新的「同意」/「1」hint)
# 手機回:同意   ← 一個字
# bot 回:✅ 訊號 DEV-TEST 已核准 → 部位 ... 已開倉
# bot 接著:✅ 所有待處理訊號都處理完了,提早結束監聽。
# script 退出
```

### Backlog (unchanged from v0.1.14.3.5)
- `expire_by_drift` adj_open consistency (deferred from v0.1.14.3)
- `scan_and_exit` modularization (deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (deferred from v0.1.14.3.1)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/`
- Standalone `scripts/run_listener_only.py` (deferred from v0.1.14.3.3)
- (Optional) display-mapping layer for `regime` / `approval_status`
  enum values

---

## [v0.1.14.3.5] — 2026-05-17 — Telegram messages: English → 中文

### Trigger
v0.1.14.3.4 Telegram connectivity smoke succeeded — operator received the
test message on phone. Follow-up request: "Telegram的訊息都改成中文白話文".

Translation patch — content-only. No semantic change, no API change, no
schema change. All Telegram-bound strings rewritten in colloquial Taiwan
finance vernacular.

### Changed (Telegram message text only)

#### `communication/telegram/sender.py`
- `format_entry_request` — full entry-approval card translated:
  - "Entry signal" → "進場訊號"
  - "Signal ID / Score / Px / ATR / Strategy / Regime" →
    "訊號 ID / 分數 / 價 / ATR / 策略 / 市況"
  - "Reasoning" → "理由" (bullet content from `sig.reason` left as-is —
    those are strategy-generated codes, not operator copy)
  - "Risk preview if approved" → "核准後的曝險變化"
  - "Portfolio exposure / Cash buffer / Sector / ETF total" →
    "整體部位 / 現金水位 / 類股 / ETF 總曝險"
  - "(min X% / cap X%)" → "(下限 X% / 上限 X%)"
  - "Drift threshold ... (signal expires if price moves > this)" →
    "漂移門檻 ... (價格偏離超過此值，訊號自動失效)"
  - "Approve before timeout at HH:MM:SS" → "請在 HH:MM:SS 之前回覆"
  - "or" → "或"
- `push_exit_notification` — exit alert:
  - "Exit fired" → "已出場"
  - "Reason / Exit price / Gross return / Net proceeds" →
    "原因 / 出場價 / 毛報酬 / 實收金額"

#### `communication/telegram/listener.py`
- Initial banner — "Helios listener active for N min / N pending: ... /
  Commands: ..." → "Helios 監聽中(N 分鐘) / 目前 N 筆待處理:... / 指令:..."
- Early-exit notice — "All pending signals resolved. Listener exiting early."
  → "所有待處理訊號都處理完了，提早結束監聽。"
- End-of-window — "Listener window ended. Approved: N, Rejected: N.
  Remaining PENDING will expire on next daily_run." →
  "監聽時間結束。已核准:N 筆，已拒絕:N 筆。剩餘待處理訊號將在下一次 daily_run 失效。"
- `/help` response — full command listing translated, terms unified:
  "核准並下單 / 拒絕(不下單) / 列出待處理訊號 / 顯示這則訊息"
- `/status` — "No pending signals." → "目前沒有待處理訊號。" ;
  "Pending signals:" → "待處理訊號:" with row format `score=` → `分數=`,
  `px=` → `價=`
- `/approve` / `/reject` usage strings — "Usage: ..." → "用法:..."
- `/approve` missing-notional error — "Cannot compute notional for X" →
  "無法計算 X 的部位金額(訊號不存在?)"
- Unknown command — "Unknown command X. Send /help." →
  "未知指令 X。請傳 /help 看可用指令。"

#### `execution/approvals.py`
The return-tuple `msg` strings flow up into the listener and get prefixed
with ✅/❌ before `bot.send_message`, so they're operator-facing Telegram
text:
- `approve_signal` returns:
  - "signal not found" → "找不到訊號"
  - "signal X cannot be approved (status=Y)" →
    "訊號 X 無法核准(目前狀態:Y)"
  - "signal X already timed out at HH:MM:SS — marked TIMEOUT" →
    "訊號 X 已逾時(逾時時間 HH:MM:SS) — 已標記為 TIMEOUT"
  - "signal X already handled (race) — current status unknown" →
    "訊號 X 已被處理過(race condition) — 目前狀態不明"
  - "signal X approved but fill failed (see logs)" →
    "訊號 X 已核准但成交失敗(請查 log)"
  - "signal X approved → position Y opened" →
    "訊號 X 已核准 → 部位 Y 已開倉"
- `reject_signal` returns similarly translated
- `_check_atr_drift` returns:
  - "price drifted A > B×ATR=C (X: signal P → fill_open Q)" →
    "價格偏離 A > B×ATR=C (X: 訊號價 P → 開盤價 Q)"
  - "drift OK (...)" → "漂移檢查通過(...)"
  - "no price data for X on DATE — cannot validate drift" →
    "X 在 DATE 無價格資料，無法驗證漂移"
  - "no atr — skip drift check" → "無 ATR 資料，跳過漂移檢查"

#### `execution/shutdown.py`
- Abort Telegram notification (the `⚠️ Helios daily_run aborted (...)` card)
  fully translated:
  - "Helios daily_run aborted" → "Helios daily_run 已中止"
  - "Reason / Error / Pending signals expired / Investigate before next run."
    → "原因 / 錯誤 / 已失效的待處理訊號 / 請先排查後再執行下一次 daily_run。"

### Tests updated
Two test assertions previously matched English substrings in approval messages:
- `test_late_approve_marks_timeout` — `"timed out" in msg.lower()` →
  `"已逾時" in msg`
- `test_drift_gate_uses_adj_open` — `"drifted" in msg.lower()` →
  `"偏離" in msg`

The state-machine-level assertions (e.g. `approval_status == "TIMEOUT"` /
`"EXPIRED_DRIFT"`) are unchanged — those are the binding contract; the
message-substring checks are soft confirmations that the human-facing
message describes the situation.

### NOT translated (deliberate)
- **`daily_run` stdout `[0]..[8]` step labels** — these are operator
  terminal / cron log output, not Telegram. Out of scope for "Telegram
  messages" framing.
- **`sig.reason` bullet content** — strategy-generated identifier strings
  (`"multi-MA aligned"`, `"breakout above 20D high"`, etc.) are not copy,
  they're audit codes the strategy module produces. Translating these
  requires changing the strategy layer, which would be a feature change
  not a localization patch.
- **`regime` enum values** — `bull` / `bear` / `transitional` flow as
  identifier strings through DB, market_regime, exit rules. Display layer
  shows them verbatim. Translating these requires a separate
  display-mapping layer (worth doing in v0.1.15 if operator prefers).
- **`approval_status` values** — `PENDING`, `APPROVED`, `REJECTED`,
  `TIMEOUT`, `EXPIRED_DRIFT` are state-machine identifiers, not copy.
- **DEV-prefixed signal_id namespace** — `DEV-TEST-001` etc. are
  identifiers. Stay English for grep/filter ergonomics.

### Validation
```
ruff check .                              All checks passed
pytest tests/                             47 passed (all green after assertion updates)
```

Preview of translated entry request (rendered with synthetic data):
```
🟢 *進場訊號 — 2330* (semi)
訊號 ID: `abc12345def67890`
分數: 0.82 / 價: 595.00 / ATR: 11.20
策略: trend_breakout_v1 / 市況: bull

理由:
  • multi-MA aligned (close > SMA50 > SMA200)
  • breakout above 20D high
  ...

核准後的曝險變化:
  整體部位:  29.0% → 47.0%
  現金水位:  71.0% → 53.0%  (下限 10%)
  類股 'semi':  9.0% → 27.0%  (上限 30%)

漂移門檻: 0.5×ATR = 5.60 (價格偏離超過此值，訊號自動失效)
請在 12:07:50 之前回覆

`/approve abc12345`  或  `/reject abc12345`
```

### Deploy (additive — no DB / config / behavior change)
```bash
scp ~/Downloads/helios-v0.1.14.3.5.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.5.zip && cd helios && uv sync

# Optional: connectivity re-smoke (now in Chinese)
uv run python -c "
from communication.telegram import TelegramBot, TelegramConfig
bot = TelegramBot(TelegramConfig.from_env())
bot.send_message('Helios v0.1.14.3.5 — 中文訊息上線')
"

# Real test: push a dev signal and observe the entry-request format
uv run python scripts/dev_push_signal.py --ticker 2330 --price 950
# 手機應收到「🟢 進場訊號 — 2330」開頭的中文卡片
```

### Backlog (unchanged from v0.1.14.3.4)
- `expire_by_drift` adj_open consistency (deferred from v0.1.14.3)
- `scan_and_exit` modularization (deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (deferred from v0.1.14.3.1)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/`
- Standalone `scripts/run_listener_only.py` (deferred from v0.1.14.3.3)
- (Optional) display-mapping layer for `regime` / `approval_status`
  enum values — would let those terms also appear in Chinese in operator
  notifications, while keeping the DB / code identifiers in English.

---

## [v0.1.14.3.4] — 2026-05-17 — Secrets hardening + config-naming alignment

### Trigger
Two independent findings surfaced during v0.1.14.3.3 nexus deploy + Telegram
setup:

1. **`HELIOS_TELEGRAM_*` vs `TELEGRAM_*` naming inconsistency.** Operator
   followed `.env.example` (canonical schema: `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, no prefix) yet daily_run perpetually printed
   `listener skipped (no_telegram)`. Diagnostic showed `Settings.telegram_bot_token`
   loaded correctly while `TelegramConfig.from_env()` returned None — they
   read different env vars.
   - `Settings` (pydantic-settings, the canonical contract) reads
     `TELEGRAM_BOT_TOKEN`
   - `TelegramConfig.from_env()` (raw `os.environ.get`) read
     `HELIOS_TELEGRAM_BOT_TOKEN`
   Operator-invisible failure. The whole conversation-history Telegram path
   was non-functional since at least v0.1.14.2 — every "listener skipped"
   log line was the symptom, treated as expected.

2. **Plaintext FinMind token in tracebacks.** Inspection of
   `logs/helios.log.2026-05-16` revealed dozens of `download_unexpected_error`
   events whose `exception` field contained the full FinMind URL —
   including `?token=<JWT>` — because:
   - `httpx.HTTPStatusError` formats the request URL into its message
   - That message propagates through `tenacity.retry` retries
   - Final raise reaches `structlog`'s `exc_info` formatter, which captures
     the full traceback
   - JWT bearer credential lands on disk in plaintext

   The leaked JWT decodes to `{"user_id":"kairos","email":"tpephc@gmail.com"}` —
   PII attached. Severity: real. Operator must rotate the FinMind token AFTER
   this hotfix deploys.

Both findings have the same character: **silent operational drift between two
code paths that should encode the same contract**. Different mechanism, same
failure class as the v0.1.14.3.2 producer-consumer plumbing gap.

### Fixed

#### A. `TelegramConfig.from_env` routed through Settings
- `communication/telegram/bot.py`:
  - Removed `import os` + raw `os.environ.get("HELIOS_TELEGRAM_*")` lookups
  - Now imports `get_settings()` and reads `s.telegram_bot_token` /
    `s.telegram_chat_id` — same source as the rest of the codebase
  - `SecretStr` wrapping unwrapped via `.get_secret_value()` defensively
    (works whether Settings returns SecretStr or plain str)
- Module docstring updated to reference `.env.example` as canonical schema
  reference
- **Operator-visible behavior change**: `.env` with `TELEGRAM_BOT_TOKEN=...`
  (no prefix) now works. `HELIOS_`-prefixed names no longer recognized.
  The pydantic-settings env_file mechanism handles `.env` loading
  automatically — `set -a; source .env; set +a` is no longer required.

#### B. FinMind token redaction in URLs
- `data/sources/finmind_client.py`:
  - New module-level helper `_redact_url(url: str) -> str` — regex-based
    redaction of `token=`, `api_key=` / `apikey=`, `secret=`, `password=`
    query parameter values. Pure function, unit-testable. Preserves all
    other URL structure (host, path, non-secret params) for diagnostic
    context.
  - New helper `_raise_finmind_http_error(e: httpx.HTTPStatusError)`:
    catches the httpx exception, builds a redacted message, raises
    `FinMindError` with `from None` to clear `__cause__` AND set
    `__suppress_context__=True` (both required to prevent Python's
    chained-traceback printing from re-leaking the original URL via
    `__context__`)
  - `_get` now wraps `r.raise_for_status()` in a `try/except httpx.HTTPStatusError`
    that delegates to `_raise_finmind_http_error`. Tenacity retry semantics
    preserved because `FinMindError` is in the retry-eligible tuple.

#### Documentation correction
v0.1.14.3.3 CHANGELOG instructed operators to set `HELIOS_TELEGRAM_BOT_TOKEN`
and `HELIOS_TELEGRAM_CHAT_ID`. **Wrong** — those names matched the buggy
code path, not the canonical `.env.example` schema. v0.1.14.3.3 operator-setup
text is hereby superseded by:

```bash
# Correct (canonical .env.example schema, works with v0.1.14.3.4):
cat >> ~/projects/helios/.env <<EOF
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
EOF
chmod 600 ~/projects/helios/.env
# No `set -a; source .env; set +a` needed — Settings reads .env automatically.
```

### Invariants added (6 new in `tests/invariants/test_semantic_invariants.py`)
- `test_telegram_config_loads_from_canonical_dotenv_keys` — `.env` with
  `TELEGRAM_BOT_TOKEN` populates `from_env()` (positive contract)
- `test_telegram_config_does_not_read_helios_prefix` — `HELIOS_TELEGRAM_*`
  env vars DO NOT populate `from_env()` (negative contract; catches
  regression of the pre-v0.1.14.3.4 code path)
- `test_finmind_url_redaction_strips_token` — base case: JWT in `?token=...`
  is stripped
- `test_finmind_url_redaction_catches_multiple_secret_param_names` — also
  redacts `api_key`, `apikey`, `secret`, `password` (defensive against
  future endpoints)
- `test_finmind_url_redaction_passthrough_when_no_secrets` — clean URLs
  pass through unchanged
- `test_finmind_http_error_propagated_exception_does_not_leak_token` —
  end-to-end: HTTPStatusError → FinMindError, asserts no leak in
  `str(exception)`, `__cause__ is None`, `__suppress_context__ is True`

The two negative-half invariants (HELIOS_ prefix; chained-traceback suppression)
are the ones operators most need: they catch the specific way the bug would
return — easy regressions for a future contributor unaware of the history.

### Non-changes
- `Settings` field names (`telegram_bot_token` etc) unchanged
- `.env.example` unchanged (it was always correct; the bug was bot.py)
- No DB / marker / state-machine touches
- Tenacity retry policy unchanged — `FinMindError` was already retry-eligible
- Other call sites that may log secrets (Shioaji future integration) NOT
  retrofitted in this patch; they'll get the same treatment when their code
  lands in v0.1.15. The `_redact_url` helper is reusable when that day comes.

### Validation
```
ruff check .                              All checks passed
pytest tests/                             47 passed (33 + 14 invariants)
                                          (+ 6 v0.1.14.3.4 invariants)
wc -l communication/telegram/bot.py       138  (was 121 — +17 for routed
                                                 from_env + docstring)
wc -l data/sources/finmind_client.py      325  (was 275 — +50 for helpers
                                                 + try/except wrap)
```

Manual end-to-end smoke of redaction (run during patch development):
```python
url with token=eyJ0eXAi...LEAKED_PAYLOAD...
→ _raise_finmind_http_error →
FinMindError("HTTP 400 from FinMind (...?token=***REDACTED***)")
'eyJ0eXAi' in str(exc) → False  ✓
__suppress_context__ → True       ✓
__cause__ → None                  ✓
```

### Deploy (replaces v0.1.14.3.3 partial deploy on nexus)
```bash
scp ~/Downloads/helios-v0.1.14.3.4.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.4.zip && cd helios && uv sync

# Verify .env still has canonical keys (rebuilt in v0.1.14.3.3 → v0.1.14.3.4 transition)
grep -E "^(FINMIND|TELEGRAM)_" .env

# Smoke A — Telegram connectivity (now works WITHOUT set -a; source .env)
uv run python -c "
from communication.telegram import TelegramBot, TelegramConfig
cfg = TelegramConfig.from_env()
print('config:', cfg)
if cfg:
    bot = TelegramBot(cfg)
    msg_id = bot.send_message('Helios v0.1.14.3.4 — connectivity smoke')
    print('msg_id:', msg_id)
"
# Expected: TelegramConfig(...) printed, msg_id integer, phone notification received

# Smoke B — verify redaction by deliberately triggering a 400 (optional)
# After deploy, the next FinMind error of any kind will go through the
# redacting path. Inspect ~/projects/helios/logs/helios.log to confirm
# `token=***REDACTED***` rather than the JWT.

# AFTER smoke A + B succeed:
# 1. Rotate FinMind token at https://finmindtrade.com (revoke leaked one)
# 2. Update .env with new token
# 3. (No `set -a; source .env; set +a` needed)
```

### Security action items (operator)
1. **Rotate FinMind token NOW** — the previous token is in
   `logs/helios.log.2026-05-16` plaintext. Treat as compromised even if
   nexus is private (assume any log might leave the machine).
2. **Optional: rotate `logs/helios.log.2026-05-16`** (delete or shred —
   it still has the old token until manually purged):
   ```bash
   # If you want to keep the structural log but drop the secret
   sed -i 's/token=eyJ[A-Za-z0-9._-]*/token=***REDACTED***/g' logs/helios.log.2026-05-16
   ```

### Backlog (unchanged from v0.1.14.3.3)
- `expire_by_drift` adj_open consistency (deferred from v0.1.14.3)
- `scan_and_exit` modularization (deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (deferred from v0.1.14.3.1)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/`
- Standalone `scripts/run_listener_only.py` (deferred from v0.1.14.3.3)

---

## [v0.1.14.3.3] — 2026-05-17 — Dev signal injection for observation-phase productivity

### Trigger
5-day paper-trade observation window begins with quiet days — strategy
produces 0 signals on most calendar slots (especially near range-bound
markets). The marker / listener / approval / lifecycle paths therefore
go untested in production conditions until a real signal happens to fire,
which may not happen at all within the 5-day window.

Per reviewer ("the best way is not to hard-modify daily_run"): rather than
add `if DEV_MODE` branches inside production paths to force signal
generation, add a separate dev-only tool that **injects** a fake PENDING
signal directly into the DB and pushes via real Telegram. Production code
remains pure; the dev tool is the only entry point that bypasses strategy
evaluation.

### Added

#### `scripts/dev_push_signal.py` — new file (220 lines)
End-to-end operator-interaction test driver. Single process performs:

1. Save PENDING signal to DB with a `DEV-`-prefixed `signal_id`
   (namespace makes dev signals filterable in logs / DB / `run_summary`'s
   signal_flow output)
2. Push via real Telegram using the same `push_entry_request` path as
   production `process_entries`
3. (Optional, default-on) Run `listen_for_approvals` in-process until the
   signal transitions out of PENDING or the listener window elapses
4. Read back final state and print `approval_status`

CLI:
```bash
# Push + listen (default 10-min window)
uv run python scripts/dev_push_signal.py --ticker 2330 --price 950

# Push only — useful for testing the TIMEOUT path
uv run python scripts/dev_push_signal.py --ticker 2330 --no-listener

# Custom id (repeatable scenarios)
uv run python scripts/dev_push_signal.py --signal-id DEV-LATE-001 --listener-minutes 1
```

Filterable markers on every dev-injected signal:
| Field | Value |
|---|---|
| `signal_id` | prefix `DEV-` (e.g. `DEV-TEST-001`) |
| `strategy` | `"dev_injected"` |
| `reason` | `["dev_test"]` |
| `metadata` | `{"dev_test": true, "target_notional": ...}` |

Any of these allow operator to grep dev signals out of marker JSON,
history JSONL, structlog stream, or DB rows.

#### Auto-incrementing namespace id helper
`next_dev_signal_id(prefix="DEV-TEST-")` — scans existing DB signals,
returns next sequential 3-digit-padded id. Exposed as a public function
of `dev_push_signal` so tests pin its behavior independently of the CLI.

### Changed

#### `storage/signals.py::save_signal` — optional `signal_id` kwarg
Default `None` preserves prior behavior (uuid4 auto-generated). When a
caller supplies a string, that value is used as the PK directly. Schema
constraint (PK uniqueness) is the only validation — same as for uuid
collisions, which are effectively zero.

Only consumer of the new kwarg: `dev_push_signal.py`. Production code
paths (`process_entries.py`, lifecycle, tests of real strategy signals)
continue to pass nothing → uuid is generated.

This is a documented exception to "no production-code changes for dev
tooling": the change is purely additive, opt-in, and the kwarg has
plausible future use (test fixtures, data migration, snapshot replay)
beyond `dev_push_signal.py`.

### Non-changes (deliberate scope-lock)
- **No `if DEV_MODE` branches anywhere in production code**. `daily_run`,
  `process_entries`, `approvals`, `lifecycle`, `paper_broker`, `listener`
  all unchanged. A DEV-prefixed signal flows through the exact same code
  as a real signal — the prefix is purely an identifier convention.
- **No marker/history side effects from dev runs**. `dev_push_signal.py`
  does NOT wrap itself in `shutdown_guard`; running it produces no
  marker or history JSONL entry. The signal itself IS persisted in DB
  and visible to `run_summary`'s signal_flow query — sufficient audit
  trail without polluting the daily_run-level operational journal.
- **Listener stays single-source-of-truth**. dev_push_signal runs its
  own in-process listener with a closure-resolved `target_notional_for`
  rather than extending the production listener to read notional from
  signal.metadata as a fallback. The production listener's contract is
  unchanged.
- **No mocking of Telegram**. If `TELEGRAM_*_TOKEN` are unset, the script
  exits 1 with an explanatory message rather than silently no-op or
  proceed with a stub. The whole point is real-Telegram observation.

### Validation
```
ruff check .                              All checks passed
pytest tests/                             41 passed (33 + 8 invariants)
wc -l scripts/daily_run.py                149  (< 150 ceiling, unchanged)
wc -l scripts/dev_push_signal.py          220  (new)
wc -l storage/signals.py                  403  (was 396 — +7 for signal_id kwarg)
```

New tests (in `tests/test_state_machine.py`):
- `test_save_signal_honors_custom_signal_id` — explicit `signal_id="DEV-TEST-001"` round-trips
- `test_save_signal_default_signal_id_is_uuid` — no regression on production caller path
- `test_next_dev_signal_id_starts_at_001` — first dev signal of a prefix
- `test_next_dev_signal_id_increments` — sequential numbering across multiple insertions
- `test_dev_push_signal_exits_when_telegram_not_configured` — clean refusal when env unset

### Operator setup (one-time, on nexus or wherever script runs)
```bash
# 1. Create bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
# 2. Send any message to the bot. Then:
curl https://api.telegram.org/bot<TOKEN>/getUpdates
#    → find "chat":{"id":N} in response

# 3. Add to .env (alongside DB and other config)
echo 'TELEGRAM_BOT_TOKEN=...' >> .env
echo 'TELEGRAM_CHAT_ID=...'   >> .env

# 4. Verify daily_run picks it up — `listener skipped (no_telegram)` should
#    become `listener starting (...)` on the next run with PENDING signals.
```

### Recommended observation-phase usage
```bash
# Day 1: smoke a normal approve flow
uv run python scripts/dev_push_signal.py --ticker 2330 --price 950
# (approve DEV-TEST-001 in Telegram)

# Day 2: smoke the reject flow
uv run python scripts/dev_push_signal.py --ticker 0050 --price 140
# (reject DEV-TEST-002)

# Day 3: smoke the TIMEOUT path
uv run python scripts/dev_push_signal.py --signal-id DEV-TIMEOUT-001 \\
    --listener-minutes 1 --no-listener
# (wait 2 min, then run daily_run or expire_by_timeout — should mark TIMEOUT)

# Day 4: smoke the EXPIRED_DRIFT path
uv run python scripts/dev_push_signal.py --signal-id DEV-DRIFT-001 \\
    --price 950 --atr 1.0
# Then approve — drift gate should reject if next-open is > 0.5 ATR from 950

# Day 5: review with run_summary
uv run python scripts/run_summary.py --days 5
# Expected: signal_flow shows DEV signals across the 4 days, current OPEN
# positions (if any approves succeeded), no repeat-failure scars
```

### Backlog (unchanged from v0.1.14.3.2)
- `expire_by_drift` adj_open consistency (deferred from v0.1.14.3)
- `scan_and_exit` modularization (deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (deferred from v0.1.14.3.1)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/`
- Standalone `scripts/run_listener_only.py` for testing crash-recovery /
  restart scenarios on PENDING signals across processes (current
  `dev_push_signal.py` does push+listen in one process). Not urgent —
  add when observation phase surfaces a need.

---

## [v0.1.14.3.2] — 2026-05-17 — Plumbing hotfix: producer→marker forwarding gap

### Trigger
v0.1.14.3.1 nexus smoke test (operator: cat ~/.helios_last_run.json) revealed
the marker payload's `summary` dict was missing `avg_position_days` and
`max_position_days` — even though `scan_and_exit` correctly computed them
and `test_scan_and_exit_summary_includes_age_aggregates` passed. The aggregates
existed at the producer (scan_and_exit) but never reached the persistence
surface (marker file / history jsonl), so `scripts/run_summary.py` could
never aggregate them across the 5-day observation window.

Root cause: `scripts/daily_run.py::main` forwards a **hardcoded tuple** of
keys from `exit_summary` into `guard.set_summary(...)`. The v0.1.14.3.1 patch
added the aggregates to `scan_and_exit`'s summary but did not extend that
tuple. Net result: aggregates computed, returned, and silently dropped.

This is a distinct class of operational bug:
- Unit tests on the producer pass (scan_and_exit returns correct values)
- daily_run runs to "ok" status (no exception, no log alarm)
- Field is silently dropped between producer and persistence

Indistinguishable from "field never existed" until an operator squints at
marker JSON. Per reviewer: "this is a new invariant type — producer-consumer
operational-metadata contract."

### Fixed

#### Plumbing — `scripts/daily_run.py::main`
Extended the `set_summary` forwarding tuple to include both v0.1.14.3.1
aggregates:
```diff
-            **{k: exit_summary[k] for k in ("exits_failed", "exits_failed_symbols",
-                "skipped_no_data", "skipped_no_data_symbols", "open_position_days")},
+            **{k: exit_summary[k] for k in ("exits_failed", "exits_failed_symbols",
+                "skipped_no_data", "skipped_no_data_symbols", "open_position_days",
+                "avg_position_days", "max_position_days")},
```
daily_run.py: 148 → 149 lines (still under the < 150 ceiling).

#### Rendering — `scripts/run_summary.py::_render_history`
Render `max_position_days` inline in the per-run history line — this is the
actionable scar ("one stuck position hiding in the population"). `avg_position_days`
remains in the JSON payload for downstream query but is **not** rendered in
the CLI output (avg is noisier; max is the operational signal).

History line format becomes:
```
  2026-05-14  ok                    exits=2  approved=3  rejected=0  exits_failed=0  max_open=18d
```
`max_open=Nd` is omitted when no positions are open.

#### Prevention — new invariant test
`tests/invariants/test_semantic_invariants.py::test_scan_and_exit_aggregates_reach_marker_payload`

Strategy: monkeypatches `scan_and_exit` to return a sentinel summary with
distinguishable values for every observability field, drives `daily_run.main`
end-to-end via argv, then asserts each sentinel value reaches the marker
file's summary dict.

Establishes a new invariant category — **producer-consumer operational-metadata
contract** — distinct from the v0.1.14.3.1 fill↔drift semantic invariant.
Together the two categories cover:

| Category | Catches |
|---|---|
| Cross-layer semantic invariant (v0.1.14.3.1) | Same concept, two layers consult different sources → execution / approval split |
| Producer-consumer plumbing invariant (v0.1.14.3.2) | Producer computes correctly, consumer drops field silently → operational metadata gap |

Future scan_and_exit observability fields must extend the `required` dict
in the test — that becomes the contract.

Verification: temporarily reverted the daily_run.py fix and re-ran the
test; it failed with the precise error message:
```
INVARIANT VIOLATED: marker.summary is missing keys
['avg_position_days', 'max_position_days'] that scan_and_exit produced.
```

### Non-changes (deliberate scope-lock per "plumbing hotfix" framing)
- No new fields added to scan_and_exit summary (would be feature creep on
  top of a hotfix)
- No CLI render of `avg_position_days` (kept in JSON only — avoids the
  per-day rollup output becoming noisier than actionable)
- No migration of v0.1.14.3.1 marker files — the missing fields just won't
  appear in historical runs from yesterday's nexus deploy. Forward runs
  carry the full payload.

### Validation
```
ruff check .                              All checks passed
pytest tests/                             36 passed (28 + 8 invariants)
wc -l scripts/daily_run.py                149  (< 150 ceiling)
wc -l scripts/run_summary.py              249  (was 243 — +6 render lines)
wc -l tests/invariants/test_semantic_invariants.py   330  (was 224 — +106 for the
                                                             new invariant + sentinel
                                                             monkeypatch infra)
```

Failing-state verification (test bites the actual bug):
- Temporarily revert daily_run.py forwarding tuple to the v0.1.14.3.1
  broken form → invariant test fails with the diagnostic message above
- Restore fix → 36/36 green

### Deploy (replaces v0.1.14.3.1 partial deploy on nexus)
```bash
scp ~/Downloads/helios-v0.1.14.3.2.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.2.zip && cd helios && uv sync

# Smoke A — same as v0.1.14.3.1: full run, [0]..[8] sequential
uv run python scripts/daily_run.py --as-of 2026-05-14 --no-listener

# Smoke B — rollup; now history line carries max_open=Nd when positions exist
uv run python scripts/run_summary.py --days 5

# Smoke D (new) — confirm marker carries aggregates
cat ~/.helios_last_run.json
# Expect summary to include both:
#   "avg_position_days": <null or float>
#   "max_position_days": <null or int>
```

5-day paper-trade observation window still starts from the first OK run
under v0.1.14.3.2; v0.1.14.3.1's yesterday smoke can be discarded.

### pyproject version-string note
`pyproject.toml` carries `version = "0.1.14.3.post2"` (PEP 440; second
post-release of v0.1.14.3). CHANGELOG header retains `v0.1.14.3.2` for
human-readable continuity. Same convention as `.post1` for v0.1.14.3.1.

### Backlog (unchanged from v0.1.14.3.1)
- `expire_by_drift` adj_open consistency (deferred from v0.1.14.3)
- `scan_and_exit` modularization (deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (deferred from v0.1.14.3.1)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/`

---

## [v0.1.14.3.1] — 2026-05-17 — Semantic hardening patch

### Trigger
Pre-deploy review of v0.1.14.3 (semantic-extension cadence approved as healthy,
but five specific gaps identified before nexus deploy). Patch addresses three
P0 items + two P1 polish items. No state-machine change, no DB migration, no
new modules other than `tests/invariants/`.

Framing per reviewer: "semantic stabilization patch, not feature expansion."

### Fixed

#### P0-A. Semantic-invariant test for fill ↔ drift price-source consistency
- `tests/invariants/test_semantic_invariants.py` — **new file** (224 lines),
  new sub-package `tests/invariants/`. Houses `test_fill_and_drift_gate_share_same_price_source`,
  which asserts: the column the drift gate compares against MUST be the same
  column the broker fills at. The test constructs `adj_open=140.5` and
  `adj_close=142.0` with signal-price 140 / drift-threshold 1.0:
  - Under v0.1.14.3+ adj_open semantic: drift=0.5 < 1.0 → approval passes,
    broker fills at 140.5 → consistent.
  - Under any future regression that splits the two: approval would either
    fail (drift gate reads adj_close→drift 2.0 → reject) or pass+mis-fill
    — either way the assertion catches it.
- Rationale (per reviewer): "this is the most important but yet-uncodified
  invariant. Future reviewers may adjust fill engine, drift guard, intraday
  fill model, or execution abstraction — and only update one side. Unit
  tests still pass, but operational semantics have split. That bug is
  dangerous because it's silent."

#### P0-B. Structured operational metadata in `FillResult`
- `execution/paper_broker.py::FillResult` — two new fields, both with
  back-compat defaults (existing call sites unaffected):
  - `execution_reason: str = "filled"` — positive identifier of what
    happened, not the absence-of-failure that `error` provides. On
    failure, mirrors the reason code. Lets `run_summary` group rejections
    by reason without parsing free-text error strings.
  - `participation_rate: float | None = None` — shares / fill-day raw
    volume, populated on every fill (success AND liquidity rejection)
    when volume is known. Enables threshold tuning ("median rejected
    participation over last 5 days"), sizing pathology analysis
    ("which regime has highest participation"), and breach distribution.
- `_fail` accepts `participation_rate=` kwarg; `_liquidity_check` passes
  the breaching ratio through so the FillResult carries it.
- Logger calls in `paper_buy_filled` / `paper_sell_filled` / `paper_fill_failed`
  now emit `participation_rate=` for structlog-side observability.

#### P0-C. `run_id` in run-ledger payload
- `execution/shutdown.py::ShutdownState` — gained `run_id: str` set at
  construction (12-hex-char uuid4 prefix). Stable for the lifetime of the
  run; written into every marker / history record this run produces (ok,
  declined_preflight, aborted — all three paths).
- `_write_marker` signature: new kw-only `run_id` arg (defaults to `None`
  for back-compat — direct callers who don't supply it still work, just
  no `run_id` field in their payload).
- Logger calls (`run_started`, `shutdown_clean`, `shutdown_declined_preflight`,
  `shutdown_aborted`) now emit `run_id=` so external log analysis (in
  whatever shape it eventually takes) can correlate the marker with the
  run's structlog stream.
- Enables: crash-recovery chain analysis, duplicate-run detection, retry
  chains, same-as_of multiple-executions disambiguation.

#### P1-D. Test rename for semantic accuracy
- `test_t_plus_1_fill_uses_next_day_close` → `test_t_plus_1_fill_uses_next_day_open`.
  Test body unchanged (seed_calendar's `adj_open == adj_close` keeps the
  140.5 assertion valid for "T+1 day" semantic); the rename eliminates
  the misleading "_close" suffix that could lead a future reviewer to
  conclude "execution semantics = close". Column-correctness (adj_open
  vs adj_close on a given day) is covered by the v0.1.14.3
  `test_fill_uses_adj_open_not_adj_close`; together they cover both axes.

#### P1-E. Holding-time aggregates in `scan_and_exit` summary
- `scripts/run_exit_scan.py` — derived from `open_position_days`:
  - `avg_position_days: float | None` — average age of OPEN positions
  - `max_position_days: int | None` — oldest OPEN position's age
- Both `None` when no positions are OPEN (rendering-friendly; run_summary
  prints "(no open positions)"). Surfaces holding-time outliers (one
  60-day position hiding in a population averaging 5 days).

### Non-changes (deliberate scope-lock per "semantic hardening" framing)
- **Approval result dataclass refactor.** `approve_signal` still returns
  `tuple[bool, str, str | None]`. Adding structured `drift_pct` would
  require restructuring that return, which ripples to telegram listener,
  listener_summary aggregations, and the on-the-wire notification text.
  That is approval-contract redesign, not operational-metadata extension.
  Deferred to v0.1.15 (where it will be co-designed with the Shioaji
  result types). The drift message string remains parseable
  (`drifted X > N×ATR=Y`) — sufficient for observation-phase analytics.
- **Shared price-source helper module.** No `execution/price_lookup.py`
  introduced. The duplication is shallow (one SQL line each), stable
  (adj_open in both places), and visible (operator can grep `adj_open`
  and see exactly two callers). The new invariant test pins the contract
  without hiding the semantic behind an abstraction.
- **Schema, calendar, state machine, lifecycle** — all untouched, as in
  v0.1.14.3.

### tests/invariants/ pattern
This patch establishes a new test sub-package. Convention:
- `tests/test_*.py` — feature correctness ("is feature X correct?")
- `tests/invariants/test_*.py` — semantic invariants ("is the system's
  internal world view consistent?")

Maintenance cost differs: a feature test changes with its feature, but
an invariant test changes only when a system semantic changes deliberately.
Mixing them in one file makes it too easy to "fix" an invariant test by
mirroring whatever the implementation now does — silently approving the
drift. Separation forces the change to be intentional.

Initial population (7 tests in `test_semantic_invariants.py`):
- `test_fill_and_drift_gate_share_same_price_source` — the P0-A invariant
- `test_fill_result_carries_execution_reason_on_success/_on_failure`
- `test_fill_result_carries_participation_rate_on_liquidity_breach/_on_success`
- `test_run_id_persists_across_marker_and_history`
- `test_run_id_unique_per_run`

Future tests likely to belong here:
- idempotency invariants (re-run same `as_of` produces same state)
- temporal invariants (signal_date vs fill_date vs as_of relationships)
- marker invariants (status transitions monotonic per run)

### Validation
```
ruff check .                              All checks passed
pytest tests/                             35 passed
                                          (28 in test_state_machine.py +
                                          7 in tests/invariants/)
wc -l scripts/daily_run.py                148  (< 150 ceiling, unchanged)
wc -l execution/paper_broker.py           358  (was 340 — FillResult fields +
                                                participation_rate plumbing)
wc -l execution/shutdown.py               345  (was 318 — run_id threading)
wc -l scripts/run_exit_scan.py            292  (was 280 — age aggregates)
wc -l tests/invariants/test_semantic_invariants.py   224  (new)
```

### Test isolation note (unchanged from v0.1.14.3)
`tests/conftest.py::isolated_marker` fixture covers both `MARKER_PATH` and
`HISTORY_PATH`. New invariant tests using `shutdown_guard` use this fixture.

### Deploy (replaces unsent v0.1.14.3 zip)
```bash
scp ~/Downloads/helios-v0.1.14.3.1.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.1.zip && cd helios && uv sync

# Smoke A — same as c3: full run, expect [0]..[8] sequential
uv run python scripts/daily_run.py --as-of 2026-05-14 --no-listener

# Smoke B — rollup; first run will show 1 history entry with a run_id
uv run python scripts/run_summary.py --days 5

# Smoke C — verify marker carries run_id
cat ~/.helios_last_run.json | python -c "import json,sys; m=json.load(sys.stdin); print('run_id:', m.get('run_id'))"
```

### pyproject version-string note
`pyproject.toml` carries `version = "0.1.14.3.post1"` (PEP 440; `0.1.14.3.1`
is not valid PEP 440 — fourth segment must be the post/dev/rc suffix).
CHANGELOG header and zip filename retain `v0.1.14.3.1` for human-readable
patch-number continuity. Same convention as `0.1.14.2-c3.post1` for
v0.1.14.2-c3.1.

### Backlog (recorded, deliberately not fixed in v0.1.14.3.1)
- `expire_by_drift` adj_open consistency (still deferred from v0.1.14.3)
- `scan_and_exit` modularization (still deferred from v0.1.14.3)
- HISTORY_PATH log rotation (operational, not functional)
- Approval result dataclass refactor (see Non-changes above)
- Migration of existing invariant-flavored tests in `test_state_machine.py`
  into `tests/invariants/` (e.g. `test_cross_day_idempotency_under_clock_drift`,
  `test_fill_uses_adj_open_not_adj_close`). Deliberately NOT migrated now —
  test churn for no semantic gain; let new invariant tests land in the new
  location and reclassify retroactively when there's a natural review trigger.

---

## [v0.1.14.3] — 2026-05-17 — Fill realism + liquidity sanity + 5-day stability instrumentation

### Trigger
v0.1.14.1.3 review graded the system **B**, with one explicit gating bar:
"only fixable by 5 consecutive trading days of paper-trade observation,
not by another code review". v0.1.14.3 does the minimum implementation
work that observation period requires:

1. **Fill realism** — the prior `FILL_MODEL="adj_close"` was a deliberate
   proxy when the dividend-adjusted open price wasn't yet in DB. Code
   archeology during scoping showed `daily_price_adj.adj_open` has in
   fact been populated since v0.1.4 (`features/dividend_adjustment.py`),
   so the proxy was stale — fixing it is a 1-line SQL change, not a
   schema migration.
2. **Liquidity sanity** — without a fill-side volume gate, a stress-test
   capital level (3× the default 1M NTD) on a thinly-traded name could
   produce a "filled" trade that no real broker would honor. Paper-trade
   "successful" fills would mask this.
3. **5-day stability instrumentation** — without per-symbol failure
   tracking across runs, a single-day green pytest run gives no signal
   about "this symbol's exit has failed 3 days in a row". That class of
   scar is exactly what the 5-day observation window is meant to surface.

### Fixed

#### A. Fill realism (adj_close → adj_open)
- `execution/paper_broker.py`:
  - `FILL_MODEL = "next_open"` (was `"adj_close"` — constant didn't match
    docstring; both now say next-day open)
  - `_lookup_price` → `_lookup_fill_data`, now returns `(adj_open, volume)`
    tuple instead of single price; SQL switched to `SELECT adj_open, volume`
  - Stale comment "we don't have open price in DB" removed from docstring;
    replaced with explicit note that adj_open has been schema-resident
    since v0.1.4
- `execution/approvals.py`:
  - `_check_atr_drift` reads `adj_open[fill_date]` (was `adj_close`).
    Drift is now `|adj_open[fill_date] - signal.price|` — the operationally
    relevant gap between signal-time close and would-be fill-time open.
  - Drift-rejection message phrasing: "signal → fill_open" (was "signal → now")

#### B. Liquidity sanity (paper-trade safety rail)
- `execution/paper_broker.py`:
  - New class constant `MAX_FILL_RATIO = 0.005` (0.5% of fill-day raw volume)
  - New helper `_liquidity_check(symbol, fill_date, shares, volume, side, signal_id)`:
    - `volume <= 0` → fail with reason `"no_volume_data"`
    - `shares / volume > MAX_FILL_RATIO` → fail with reason `"insufficient_liquidity"`,
      structured log at warning level for offline analysis
  - `submit_buy`: gate runs AFTER share count is computed from target_notional
  - `submit_sell`: gate runs BEFORE fill_price computation (shares known up front)
  - On rejection, returns `FillResult(success=False)` via existing `_fail`
    path — no new state, no DB write, no order row

#### C. Stability instrumentation (5-day rollup observability)
- `execution/shutdown.py` — additive only, no decision-logic change:
  - New `HISTORY_PATH = Path.home() / ".helios_run_history.jsonl"`
  - New `_append_history(payload)` called inside `_write_marker` — best-effort,
    never raises (try/except OSError → log warning)
  - New `read_history(n=5)` helper for the rollup consumer
  - `check_previous_run` UNCHANGED — still reads `MARKER_PATH` only; the
    state-machine contract for "is the previous run clean?" continues to
    depend solely on the single most-recent marker
- `scripts/run_exit_scan.py::scan_and_exit` summary now carries three new
  per-run fields (counters only — no state-machine touch):
  - `open_position_days: list[{position_id, symbol, age_days}]` — every
    OPEN position scanned this run, with age. Surfaces stuck-OPEN positions.
  - `exits_failed_symbols: list[str]` — symbols whose exit rule fired
    this run but whose fill failed at the broker. Cross-run aggregation
    in `run_summary` detects "same symbol failing N days in a row".
  - `skipped_no_data_symbols: list[str]` — parallel to the existing
    `skipped_no_data` count, but with symbol identity preserved for the
    rollup.
- `scripts/daily_run.py` — `guard.set_summary` now forwards the three new
  fields plus `exits_failed` into the marker payload via dict-unpack
  (kept under the 150-line ceiling at 148 lines)
- `scripts/run_summary.py` — **new file** (243 lines). Read-only rollup
  reporter, safe to run ad-hoc at any time:
  - CLI: `python scripts/run_summary.py [--days N] [--as-of YYYY-MM-DD]`
  - Aggregation helpers (pure, unit-testable, separated from rendering):
    - `compute_failure_streaks(history)` — symbol → consecutive failure
      streak ending in the most recent `status="ok"` run. Non-ok runs
      (declined_preflight, aborted) are skipped, NOT treated as recovery
      — a holiday shouldn't reset a real failure scar.
    - `query_signal_flow(since)`, `query_order_flow(since)`,
      `query_open_positions(as_of)` — DB queries (read_only)
  - Output sections: run history (last N from JSONL) / signal flow per
    approval_status / order flow per side+status / current OPEN positions
    with age / repeat-failure scars / latest marker

#### D. Deferred from this version
- **`exit_engine.py` refactor / scan_and_exit modularization** — scan_and_exit
  is now 280 lines (was 218). Already a refactor candidate before this version;
  v0.1.14.3 declined to combine refactor with semantic change. Tracked under
  v0.1.15 Planned.
- **`execution/expiry.py::expire_by_drift`** — also reads `adj_close[as_of]`
  for its drift comparison. This is a *coarser* pre-approval staleness
  filter (runs at daily_run Step 4, before approval) and is operationally
  narrow (only fires for carry-over PENDING signals — rare under 30-min
  timeout). Discovered during implementation; deliberately NOT changed in
  v0.1.14.3 because it falls outside the approved scope. Approval-time
  drift gate (`approvals._check_atr_drift`) IS switched to adj_open and is
  the operationally relevant gate. Documented in `approvals.py` docstring.
  Revisit if reviewer wants full semantic consistency.

### Non-changes (deliberate scope-lock)
- Schema, calendar API (`market.trading_calendar`), state machine (signals
  / positions / approval lifecycle), `run_exit_scan._lookup_today` (kept
  reading adj_close — decision-time semantic is correctly close[T], distinct
  from fill-time which is open[T+1])
- `scripts/process_entries.py:72` mark-to-market valuation (correctly uses
  latest adj_close — that's equity valuation, not fill price)

### Validation
```
ruff check .                              All checks passed
pytest tests/                             26 passed (16 baseline + 10 new)
wc -l scripts/daily_run.py                148  (< 150 ceiling, same as c3)
wc -l scripts/run_summary.py              243  (new file)
wc -l execution/paper_broker.py           340  (was 270 — fill_data tuple +
                                                liquidity helper + docstring
                                                cleanup)
wc -l scripts/run_exit_scan.py            280  (was 218 — stability counters)
```

New tests:
- `test_fill_uses_adj_open_not_adj_close` — distinct adj_open=140 / adj_close=145,
  assert ref_price ≈ 140
- `test_drift_gate_uses_adj_open` — adj_open drift > threshold while adj_close
  drift < threshold; pre-v0.1.14.3 path would have approved, must now reject
- `test_liquidity_check_blocks_oversized_buy` — volume=10k, target=50k @ 1.0
  → shares ≈ 50k, ratio ≫ 0.5% → fail with `error == "insufficient_liquidity"`
- `test_liquidity_check_allows_normal_buy` — volume=1M, ≈500 shares → 0.05% pass
- `test_liquidity_check_blocks_oversized_sell` — symmetric guard for sell side
- `test_scan_and_exit_reports_open_position_ages` — summary["open_position_days"]
  populated with age_days ≥ 3 (entry at seed_calendar[0], as_of at [3])
- `test_scan_and_exit_reports_failed_symbols` — bear regime + missing fill-day
  data → exit fires but fill fails → symbol in exits_failed_symbols
- `test_run_summary_compute_failure_streaks_basic` — declined_preflight
  doesn't break streak; symbol failing in 3 of 4 ok runs → streak == 3
- `test_run_summary_compute_failure_streaks_recovery` — symbol absent in
  most recent ok run → not in streaks output
- `test_run_summary_history_round_trip` — shutdown_guard writes HISTORY_PATH,
  read_history reads back, compute_failure_streaks aggregates correctly

Existing 16 baseline tests unchanged (`seed_price` gained optional
`open_price` and `volume` kwargs that default to prior literal values,
preserving backward compatibility).

### Test isolation note
`tests/conftest.py::isolated_marker` fixture extended to also override
`HISTORY_PATH`, so shutdown_guard-using tests don't pollute the operator's
real `~/.helios_run_history.jsonl`. Important: any future test that calls
`shutdown_guard` directly must use this fixture.

### Deploy (full deploy on nexus — replaces v0.1.14.2-c3.1)
```bash
scp ~/Downloads/helios-v0.1.14.3.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.3.zip && cd helios && uv sync

# Smoke A — same as c3: full run, expect [0]..[8] sequential
uv run python scripts/daily_run.py --as-of 2026-05-14 --no-listener

# Smoke B — new: confirm history append + rollup output
uv run python scripts/run_summary.py --days 5

# Expected on first run: history has 1 entry (today's smoke A), no repeat
# failures yet, current OPEN positions listed if any
```

### Operational behavior changes worth flagging
1. **Fill prices will differ from prior runs.** Any historical paper-trade
   numbers from v0.1.14.2 or earlier used adj_close[T+1]; v0.1.14.3 uses
   adj_open[T+1]. For backtest comparisons across versions, re-run from
   v0.1.14.3 for apples-to-apples.
2. **Some previously-"successful" fills will now fail.** Specifically:
   sells of 100+ shares against names with fill-day volume < 20k shares,
   or buys whose share count exceeds 0.5% of fill-day volume. These are
   *correct* rejections; they would have failed at a real broker too.
3. **`~/.helios_run_history.jsonl` will grow unboundedly.** No rotation
   yet — file is jsonl, easy to truncate manually. ~200 bytes per run,
   so ~70KB/year. Not urgent.

### Backlog (recorded, deliberately not fixed in v0.1.14.3)
- `expire_by_drift` semantic consistency with new fill model (see D above)
- `scan_and_exit` modularization (see D above)
- HISTORY_PATH log rotation (operational, not functional)
- ADV-based liquidity check (v0.1.15 will replace the volume-of-fill-day
  heuristic with proper average-daily-volume from the broker API)

---

## [v0.1.14.2-c3.1] — 2026-05-17 — Cosmetic: daily_run step labels

### Trigger
Nexus smoke test of v0.1.14.2-c3 functioned correctly but stdout showed
mis-numbered step labels: `[5] exit scan` followed by `[5] entry pipeline`
(both 5), then `[6] listener`, `[7] reconciliation` — labels frozen at
pre-c3 numbering. c3's step reorder (calendar-aware `is_trading_day`
promoted to Step 1) shifted subsequent steps by +1, but the rewrite
only updated Steps 0–5 print labels and missed 6–8.

### Fixed
- `scripts/daily_run.py` — three print labels + matching section comments:
  - `[5] entry pipeline` → `[6]`
  - `[6] listener {starting,approved,skipped}` → `[7]` (×3)
  - `[7] reconciliation` → `[8]`

### Non-changes (deliberate scope-lock)
- Schema, calendar, state machine, lifecycle, tests, version naming
  convention, PEP 440 normalization quirk (`-c3` → `rc3` by hatchling)
  — all untouched. `git diff v0.1.14.2-c3..v0.1.14.2-c3.1 --stat` should
  show changes to two files only: `scripts/daily_run.py` and the version
  string in `pyproject.toml` (plus this CHANGELOG entry).

### Validation
```
ruff check .                  All checks passed
pytest tests/                 16 passed
wc -l scripts/daily_run.py    148  (< 150)
```

### pyproject version-string note
`pyproject.toml` carries `version = "0.1.14.2-c3.post1"` (PEP 440 valid;
normalizes to `helios==0.1.14.2rc3.post1` on install) while this CHANGELOG
header and the zip filename retain `c3.1` for human-readable continuity.
This is the post-release form of c3, semantically equivalent to "c3.1"
in our patch-series convention. Caught when ruff RUF200 rejected the
naive `c3.1` form (no PEP 440 continuation rule after `-c3`).

### Deploy (cosmetic re-deploy on nexus)
```bash
scp ~/Downloads/helios-v0.1.14.2-c3.1.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -oq helios-v0.1.14.2-c3.1.zip && cd helios && uv sync
# Re-run smoke A to confirm labels: should see [0]..[8] sequential, no repeats
uv run python scripts/daily_run.py --as-of 2026-05-14 --no-listener
```
No schema/state side effects vs c3 — DB and marker can stay as they are.

### Backlog (recorded, deliberately not fixed)
- PEP 440 `-c3` → `rc3` normalization in `helios==<v>` console output.
  Cosmetic, no functional impact. Renaming `c2/c3/c3.1` → `rc2/rc3/rc3.1`
  in CHANGELOG / git tags / deploy docs would inflate scope unbounded
  for zero operator benefit. Revisit only if it actively confuses an
  operator (none reported so far).

---

## [v0.1.14.2-c3] — 2026-05-17 — Temporal semantics + calendar consolidation

### Trigger
Reviewer second-pass review of v0.1.14.2-c2 plus nexus smoke-test findings.
Reviewer identified two architecture-level contract bugs; smoke test
exposed a third (marker cascade). c2 was correctly diagnosed by reviewer
as "still not release-ready" — c3 is the release-readiness stabilization.

c3 is positioned (per user direction) as the **temporal-semantics
stabilization release** that closes out the v0.1.14.x line before any
operational scars work in v0.1.14.3.

### Fixed — P0 (architecture-level)

- **P0-2 signal_date / created_at split (temporal semantics)** — the
  `signals` table had only `timestamp` (system insertion time, written
  with `datetime.now()`), and `_has_active_signal_for` (the P1-8
  idempotency check from -c) compared it via `CAST(timestamp AS DATE)`
  with the caller's `signal_date` parameter. This only worked when the
  insertion day happened to equal `as_of`. For catch-up runs, weekend
  reruns, backtest replays, or any case where the system clock differs
  from the trading day being processed, the duplicate check silently
  missed prior signals and produced duplicates.

  Fix:
  - `signals` table now has `signal_date DATE NOT NULL` (market semantic)
    AND `created_at TIMESTAMP NOT NULL` (system insertion), as separate
    columns. Indexed both, plus a composite idempotency index on
    `(symbol, strategy, signal_type, signal_date, approval_status)`.
  - `save_signal()` now requires a `signal_date` keyword argument.
  - `_has_active_signal_for` queries the `signal_date` column directly,
    no `CAST` involved.
  - All call sites updated: `process_entries` (×2), `generate_signals`,
    `validate_install` (×2), signals.py smoke test.
  - The reviewer's framing on this one: "市場語意時間 vs 系統執行時間
    不能混用". c3 commits to that distinction architecturally.

- **P0-3 calendar consolidation (single source of truth)** — two
  `next_trading_day` implementations had coexisted: `execution.shutdown`
  (data-based — queried `daily_price_adj`) and `market.trading_calendar`
  (calendar-based — weekday + holiday rules + DB hybrid). Same name,
  different contracts. c2 CHANGELOG had flagged this for v0.2; reviewer
  correctly insisted it be fixed before release-readiness.

  Fix:
  - `execution.shutdown` no longer defines `is_trading_day` or
    `next_trading_day`. Both removed; `execution/__init__.py` no longer
    re-exports them.
  - `market.trading_calendar` is now the single source. Added a new
    function `next_fillable_day(d)` that composes calendar truth +
    data availability: returns the calendar-next trading day only if
    its `daily_price_adj` row exists, else None.
  - `check_data_freshness` and `daily_run.py`, `run_exit_scan.py` all
    import calendar functions from `market`, not `execution`.

  This split is the user's contribution beyond the reviewer's framing:
  the reviewer asked for consolidation, the user pointed out that
  "calendar truth" and "data availability" are TWO different concerns
  that should be exposed as two functions, not silently bundled into
  one. c3 honors that distinction.

### Fixed — Bug 1 (from c2 nexus smoke test)

- **Marker cascade** — preflight failures (Step 0/1/4) used `raise
  RuntimeError`, which `shutdown_guard` caught uniformly and recorded
  as `status="aborted"` in the marker file. The next run's prev-check
  refused to proceed, AND wrote a fresh "aborted" marker itself,
  creating a self-perpetuating block: every run aborts because the
  previous run aborted, forever. Manually deleting the marker once
  didn't help — the first declined run after that re-created it.

  Fix:
  - New exception class `execution.PreflightDecline` (intentionally
    NOT `*Error` suffix; deliberate N818 violation, see docstring).
    Signals a "controlled refusal to start", semantically distinct from
    a mid-pipeline crash. Like stdlib `KeyboardInterrupt` / `SystemExit`,
    it's a control-flow event, not a failure.
  - `shutdown_guard` catches `PreflightDecline` separately: writes
    `status="declined_preflight"` (not "aborted"), no abort cleanup
    (no signal expiry, no telegram crash notification), prints a clean
    one-line message to stderr, raises `SystemExit(1)`. No Python
    traceback in operator output.
  - `check_previous_run` treats `declined_preflight` as proceed-safe:
    a preflight decline by definition made no side effects (didn't
    enter the pipeline body), so there's nothing for an operator to
    investigate. Only `aborted` (true mid-run crash) blocks the next
    run.
  - `daily_run.py` Steps 0/1/2/3 all raise `PreflightDecline` (not
    `RuntimeError`) on controlled refusal.

### Fixed — P1 (step reorder, comes free with P0-3)

- **`daily_run.py` step order** — was `1=freshness, 2=trading_day`. A
  Sunday `--as-of` failed Step 1 with "data stale" instead of Step 2
  with "non-trading day", because `is_trading_day` was data-based and
  the Sunday had no row. With calendar consolidated (P0-3), `is_trading_day`
  is now data-free (weekday + holiday check), so it can run first and
  cheaply reject non-trading-day inputs.

  New order: `0=prev_check → 1=is_trading_day → 2=T+1_readiness →
  3=freshness → 4=expire → 5=exits → 6=entries → 7=listener → 8=reconcile`.

### Schema migration (breaking — no backwards compat)

Per user direction (no production data exists at this stage),
`init_schema()` detects pre-c3 `signals` table (missing `signal_date`
column) and drops + recreates it. Existing paper-trading signals on
nexus will be lost on first c3 run. This is acceptable: pre-c3
signals had unreliable idempotency anyway.

Deploy on nexus:
```bash
scp ~/Downloads/helios-v0.1.14.2-c3.zip tradeagent@nexus:~/projects/
ssh tradeagent@nexus
cd ~/projects && unzip -q helios-v0.1.14.2-c3.zip && cd helios && uv sync
rm -f ~/.helios_last_run.json   # clear stale c2 cascade marker
uv run pytest tests/ -v          # 16 passing
uv run python scripts/daily_run.py --as-of 2026-05-14 --no-listener
uv run python scripts/daily_run.py --as-of 2026-05-15 --no-listener
# Expected: 5/14 runs end-to-end. 5/15 declines cleanly at Step 2
# (t_plus_1_fill_unavailable), no traceback, marker = declined_preflight,
# next run does NOT cascade-block.
```

### Added — tests (12 → 16)

- `test_cross_day_idempotency_under_clock_drift` — P0-2 acceptance.
  Saves a signal with `datetime.now()` monkey-patched to one day,
  then queries with the original `signal_date` from a different
  monkey-patched day. Asserts the duplicate is found despite
  `created_at::date != signal_date`. This is exactly the bug pre-c3
  had; the test would fail against any reversion.
- `test_calendar_vs_fillable_day_split` — P0-3 acceptance. With data
  through 5/15 but not 5/18, asserts `next_trading_day(5/15) ==
  date(2026,5,18)` (calendar truth) AND `next_fillable_day(5/15) is
  None` (data unavailable). After ingesting 5/18, both agree.
- `test_preflight_decline_does_not_cascade` — Bug 1 acceptance.
  Triggers `PreflightDecline` inside `shutdown_guard`, asserts
  `SystemExit(1)`, marker `status="declined_preflight"`,
  `check_previous_run` for next-day proceeds OK with "no side effects"
  language. The cascade trace from c2's nexus output is structurally
  impossible after this fix.
- `test_is_trading_day_calendar_correctness` — calendar sanity.
  Sundays/Saturdays/Labor-Day-2026 are not trading days; post-holiday
  Mondays are. Defends against future calendar regressions.

### Test fixture migration

`seed_calendar` (in `tests/conftest.py`) was previously seeded 10
consecutive *calendar* days starting 2026-05-01. Under c3's
calendar-aware `is_trading_day`, that fixture would have included
Saturday/Sunday and Labor Day as "trading days" (since the old fixture
seeded `daily_price_adj` for those days, the data-based old logic
accepted them). The c3 calendar correctly rejects them. Fixture
updated to step via `market.trading_calendar.next_trading_day`,
starting Mon 2026-05-04 (post-Labor-Day, no nearby holidays).

### Validation

```
ruff check .                  All checks passed
pytest tests/                 16 passed
wc -l scripts/daily_run.py    148  (< 150 ceiling)
```

### Deferred to v0.1.14.3 (not c3 scope, deliberately)

- `execution/exit_engine.py` refactor of run_exit_scan.py orchestration
  body (P1 from reviewer second pass; architectural cleanup, not a bug)
- Fill realism (next-day-open vs adj_close)
- 5-day operational stability run
- Slippage / partial fill / reconciliation completion

Reviewer's framing: "v0.1.14.x 在這版才算真正封口". The temporal-semantics
and calendar-semantics work were the prerequisites; v0.1.14.3's
operational scars accumulation can now proceed against stable
foundations.

---

## [v0.1.14.2-c2] — 2026-05-17 — Hotfix: T+1 freshness contract gap

### Trigger
Nexus smoke test of v0.1.14.2-c (`scripts/daily_run.py --as-of 2026-05-15
--no-listener`) on 2026-05-17 (Sun, market closed). All 11 unit tests passed,
but the pipeline aborted mid-run with an unhandled `RuntimeError` traceback at
Step 4. Investigation revealed a **contract mismatch** introduced by -c's P0-2
fix, not exposed by the unit tests because no test ran the daily pipeline at
its `latest == as_of` boundary.

### Root cause
P0-2 changed fill semantics from same-day to T+1, implemented via
`execution.next_trading_day(as_of)` which queries `daily_price_adj` for the
next row strictly after `as_of`. This implicitly raised the data-freshness
requirement from `latest >= as_of` (signal-day data) to `latest >= T+1`
(fill-day data). But `check_data_freshness` was not updated, so:

```
Step 1 freshness:   latest >= as_of   → passed (latest == as_of)
Step 4 T+1 fill:    latest >  as_of   → next_trading_day() returned None → raise
```

Result: opaque traceback at line 94 of `daily_run.py`, after side effects
from Steps 0–3 already executed. Violates Helios §9 principle that errors
must be **early, clean, and explainable**.

### Fix
- `execution/shutdown.py` `check_data_freshness` now additionally calls
  `next_trading_day(as_of)` and returns a controlled-abort message
  `data_not_ready_for_t_plus_1_fill: as_of=<d> latest=<d>` when it returns
  None. Step 1 is now the single gate for both the signal-day and fill-day
  data requirements.
- `scripts/daily_run.py` Step-4 raise reworded to `invariant: ...` and
  marked `# pragma: no cover` since Step 1 is now authoritative. Kept as
  belt-and-suspenders per Helios defensive culture.

### Added
- `tests/test_state_machine.py::test_freshness_blocks_when_no_t_plus_1_data`
  — covers the `latest == as_of` boundary that the smoke test exposed.
  Asserts controlled-abort (not raise), correct error string, and that the
  symmetric `latest > as_of` case (T+1 data present) still passes with a
  message identifying the covered T+1 fill day.

### Validation
```
ruff check .                  All checks passed
pytest tests/                 12 passed (11 from -c + 1 new boundary test)
wc -l scripts/daily_run.py    149  (< 150 ceiling)
```

### Smoke test contract (post-c2)
With nexus data fresh through 2026-05-15:
- `--as-of 2026-05-14` → Step 1 OK (T+1=2026-05-15 covered), pipeline runs
- `--as-of 2026-05-15` → Step 1 controlled abort with `data_not_ready_for_t_plus_1_fill`,
  exit non-zero, no traceback, no partial side effects past Step 1

### Note for v0.1.14.3 backlog
Two follow-ups arising from this hotfix, deferred (not blockers):
1. The two `next_trading_day` implementations (`execution.shutdown` data-based,
   `market.trading_calendar` calendar-based) should converge on a single
   authoritative API in v0.2 once TWSE official calendar lands.
2. `shutdown_guard` should special-case `data_not_ready_for_t_plus_1_fill` so
   the marker records `skipped` not `failed` (since it's a data-freshness
   skip, not a system error). Out of scope for c2 to keep change surface tight.

---

## [v0.1.14.2-c] — 2026-05-17 — Hotfix: 8 P0/P1 issues from reviewer second pass

### Reviewer verdict triggering this hotfix
v0.1.14.2-b received **B-** rating. Verdict: "尚未可進入 5 日穩定 paper trading".
Reviewer identified 4 P0 (must-fix) + 4 P1 (should-fix) issues. All 8 addressed
in this version before any operational deployment.

### Fixed — P0 (security / correctness / honesty)

- **P0-1 chat_id validation (security)** — `communication/telegram/listener.py`
  added authorization gate in poll dispatch loop. Without this, any user who
  guesses the bot username could `/approve` trades. Now: incoming messages from
  unauthorized chat_id are logged + tracked in `summary["ignored"]` with reason
  `unauthorized_chat:{id}`, dispatcher is bypassed entirely.

- **P0-2 T+1 fill semantics (correctness)** — added `execution.next_trading_day()`
  helper; threaded fill_date through `daily_run.py` → `listener` → `approvals`
  → `paper_broker`. Previously: signal generated using day-T close was filled
  at day-T adj_close, conflating signal/fill instants. Now: fill date strictly
  > signal date (T+1 close proxy until intraday data exists in v0.1.14.3).
  - `scripts/daily_run.py` Step 4 computes `fill_date = next_trading_day(as_of)`;
    aborts if no T+1 data available (better than degraded fill).
  - `scripts/run_exit_scan.py:scan_and_exit()` signature now accepts `fill_date`
    parameter; defaults to `as_of` for backward compatibility.
  - `scripts/run_exit_scan.py` CLI gains `--fill-date` override.

- **P0-3 Telegram push failure handling (correctness)** —
  `scripts/process_entries.py:generate_pending_signals()` now checks `msg_id`
  return from `push_entry_request()`. If push fails (`None`), signal is
  immediately transitioned to `TIMEOUT` with `expired_reason='telegram_push_failed'`
  and NOT included in returned `pending_ids`. Per §9 escalation: "missed signal
  > wrong trade" — operator who didn't see the signal can't approve it.

- **P0-4 pytest suite committed to repo (honesty)** — `tests/` directory created:
  - `tests/__init__.py`
  - `tests/conftest.py` — `tmp_db` fixture (per-test isolated DuckDB via Settings
    injection), `seed_price()` / `seed_calendar` fixtures for synthetic price
    data, `MockTelegramBot` class (records send_message + queues get_updates)
  - `tests/test_state_machine.py` — 11 tests covering all 8 P0/P1 + 2 negative
    cases. **All 11 passing.**
  - v0.1.14.2-b's claim "unit path covered" now backed by actual repo tests.

### Fixed — P1 (correctness / cleanliness)

- **P1-5 late /approve transitions inline** — `execution/approvals.py:approve_signal()`
  when `timeout_at < now`: now calls `update_approval(... TIMEOUT, "late_approval_after_timeout")`
  inline instead of just returning False. Previously the signal stayed PENDING
  until the next daily_run's `expire_by_timeout` swept it.

- **P1-6 update_approval return value honored** — `approve_signal` and
  `reject_signal` now check the atomic UPDATE return; if `False` (someone else
  already transitioned this signal — race condition), bail with race-safe message.
  Previously the return value was ignored, hiding race-condition edges.

- **P1-7 exit scan uses lifecycle (single source of truth)** —
  `scripts/run_exit_scan.py:scan_and_exit()` refactored to delegate position
  closure to `execution.lifecycle.close_position_for_exit()` instead of inline
  `broker.submit_sell()` + `mark_position_closed()`. The lifecycle layer is
  now the SOLE code path for OPEN→CLOSED transitions (matching what v0.1.15
  will use when swapping in Shioaji broker).

- **P1-8 same-day idempotency** — `scripts/process_entries.py` added
  `_has_active_signal_for(symbol, strategy, signal_type, signal_date)` check
  before `save_signal`. Same-day re-run of `daily_run.py` (e.g., after
  recoverable abort) no longer creates duplicate PENDING entries for the
  same (symbol, strategy, signal_type, trading_day) tuple.

### Added — Infrastructure

- **`execution/shutdown.py::next_trading_day(d, max_lookahead=10)`** — sibling
  helper to `is_trading_day`. Queries `daily_price_adj` for min date strictly
  after `d` within lookahead window. Returns `None` on data gap (caller
  decides whether to abort or skip).

- **`tests/`** — first proper test directory; pyproject.toml dev-dependencies
  already had `pytest>=8.0` + `pytest-cov>=5.0`. Test infrastructure invented:
  `Settings` injection pattern for per-test DB isolation (cleaner than env-var
  monkey-patching given pydantic-settings caching).

### Verified
- `ruff check .` — All checks passed ✓
- `pytest tests/` — 11 passed ✓
- `daily_run.py` — **149 lines** (< 150 ceiling) ✓
- All Round-2 module APIs preserved (no breaking changes to import surface)

### Acceptance criteria (8 items, updated for v0.1.14.2-c)
- [x] daily_run.py < 150 lines (149 actual)
- [x] execution/ each module single interface
- [ ] Telegram message latency < 30s (live measurement on nexus)
- [x] /approve, /reject correctly trigger state transitions (test_state_machine ✓)
- [x] ATR drift > 0.5×ATR auto-expires (test_atr_drift_expiry ✓)
- [x] Late /approve correctly rejected AND transitions DB (test_late_approve_marks_timeout ✓)
- [ ] 5 consecutive trading days no anomaly (→ v0.1.14.3 5-day window)
- [x] Graceful shutdown: durable state preserved on abort
- [x] **NEW**: chat_id security gate (test_unauthorized_chat_ignored ✓)
- [x] **NEW**: T+1 fill semantics correct (test_t_plus_1_fill_date + uses_next_day_close ✓)
- [x] **NEW**: Telegram push failure doesn't leak PENDING (test_push_failure_does_not_leave_pending ✓)
- [x] **NEW**: Same-symbol double-open blocked (test_same_symbol_double_open_blocked ✓)

### Bumped
- `pyproject.toml` 0.1.14.2-b → 0.1.14.2-c

### Reviewer's mandated test list — all delivered
| Reviewer's test name | Implemented |
|---|---|
| test_unauthorized_chat_ignored | ✓ |
| test_approve_pending_to_position | ✓ |
| test_reject_pending | ✓ |
| test_late_approve_marks_timeout | ✓ |
| test_atr_drift_expiry | ✓ (+ negative case `test_atr_drift_under_threshold_no_expire`) |
| test_push_failure_does_not_leave_pending | ✓ |
| test_double_approve_idempotent | ✓ |
| test_same_symbol_double_open_blocked | ✓ |
| test_t_plus_1_fill_date | ✓ (+ `test_t_plus_1_fill_uses_next_day_close`) |

---

## [v0.1.14.2-b] — 2026-05-17 — Paper Trading Round 2: Telegram + approval flow + graceful shutdown

### Scope (Round 2 of 2)
Build the Telegram approval loop on top of Round 1's execution + storage foundation.
Per decision-confirmation v0.1.14.2-b: 6 modules + ADR-008 + graceful shutdown,
strictly bounded scope.

### Added — communication layer

- **`communication/__init__.py`** (new package)
- **`communication/telegram/`** new module (per ADR-008 — polling, no SDK):
  - `__init__.py` — exports `TelegramBot`, `TelegramConfig`
  - `bot.py` v0.1.0 — minimal Bot API client using raw `requests`
    - `TelegramConfig.from_env()` reads HELIOS_TELEGRAM_BOT_TOKEN + HELIOS_TELEGRAM_CHAT_ID
    - `send_message()` returns None on network failure (per §9 escalation: Telegram outage acceptable degradation for entries)
    - `get_updates()` long-polling (30s default)
  - `sender.py` v0.1.0 — high-level formatters:
    - `format_entry_request()` Markdown with **risk preview** (per review #4):
      portfolio exposure delta / cash buffer delta / sector exposure delta / ETF total / ATR drift threshold / timeout
    - `push_entry_request()`, `push_exit_notification()`, `push_simple()`
  - `listener.py` v0.1.0 — 30-min polling window (per decision-confirmation B1):
    - `listen_for_approvals()` with configurable duration
    - Handles `/approve <id>`, `/reject <id>`, `/status`, `/help`
    - Early exit when no pending remain
    - Final summary message at window end

### Added — execution layer modules

- **`execution/approvals.py`** v0.1.0:
  - `approve_signal(signal_id_or_prefix, target_notional, fill_date, broker, ...)` 
    Validates: status==PENDING, not timed out, ATR drift within threshold AT APPROVAL TIME
    On success: signal → APPROVED, calls lifecycle.open_position_from_signal
    Returns (success, human_message, position_id)
  - `reject_signal(...)` terminal transition
  - `list_pending_for_display()` for `/status`
  - Internal: `_resolve_signal()` supports short-prefix lookup for Telegram

- **`execution/lifecycle.py`** v0.1.0 (per decision-confirmation Q3 boundary):
  - `open_position_from_signal()` — broker buy + storage open, atomic-as-possible
  - `close_position_for_exit()` — broker sell + storage mark_closed
  - Failure modes logged explicitly (broker fill fail, storage write fail)

- **`execution/expiry.py`** v0.1.0:
  - `expire_by_timeout(now)` — delegates to storage.signals.expire_timed_out
  - `expire_by_drift(as_of, multiplier=0.5)` — builds current-price dict, delegates
    to storage.signals.expire_drifted; returns list of expired signal_ids
  - `expire_all_pending(reason)` — graceful-shutdown helper (used by shutdown.py)

- **`execution/reconciliation.py`** v0.1.0 — **STUB**:
  - `ReconciliationReport` dataclass committed (API surface for v0.1.15)
  - `reconcile(as_of)` returns skipped=True, clean=True with skip_reason
  - v0.1.15 will replace with Shioaji-backed real impl; call site (daily_run Step 7) unchanged

- **`execution/shutdown.py`** v0.1.0 (per decision-confirmation new criterion #8):
  - `shutdown_guard(as_of, telegram_notify=None)` context manager
  - On normal exit: write completion marker status='ok'
  - On exception/KeyboardInterrupt: 3-step abort cleanup:
    1. `expire_all_pending()` (don't leave half-processed state)
    2. Telegram notify (if configured) with abort reason + error
    3. Write marker status='aborted' (next prev-day check will refuse)
  - Each cleanup step wrapped in try/except — never raise from cleanup
  - Plus: `check_previous_run()`, `check_data_freshness()`, `is_trading_day()`
    (sibling pre-run checks, moved here from daily_run.py for line budget)

### Refactored — orchestration layer

- **`scripts/daily_run.py`** — full rewrite from Round-1 (was ~210 lines, now 149):
  - Pipeline of 7 numbered steps, each is single module call
  - Wrapped in `shutdown_guard` for abort handling
  - Step 5 calls `process_entries.generate_pending_signals()` (new callable API)
    which pushes to Telegram if bot configured
  - Step 6 launches 30-min listener if pending signals + bot available
  - Step 7 calls reconciliation stub
  - Argparse: `--listener-minutes`, `--no-listener`, `--ignore-prev-check`

- **`scripts/process_entries.py`** — added `generate_pending_signals(as_of, capital, bot=None)`
  callable for daily_run integration; keeps standalone CLI for testing

### Added — Documentation

- **`docs/decision_records/ADR-008-telegram-polling.md`** —
  formalize polling-over-webhook choice; rejects always-on listener and SDK dependency
  per §0.5 Simplicity Doctrine three-test.

- **`docs/reviews/`** new directory structure (per decision-confirmation canonical/archive split):
  - `README.md` — convention, frontmatter format, when to use canonical vs archive
  - `canonical/` — load-bearing reviews still informing active design:
    - `v0.1.14.1_portfolio-cluster-warning.md` (origin of ADR-003 + §7.5)
    - `v0.1.14.1.3_architecture-A-minus.md` (origin of §6.5 / §7.5 / §9 escalation / §11.5)
    - `v0.1.14.2_decision-confirmation.md` (Round 2 scope locking process)
  - `archive/` — superseded / historical context:
    - `v0.1.13.3_round-trip-strong-pass.md`
    - `v0.1.14.1.2_architecture-A-rating.md`

- **`ARCHITECTURE.md §0.7 Determinism Principle`** — added operator-trust sentence
  (per decision-confirmation: minimal-dose, not new section)

### Verified (workspace unit tests)
- All module imports clean ✓
- Shutdown guard normal path: marker status='ok' ✓
- Shutdown guard abort path: marker status='aborted' + Telegram notify ✓
- `check_previous_run` correctly blocks subsequent run after abort ✓
- Reconciliation stub returns skipped + is_clean ✓
- `expire_all_pending` shutdown helper works ✓
- Telegram listener `/help` command parser ✓
- All 12 modules pass ruff check ✓

### Acceptance criteria (8 items, per decision-confirmation)
- [x] `daily_run.py` < 150 lines — **149 actual**
- [x] `execution/` each module single interface
- [ ] Telegram message latency < 30s (needs live measurement on nexus)
- [ ] `/approve` `/reject` correctly trigger state transitions (needs live e2e)
- [ ] ATR drift > 0.5×ATR auto-expires (unit-test path covered; needs live e2e)
- [ ] Late `/approve` after expiry correctly rejected (unit-test path covered; needs live e2e)
- [ ] 5 consecutive trading days no anomaly (5-day observation, → v0.1.14.3)
- [x] Graceful shutdown: durable state preserved on abort (unit tested)

### Bumped
- `pyproject.toml` 0.1.14.2-a → 0.1.14.2-b

### Round 2 deliverable
Full paper-trading pipeline with Telegram approval is now end-to-end runnable.
**User prep before testing**: set `HELIOS_TELEGRAM_BOT_TOKEN` + `HELIOS_TELEGRAM_CHAT_ID`
env vars (or `.env`).

Without Telegram config, daily_run runs through steps 0-5 and 7, skipping step 6
(listener). Operator can still test via `scripts/process_entries.py --auto-approve`
(Round-1 style).

Next: v0.1.14.3 — 5-day stability validation + fill realism.

---

## [v0.1.14.2-a] — 2026-05-17 — Paper Trading Round 1: state machine + broker + execution

### Scope (Round 1 of 2)
Build the **execution + storage foundation** for paper trading: positions state machine,
paper broker with cost model, exit-scan logic, entry-signal processing. Telegram +
inline daily_run approval flow deferred to Round 2 (needs user-provided bot token).

### Added — Storage layer

- **`data/database.py`** — bumped to v0.1.6:
  - New `positions` table (34 columns) implementing ARCHITECTURE §6.5 state machine
  - Status column: OPENING / OPEN / CLOSING / CLOSED
  - Per review #1: `regime_at_entry` column for post-hoc analysis
  - Running stats columns: `last_close`, `max_close_since_entry`, `min_close_since_entry`
    + their dates
  - Exit fields: date, price, reason, regime, commission, tax, slippage, proceeds
  - FK columns to signals and orders (entry & exit each)
  - Indexes on status, symbol, entry_date

- **`storage/positions.py`** — full rewrite (v0.2.0):
  - Replaces previous event-sourced derive-from-orders approach with first-class
    positions table (state needs to persist across daily_run invocations)
  - `Position` dataclass with computed properties: mfe_pct, mae_pct,
    current_drawdown_pct (review #1), unrealized_pnl_ntd, gross_return_pct,
    net_pnl_ntd, holding_days, is_open
  - CRUD: `open_position()`, `mark_position_open()`, `update_running_stats()`,
    `start_closing()`, `mark_position_closed()`
  - Reads: `get_position()`, `get_open_positions(symbol=None)`,
    `get_closed_positions(limit)`, `has_open_position(symbol)`
  - State machine enforcement: `ALLOWED_TRANSITIONS` dict, `_transition()` helper
    raises on invalid transitions

### Added — Execution layer

- **`execution/`** new module:
  - `__init__.py` — exports `PaperBroker`, `TransactionFees`, `FillResult`,
    `DEFAULT_TW_FEES`
  - **`paper_broker.py`** v0.1.0 (per review #2):
    - `TransactionFees` frozen dataclass: commission_rate, sell_tax_rate, slippage_rate
    - `DEFAULT_TW_FEES`: 永豐金 retail (0.1425% comm, 0.3% sell tax, 0.1% slippage)
    - `FillResult` dataclass: full breakdown (success, fill_price, ref_price, shares,
      notional, commission, tax, slippage_cost, total_cost, cash_delta)
    - `PaperBroker.submit_buy(symbol, target_notional, fill_date)` — asymmetric cost,
      writes filled order to orders table, returns FillResult
    - `PaperBroker.submit_sell(symbol, shares, fill_date)` — same with tax included
    - `FILL_MODEL = "adj_close"` (v0.1; configurable to "next_open" in future)
    - Graceful failure: no_price_data, invalid_price, insufficient_notional, etc.

### Added — Scripts

- **`scripts/run_exit_scan.py`** v0.1.0:
  - Loads all OPEN positions
  - For each: looks up today's adj_close + ATR + market_regime
  - Updates running stats
  - Applies exit rules (RegimeExit priority=1, TrailingStop priority=2)
  - Auto-executes via PaperBroker (per ADR-004 — no approval for exits)
  - `scan_and_exit(as_of, fees)` function callable from daily_run.py
  - CLI: `--as-of YYYY-MM-DD`, `--slippage RATE`

- **`scripts/process_entries.py`** v0.1.0:
  - Runs TrendBreakoutStrategy.generate_signals
  - Loads account state (cash, equity, sector exposures) from positions table
  - Applies portfolio constraints (selector logic from `portfolio/`)
  - Writes accepted signals to signals table as PENDING (or AUTO_APPROVED with flag)
  - **Per review #4**: prints Risk Preview for each candidate — portfolio exposure
    delta / cash buffer delta / sector exposure delta / ETF total — so operator
    has informed-approval context
  - `--auto-approve` flag (testing only): bypass ADR-004, immediately fill + open
    via PaperBroker
  - CLI: `--as-of`, `--capital`, `--slippage`, `--auto-approve`

- **`scripts/daily_run.py`** v0.1.0 (skeleton, Round 1):
  - Step 0: **previous-run check** (per review #3) — `~/.helios_last_run.json` marker
    file; abort if previous status != ok unless `--ignore-prev-check`
  - Step 1: Data freshness check (per §9 Operational Assumptions)
  - Step 2: Market calendar check (v0.1.14.2: any date with data is trading day;
    v0.2+: TWSE official calendar API)
  - Step 3: Inline exit scan (calls `run_exit_scan.scan_and_exit`)
  - Step 4: Entry processing — Round 1: prints "run process_entries.py separately";
    Round 2 will inline with Telegram push
  - Writes completion marker on success / failure with status + summary

### Per-review adjustments incorporated

| Review item | Where addressed |
|---|---|
| #1 `regime_at_entry` + `max_drawdown_pct` | positions.regime_at_entry column; `Position.current_drawdown_pct` computed property |
| #2 paper_broker cost model明確化 | `TransactionFees` dataclass + `FILL_MODEL` constant + asymmetric buy/sell math |
| #3 previous-day completion check | `daily_run.py` step 0 + marker file `~/.helios_last_run.json` |
| #4 Telegram risk preview | `process_entries.py._print_risk_preview()` — exposure / cash / sector deltas |
| #5 quantitative acceptance | (deferred to Round 2 — needs e2e Telegram for full criteria 1-6 measurement) |

### Verified (workspace unit tests)
- Schema includes positions table with all 34 columns including regime_at_entry ✓
- Position state machine: OPEN → CLOSED transition with full exit field population ✓
- Invalid transition (CLOSED → CLOSED) raises ValueError ✓
- update_running_stats correctly tracks max/min only when strictly higher/lower ✓
- Computed properties (MFE/MAE/current_drawdown/unrealized_pnl) match math ✓
- TransactionFees defaults match 台股 standard rates ✓
- PaperBroker handles missing price data gracefully (returns FillResult with error) ✓

### Bumped
- `pyproject.toml` 0.1.14.1.4 → 0.1.14.2-a

### Round 1 deliverable
End-to-end paper-trading pipeline **minus Telegram**. User can:
1. Run `scripts/run_exit_scan.py --as-of YYYY-MM-DD` to test exit logic
2. Run `scripts/process_entries.py --as-of YYYY-MM-DD --auto-approve` to test entry pipeline
3. Run `scripts/daily_run.py --as-of YYYY-MM-DD` to test orchestration
4. Query `positions` table to inspect state machine evolution

Round 2 (next session): adds Telegram bot integration for the real approval flow.
User prep between sessions: get bot token + chat_id (instructions in v0.1.14.2-b plan).

---

## [v0.1.14.1.4] — 2026-05-17 — FINAL docs sprint: state machine + portfolio philosophy + operational physics

### 觸發
Third architecture review (after v0.1.14.1.3). Reviewer rated:
- Architecture maturity A-, System philosophy A, Operational realism A, Complexity discipline A
- Production readiness B (still missing paper/live operational scars — NOT fixable by more docs)

Reviewer identified 5 final additions. Two are critical pre-v0.1.14.2 (state machine + escalation
policy define the input spec for implementation). Three are valuable but not blocking
(portfolio philosophy, calendar acknowledgment, roadmap rule).

### Added — ARCHITECTURE.md

- **§6.5 Signal Lifecycle State Machine** (NEW, critical) —
  Mermaid state diagram + state definitions table + transition rules (with edge cases)
  + invariants. Maps directly to v0.1.14.2 implementation surface (storage / telegram /
  paper_broker / daily_run). Without this section, v0.1.14.2 would invent transitions
  ad-hoc and ship with ambiguity bugs at edges.

- **§7.5 Portfolio Philosophy** (NEW) —
  Six principles framing portfolio layer as **alpha-preserving filter** (not just risk
  control). Distills F-experiment insight: constraints filter quality, capital scarcity
  forces ranking, clustering is feature, sparsity is correct, underdeployment is OK,
  concentrated exposure can improve expectancy.

- **§9 Operational Assumptions** — added two subsections:
  - **Escalation Policy** (NEW, critical) — 9-scenario table for operator unavailability
    (timeout, drift, Telegram outage, late approval, etc.). Principle: "missed signal >
    wrong trade". Maps to concrete handlers in v0.1.14.2.
  - **Market Calendar Semantics** (NEW) — TWSE business days, half-day markets, holidays,
    typhoon closures, makeup workdays. v0.1.14.2 strategy: hardcode 2026 calendar.
    v0.2+ strategy: TWSE API.

- **§12 Future Roadmap** — preamble added: 4-gate discipline ("backtested → OOS validated →
  paper-traded → operationally observed") as governing rule for all future versions.

### Final ARCHITECTURE.md TOC

```
§0     Identity
§0.5   Simplicity Doctrine (Standing Order)
§0.7   Determinism Principle
§1     Mission
§2     Why Helios is intentionally NOT HFT
§3     Layer Map
§4     Data Layer
§5     Feature Layer
§6     Strategy Layer
§6.5   Signal Lifecycle State Machine        ← NEW v0.1.14.1.4
§7     Backtest + Portfolio Layer
§7.5   Portfolio Philosophy                  ← NEW v0.1.14.1.4
§8     Validation Pipeline
§9     Operational Assumptions
       └ Data Freshness Contract
       └ Escalation Policy                   ← NEW v0.1.14.1.4
       └ Market Calendar Semantics           ← NEW v0.1.14.1.4
§10    Empirical Findings
§10.5  Experimental Findings (F)
§11    Known Limitations
§11.5  Failure Modes
§12    Future Roadmap (with 4-gate rule)     ← UPDATED v0.1.14.1.4
§13    Hard Rules (Never Violate)
§14    Decision Records (7 ADRs)
```

### Bumped
- `pyproject.toml` 0.1.14.1.3 → 0.1.14.1.4

### v0.1.14.1.4 deliverable + HARD COMMIT

ARCHITECTURE.md is now feature-complete for v0.1.14.2 implementation. State machine
defines transitions; escalation policy defines edge cases; portfolio philosophy
defines design tenets; calendar semantics defines perimeter; roadmap rule defines
gates.

**Next session is v0.1.14.2 paper trading. Any further architecture review feedback
will be acknowledged but NOT acted upon until v0.1.14.2 is shipped.** This is the
hard commit; doc polishing has reached diminishing returns.

---

## [v0.1.14.1.3] — 2026-05-17 — Simplicity Doctrine + Failure Modes + F findings + ADR-007

### 觸發
Second-pass ARCHITECTURE review (after v0.1.14.1.2). Reviewer rated A/A- but flagged
5 critical additions:
1. Simplicity Doctrine (standing order vs specific decisions)
2. Failure Modes (paper-trade-readiness requires explicit "expected to fail under...")
3. Data Freshness Contract (operational physics)
4. Position sizing rationale (the "why 20%")
5. Why deterministic (philosophy beyond just ADR-005)

Combined with the **F experiment findings review** (CONCENTRATED 3×30% unexpectedly
dominates CURRENT 5×20% on OOS — structural insight, not optimization).

### Added — ARCHITECTURE.md sections

- **§0.5 Simplicity Doctrine** (NEW, the "constitution") — three-test gate (alpha
  contribution / operational necessity / maintenance sustainability) for ALL future
  additions. ADRs become specific applications of this standing order.
- **§0.7 Determinism Principle** (NEW) — short callout in main flow making determinism
  explicit (was previously only in ADR-005).
- **§7 Position sizing rationale** (UPDATE) — 6-bullet "why 20%" with F-experiment
  cross-reference.
- **§9 Data Freshness Contract** (UPDATE) — concrete T-1 ingest deadline (08:30 Asia/Taipei),
  freshness check first action in daily_run.py, ABORT-not-degrade policy.
- **§10.5 Experimental Findings** (NEW) — F experiment full table + 3 structural
  insights + "not promoted because" reasoning.
- **§11.5 Failure Modes** (NEW) — 8 market conditions + 5 system failure modes +
  operator instructions for using this section during paper trading.

### Added — Decision Records

- **`docs/decision_records/ADR-007-profile-switching.md`** — **Proposed** status (NOT
  Accepted). First Proposed ADR; documents the CONCENTRATED-profile finding + the
  case for not acting now + promotion triggers. Prevents both forgetting AND
  premature adoption.
- Updated ADR README index with ADR-007 entry.

### Added — RESEARCH_JOURNAL.md

- New entry `v0.1.14.1.2.experiment` — F budget sweep findings with reviewer's
  reframing ("system dynamics, not curve fitting") + 3 structural insights +
  operator framing ("regime-aware sniper, not signal farm").

### Bumped
- `pyproject.toml` 0.1.14.1.2 → 0.1.14.1.3

### v0.1.14.1.3 deliverable

**Final docs sprint before v0.1.14.2 paper trading.** ARCHITECTURE.md now contains:
- Identity (what Helios is/isn't)
- Simplicity Doctrine (how additions are gated)
- Why determinism / Why NOT HFT (specific philosophy)
- Operational physics (freshness contract, T+1 settlement)
- Experimental findings + ADR-007 (proposed future direction recorded but not active)
- Failure Modes (the "this is expected behavior" reference for paper trading)

Hard commit: next session is v0.1.14.2 paper trading execution.

---

## [v0.1.14.1.2] — 2026-05-17 — Architecture crystallized + ADR records

### 觸發
Reviewer (再次) 強調: 「現在最值得保護的不是 code, 是系統哲學」.
警告 complexity creep 是量化系統最常見死因 (不是 strategy fail).
建議 explicit identity statement + explicit non-goals + ADR (Architecture Decision Records).

### Why this matters
> v0.1.14.1.1 ARCHITECTURE.md had decent layer-map but missing **identity**, **operational
> assumptions**, **known limitations**, and **explicit non-goals** for v0.1.14.2.
> Without these, future "scope creep pressure" (add websocket / add LLM / add Kelly) has
> no written counter. Identity statement is the **complexity firewall**.

### Added

- **`docs/ARCHITECTURE.md`** — substantial rewrite, now 14 sections including:
  - **§0 Identity** (NEW, leading position) — "Helios IS / IS NOT" lists
  - **§2 Why Helios is intentionally NOT HFT** (NEW) — table of complexity vectors closed off
  - **§9 Operational Assumptions** (NEW) — system "physics" (single user / daily batch / T+1 / approval)
  - **§11 Known Limitations** (NEW) — alpha character + scope + methodological limits
  - **§12 Future Roadmap** — added v0.1.14.2 explicit non-goals
  - **§14 Decision Records** — links to ADRs

- **`docs/RESEARCH_JOURNAL.md`** — renamed from JOURNAL.md (per reviewer naming),
  header tweaked to clarify role vs ARCHITECTURE / data_behavior_notes / decision_records

- **`docs/decision_records/`** new directory:
  - `README.md` — Michael Nygard ADR format + when to write a new ADR + current index
  - `ADR-001-no-hft.md` — daily-batch is non-negotiable
  - `ADR-002-polars-native-indicators.md` — no TA-Lib / pandas-ta
  - `ADR-003-portfolio-before-papertrading.md` — capital validation before execution
  - `ADR-004-human-approval-required.md` — no autopilot; exits auto, entries manual
  - `ADR-005-deterministic-regime.md` — no HMM / ML for regime
  - `ADR-006-cohesion-over-abstraction.md` — single file per layer in v0.1

### Why ADRs (and not just notes)
Each ADR closes off a **complexity vector** with a written rationale.
6 months from now, when the temptation to "add websocket" / "switch to TA-Lib" / "add a Kelly sizing
optimizer" arises, the ADR is the firewall — either the change supersedes the ADR (with explicit
new reasoning), or it doesn't belong in Helios.

### Skipped (per reviewer)
- ❌ F (budget sweep run) — premature optimization; `scripts/budget_sweep.py` stays in repo as future tool
- ❌ G (telecom removal) — n=6 too small; telecom serves as "low-momentum control group"

### Bumped
- `pyproject.toml` 0.1.14.1.1 → 0.1.14.1.2

### v0.1.14.1.2 deliverable
System identity now formally crystallized in repo. Future scope-pressure has a documented
counter. Next: v0.1.14.2 paper trading with strict scope (per ADR-001 non-goals).

---

## [v0.1.14.1.1] — 2026-05-17 — Docs + Notebook + Budget Sweep

### 觸發
v0.1.14.1 substantively STRONG PASS. User chose E+F: 暫停整理 + low-cost budget 實驗,
然後再進 v0.1.14.2 paper trading.

### Added
- **`docs/ARCHITECTURE.md`** (~300 行):
  - Mission + design tenets (5 priorities)
  - Layer map (Foundation → Data → Feature → Strategy+Backtest → Portfolio → Execution[planned])
  - Per-layer detail with decisions
  - Empirical findings snapshot
  - Future roadmap + hard rules

- **`docs/JOURNAL.md`** (~260 行):
  - Reverse chronological per-version: what / why / key insight / reviewer feedback
  - Cumulative reviewer wisdom (top 10 lessons)
  - "Lessons that surprised us" table

- **`notebooks/portfolio_analysis.ipynb`** (19 cells):
  - Load equity.csv / trades.csv / decisions.csv
  - Plots: equity curve / drawdown / exposure / trade scatter / return histogram
  - Tables: by sector / exit reason / regime / reject distribution
  - Score-decision matrix

- **`scripts/budget_sweep.py`** (~200 行):
  - F experiment — sweep 5 budget configs:
    - CURRENT (5×20%) — default
    - CONCENTRATED (3×30%) — fewer but bigger positions
    - EFFECTIVE-4 (4×22%) — match cash_buffer binding
    - WIDER (5×18%, etf=50%, sec=35%) — more diversified
    - NO-ETF-CAP (5×20%, etf=100%) — see ETF cap impact
  - Side-by-side comparison (CAGR / DD / PF / Win% / Exposure / Rejects)
  - Reject reason distribution variation per config

### Bumped
- `pyproject.toml` 0.1.14.1 → 0.1.14.1.1

### v0.1.14.1.1 deliverable
1. 跑 `scripts/budget_sweep.py --is-end 2023-12-31` 拿到 5-config comparison
2. 在 `notebooks/portfolio_analysis.ipynb` 開圖看 equity / DD / exposure
3. Decide budget profile (or stay default) → 進 v0.1.14.2 paper trading

---

## [v0.1.14.1] — 2026-05-17 — Portfolio Layer + Constrained Backtest (deployment reality check)

### 觸發
v0.1.13.3 round-trip 跑出 ✓✓ STRONG PASS (OOS net PF 2.50, mean +1.99%).
但 reviewer §40-49 警告: **trade-level metrics ≠ portfolio-level deployability**:
- 假設每個 signal 都能開倉 (unconstrained capital)
- 沒考慮 ETF + 金融 cluster 高度 correlated
- 真實 portfolio max DD 可能是 trade-level worst (-7.7%) 的 2-3 倍
- 在 paper trade 前必須跑 **constrained** backtest
→ v0.1.14.1 = "deployment reality check", 不是 paper trading 本身.

### Architecture decisions (per reviewer §43-46 + user spec)
- **Equal-weight 20% per position** (no Kelly / no covariance optimization)
- **max_positions=5** (但 cash_buffer 10% 實際上 binding 在 4 positions)
- **max_etf_exposure=40%** (ETF cluster cap, 防 over-concentration)
- **max_sector_exposure=30%** (任一 sector 不可超過)
- **cash_buffer=10%** (永遠留現金, 緊急 buffer + 心理安全)
- **Sector classification hardcoded** in v0.1 (15 symbols), 未來轉 company_metadata.industry_code
- **NO portfolio optimizer / HRP / risk parity** (reviewer §45 明文)

### Added
- **`portfolio/`** new module:
  - `__init__.py` — exports
  - `risk_budget.py` v0.1.0 — `RiskBudget` frozen dataclass
    - `DEFAULT_RISK_BUDGET` (per user spec)
    - `describe()` for logging
  - `selector.py` v0.1.0 — sector classification:
    - `SECTOR_MAP` (15 symbols hardcoded: 5 etf / 3 semi / 3 electronics / 3 financial / 1 telecom)
    - `get_sector(stock_id)` / `is_etf(stock_id)` / `all_sectors()`

- **`backtest/portfolio_simulator.py`** v0.1.0:
  - `PortfolioPosition` — Position + sizing (notional / shares / sector / is_etf_pos)
  - `EquitySnapshot` — daily (cash / positions_value / equity / n_positions / exposure_pct)
  - `SignalDecision` — per-signal (accepted / rejected + reject_reason)
  - `PortfolioMetrics` — CAGR / max DD / avg exposure / reject distribution
  - `PortfolioBacktest` class:
    - Preload close + ATR + regime + signals
    - Daily flow: update → exit check (priority order) → process signals (constraints) → record equity
    - Multi-signal selection: sort by score DESC, apply constraints
    - Costs applied: buy = notional × (1 + commission + slippage); sell = proceeds × (1 - commission - tax - slippage)
    - Force-close remaining open at end

- **`scripts/run_portfolio_backtest.py`** v0.1.0:
  - Full CLI: capital / budget knobs / costs / IS-OOS split / CSV exports
  - 3-panel output: FULL HISTORY / IN-SAMPLE / OUT-OF-SAMPLE
  - Verdict logic (user spec):
    - ✓✓ STRONG PASS: OOS PF > 1.7, max DD < 15%, avg exposure 30-90%
    - ✓ PASS: OOS PF > 1.3, max DD < 25%
    - ⚠ FAIL: insufficient sample / negative return / weak edge
  - Sector exposure breakdown + equity curve sample points

### Verified (workspace)
- Sector classification correct for all 15 universe symbols ✓
- DEFAULT_RISK_BUDGET matches user spec ✓
- 5-sector distribution: etf=5, semi=3, electronics=3, financial=3, telecom=1 ✓
- Critical implication: cash_buffer 10% binding before max_positions 5 ✓
- All imports clean, CLI loads cleanly ✓

### Bumped
- `pyproject.toml` 0.1.13.3 → 0.1.14.1

### v0.1.14.1 deliverable (per user spec exit criteria)
跑 `scripts/run_portfolio_backtest.py --is-end 2023-12-31` 拿到:
- OOS net PF (要 > 1.7 for STRONG)
- OOS max DD (要可接受)
- 平均曝險 (合理範圍)
- 拒絕訊號分布 (沒過度集中)
→ STRONG PASS → 進 v0.1.14.2 (paper trading execution)
→ PASS → 也進 v0.1.14.2, 但 risk 控制更嚴
→ FAIL → 調整 budget 或退回 v0.1.12 重審

---

## [v0.1.13.3] — 2026-05-17 — OOS round-trip + transaction costs (deployment-grade)

### 觸發
v0.1.13.2 round-trip backtest 跑出 profit factor 2.67, MFE/|MAE| 4.47, 教科書級 trend signature.
但結果是 **in-sample (5 年全部) + 零成本**. 進 paper trading 前必須回答:
  - exit logic 在 OOS 期間是否一樣有效?
  - 扣台股 ~0.6% round-trip 成本後 alpha 還在嗎?
→ v0.1.13.3 = 「deployment-grade check」前的最後一關.

### Added
- **`backtest/round_trip.py`** v0.1.0 → v0.1.1:
  - `TransactionCosts` dataclass (commission / sell_tax / slippage)
  - `total_round_trip_pct` property: 2*commission + sell_tax + 2*slippage
  - 台股 default: commission=0.1425% / sell_tax=0.3% / slippage=0
  - `compute_metrics(trades, costs)` — 接受 costs, 從 gross_return 扣除
  - `partition_by_date(trades, is_end)` — IS/OOS split by entry_date
  - `NO_COSTS` constant for clarity

- **`scripts/run_backtest.py`** v0.1.0 → v0.1.1 (完全 rewrite):
  - `--commission` / `--sell-tax` / `--slippage` / `--no-costs` 旗標
  - `--is-end YYYY-MM-DD` 啟用 IS/OOS side-by-side
  - Gross vs Net 兩欄並列 (確認 cost impact)
  - Verdict logic per user spec:
    - ✓✓ STRONG PASS: OOS net mean > 1.0% AND PF > 1.7 AND W/L > 1.5
    - ✓ PASS: OOS net mean > 0 AND PF > 1.3 AND crisis = 0 AND n >= 30
    - ⚠ FAIL: insufficient sample / regime broken / negative expectancy / weak edge

### Cost model (台股)
```
buy:  commission 0.1425%
sell: commission 0.1425% + tax 0.3% = 0.4425%
total round-trip = 0.585% (no slippage)
                 = 0.785% (with 0.1% slippage)
```

### Verified (workspace unit tests)
- TransactionCosts math: default 0.585%, +0.1% slippage = 0.785% ✓
- compute_metrics with cost: gross +1.71% → net +1.13% (correct -0.585% drag) ✓
- compute_metrics PF: 3.00 → 2.02 with cost ✓
- partition_by_date splits 7 trades into 4 IS / 3 OOS at boundary ✓

### Bumped
- `pyproject.toml` 0.1.13.2 → 0.1.13.3

### v0.1.13.3 deliverable
跑 `scripts/run_backtest.py --is-end 2023-12-31` 拿到 VERDICT (PASS/STRONG PASS/FAIL).
PASS+ → 可進 paper trading prep (v0.1.14).
FAIL  → 退回 v0.1.12 重審 strategy 條件.

---

## [v0.1.13.2] — 2026-05-17 — Exit Logic + Round-trip Backtest (第一個完整 trade lifecycle)

### 觸發
v0.1.13.1 OOS validation 跑出 ✓ REAL ALPHA (OOS 65% hit_20 > IS 60%, mean 2.93% > IS 1.65%).
Reviewer §53: 「v0.1.13.2 不是 production engine, 是第一個完整 deterministic trade lifecycle」.
→ 從 half-loop (entry only) 變 full-loop (entry + exit + round-trip metrics).

### Architecture decisions (採納 reviewer §33-52 全部建議)
- **Regime exit priority > ATR stop** (§43): 大虧通常來自 regime collapse, ATR 太慢
- **Fixed multiplier 2.0** (§36): NOT adaptive / ML / volatility-aware
- **No time stop** (§47): 會切掉最好 winners, trend-following 大忌
- **Exit metadata 必含 MFE/MAE/exit_reason** (§40): risk profile transparency
- **No Kelly / sizing / portfolio overlap** (§51): 單策略行為理解優先
- **Backtest 不寫 DB** (§53 "原型"): in-memory positions, 不過早 schema persist

### Added
- **`strategies/exit/`** new module:
  - `__init__.py` — exports
  - `base.py` v0.1.0 — `ExitRule` ABC + `Position` lifecycle dataclass + `ExitDecision`
    - `Position` 含 MFE/MAE/holding_days/is_open 等 property
    - `update_running_stats(close, date)` 跟隨 max/min close
  - `regime_exit.py` v0.1.0 — priority=1, 規則簡單: regime != 'bull' → exit
  - `trailing_stop.py` v0.1.0 — priority=2, 規則: close < max_close - 2 * atr_14

- **`backtest/`** new module:
  - `__init__.py` — exports
  - `round_trip.py` v0.1.0:
    - `RoundTripBacktest` class — daily close-based simulator
    - 預載 (close + atr + regime + signals) 後 in-memory iteration
    - Flow: update stats → check exits (priority order) → open new positions
    - Force-close 剩餘 open positions at end (exit_reason='end_of_backtest')
    - `compute_metrics()` → `RoundTripMetrics` (reviewer §50 全部欄位)
    - `trades_to_polars()` → DataFrame 給 CSV export

- **`scripts/run_backtest.py`** v0.1.0:
  - 跑全歷史 round-trip + 印 reviewer §50 metrics:
    - win_rate / mean / median / best / worst / avg_win / avg_loss
    - win_loss_ratio / profit_factor / avg_holding_days
    - avg_mfe / avg_mae + MFE/|MAE| ratio
    - exit_reason distribution (regime_exit_share vs trailing_stop_share)
    - by_entry_regime + top symbols + per-symbol win_rate
  - `--export-csv` 輸出 trades 表

### Verified (workspace unit tests)
- `Position.update_running_stats` 正確 tracking max/min close
- MFE/MAE 計算精確 (entry=600, max=620 → MFE=+3.33%, min=590 → MAE=-1.67%)
- `TrailingStop` triggers correctly at 589 < 590 (max 620 - 2*15 ATR)
- `RegimeExit` triggers on crisis, NOT on bull
- Priority order: regime_exit (p=1) before trailing_stop (p=2)
- Position lifecycle (entry → update → exit) 完整正確

### Bumped
- `pyproject.toml` 0.1.13.1 → 0.1.13.2

### v0.1.13.2 deliverable
Reviewer §54: 「entry + exit + round-trip 跑通, Helios 真正從 research infra
變成可部署交易系統原型」.
跑 `scripts/run_backtest.py` 拿到 round-trip metrics → ✓ 完成.

---

## [v0.1.13.1] — 2026-05-17 — Out-of-Sample validation (alpha 不是 AI bull noise 的 sanity check)

### 觸發
v0.1.12 audit 跑出 217 signals 5 年, hit rate 51→58→63% 隨 horizon 上升, 右偏分布.
Reviewer 警告:
  - 「2023-2025 是 AI mega trend, breakout strategy 天然吃這波」
  - 「最大風險不是沒 exit, 而是太早相信 alpha」
  - 「需要小型 OOS sanity, 不要 ML train/test 那種複雜」
→ 切簡單 IS/OOS, 不調參, 純驗證 alpha 跨期穩定性.

### Added
- **`scripts/oos_validation.py`** v0.1.0 (新檔):
  - Split: IS ≤ 2023-12-31 < OOS (預設, 可 --is-end override)
  - 跑 strategy 在 IS / OOS 各跑一遍, **不調 parameters**
  - Side-by-side metric table:
    - Period years / trading days / signal count / rate per year
    - Regime % (bull-only check) / Crisis count (gate check)
    - 5/10/20-day hit rate / median / mean / best / worst
  - Verdict logic (reviewer §32-33):
    - ✓ REAL ALPHA       — IS > 55% AND OOS > 55% hit_20
    - ○ MARGINAL         — IS > 55% AND OOS 50-55%
    - ⚠ OVERFIT WARNING  — IS > 60% AND OOS < 50%
    - ⚠ Crisis 在 OOS 漏訊號

### Architecture decision
- 用簡單 date split, **不做** ML-style cross-validation / walk-forward / Monte Carlo
  (reviewer §30 「不要 ML train/test 那種複雜」)
- 不寫專門的 metric module — 跟 signal_audit.py 有部分重複, 但 v0.1 cohesion > DRY
- Verdict 用 threshold 不用 statistical test (n=200+ 級 sample, threshold 已夠 informative)

### Verified (workspace)
- Import + 結構 OK; full run 要在 nexus 跑 (要 5 年 daily_features 資料)

### Bumped
- `pyproject.toml` 0.1.12 → 0.1.13.1

### 決策樹 (跑完 OOS 後)
  ✓ REAL ALPHA       → 繼續 v0.1.13.2 (exit logic)
  ○ MARGINAL         → 也繼續, 但要 v0.1.13.3 後再決定要不要 paper trade
  ⚠ OVERFIT WARNING  → 退回 v0.1.12, 重新審視 (可能放寬 condition 但要小心)
  ⚠ Crisis 漏訊號     → 退回 v0.1.11, 收緊 crisis_vol_threshold

---

## [v0.1.12] — 2026-05-17 — Strategy Framework + TrendBreakout v1 (第一個 deterministic decision loop)

### 觸發
v0.1.11 完成 feature layer 全部 9 indicators + 4-state regime.
Reviewer: "Helios 不是 feature factory, 是可執行的市場決策系統"
→ 不再 feature expansion, 直接進 feature → signal 的 decision loop.

### Architecture decisions (採納 reviewer 建議)
- **Conservative breakout 條件** (台股 fake-breakout 問題): close > donchian_high.shift(1), 不是 touch
- **Slope filter** (避免「在 SMA 上方但 trend 已死」): sma_50 > sma_50.shift(5)
- **Volume confirmation** (reviewer §35 台股 breakout 沒量很危險): rel_volume_20 >= 1.5
- **Regime gate** (Helios 真正 edge — 不在爛市場交易): regime == 'bull'
- **全 AND 不是 OR**: 寧少而精, 不要 over-fire (v0.1 不該 chase signal count)
- **Replay mode 預設 dry-run**: 避免 backtest 污染 production signals 表

### Added
- **`strategies/__init__.py`** v0.1.0 (新 module)
- **`strategies/base.py`** v0.1.0:
  - `Strategy` ABC — 子類必須實作 `generate_signals(as_of, symbols)`
  - `Signal` dataclass — 7 必填欄位 + reason list + metadata dict
  - Score 範圍驗證 (0.0 ~ 1.0), side 限定 buy/sell/exit
- **`strategies/trend_breakout.py`** v0.1.0:
  - Single SQL with LAG window functions (donchian.shift(1) + sma_50.shift(5))
  - 6 個 filter 全 AND 條件
  - Score 公式 0.5 baseline + 4 個 bonus (rel_vol 2x, 3x, RSI sweet spot, ROC > 5%)
  - Decision context: 6-7 行 human-readable reason + 17 個 structured metadata key
- **`scripts/generate_signals.py`** v0.1.0:
  - 3 modes: LIVE (today, write) / REPLAY-COMMIT (--date --commit) / DRY-RUN (--date 預設)
  - 美化的 signal 印出 (含 reason 條列)
- **`scripts/signal_audit.py`** v0.1.0:
  - Full historical sweep + 5 reviewer questions:
    1. Signals 太多嗎? (rate per year)
    2. Bull market 才觸發嗎? (regime distribution)
    3. Crisis 被過濾嗎? (crisis count vs trading days)
    4. Breakout 後延續嗎? (forward 5/10/20-day returns + hit rate)
    5. ATR spike 後續? (% 訊號後 20 日 ATR > 1.5x entry)
  - Verdict 自動評等 (✓/○/⚠)

### Verified
- Mock test on synthetic data: strategy fires correctly with realistic noise
  - TEST symbol breakout: BUY @ 319.06, score=0.80, all 6 conditions verified
  - All explainability fields populated (reason list + metadata dict)
- Storage layer 既有的 `save_signal()` 介面 100% compatible (沒改 schema, reason/regime/metadata 欄位已存在)

### Bumped
- `pyproject.toml` 0.1.11 → 0.1.12

### Step 4 (v0.1.12) 完成定義
跑 `scripts/signal_audit.py` 拿到 5 個問題的明確 verdict → ✓ 完成
這 loop 是 Helios 從 "infra project" 變成 "trading system" 的關鍵分界線.

---

## [v0.1.11] — 2026-05-17 — Technical Indicators + Market Regime (Step 3)

### 觸發
v0.1.10.2 拿到 100% adjustment absorption, daily_price_adj 進入 production-clean state.
Reviewer 確認 §12 觀察是真實市場行為 (mechanical adj 跟 market reaction 區分清楚).
→ Step 2.5 正式完成, Step 3 開工: indicators + regime.

### Architecture decisions (採納 reviewer 建議)
- **Polars-native 手刻** (vs pandas-ta / TA-Lib): 透明、無新 dep、跟現有 stack 完美整合
- **單一 technical.py** (cohesion > abstraction in v0.1, 未來真複雜再拆)
- **Deterministic regime** (vs HMM): 先 market intuition encoding, 不上 latent state
- **LazyFrame-compatible helpers + materialized table**: 靈活查詢 + 快速 lookup

### Added
- **`features/technical.py`** v0.1.0 (新檔, 9 個 indicators):
  - Trend:      `add_sma(20/50/200)`, `add_ema(20)`
  - Momentum:   `add_rsi(14)` (Wilder smoothed), `add_roc(20)`
  - Volatility: `add_atr(14)` (Wilder smoothed, 用 adj OHLC 避免 dividend 污染)
  - Breakout:   `add_donchian(20)` (high + low)
  - Volume:     `add_volume_indicators(20)` (volume_ma + rel_volume)
  - Single source of truth: `compute_indicators(df)`

- **`features/regime.py`** v0.1.0 (新檔):
  - 4-state classification: bull / bear / crisis / neutral
  - 規則:
    - crisis:  vol_20 > 0.020 (TAIEX 20-day return stdev > 2%)
    - bull:    close > sma_200 AND vol_20 <= 0.020
    - bear:    close < sma_200 AND vol_20 <= 0.020
    - neutral: 過渡 (跨 SMA200 期間)
  - 不上 HMM (per reviewer 建議), v0.2 才考慮 expanding window quantile

- **`data/database.py`** v0.1.4 → v0.1.5:
  - 新增 `daily_features` 表 (11 個 indicator columns + PK + computed_at)
  - 新增 `market_regime` 表 (taiex_close, sma_200, vol_20, regime + computed_at)

- **`scripts/compute_features.py`** (新檔):
  - Phase 1: 對每個 symbol 從 daily_price_adj 算 indicators
  - Phase 2: 從 daily_price TAIEX 算 regime
  - `--indicators-only` / `--regime-only` 旗標

- **`scripts/feature_inspect.py`** (新檔, reviewer 的 Step 3 exit criteria):
  - 自動回答 5 個 strategy-readiness 問題:
    1. 現在是不是 bull regime?
    2. 個股是否高於 SMA200?
    3. 是否 volume breakout (rel_volume > 1.5x)?
    4. ATR 是否異常擴張 (vs 60d median > 1.5x)?
    5. 個股是否 Donchian-20 breakout/breakdown?

### 演算法驗證 (workspace mock tests, 全部 pass)
- SMA: trivial ✓
- RSI on alternating ±1 → 48.15 (≈ 50 expected) ✓
- RSI on monotonic uptrend → 100.00 ✓
- ATR Wilder on known TR series [4, 5, 4, 5, 5] → [4.000, 4.333, 4.222, 4.481, 4.654] (跟手算精確一致) ✓
- Regime on uptrending sine → 51 bull / 199 neutral days ✓
- compute_indicators 11 columns 全 non-null at latest row ✓

### Bumped
- `pyproject.toml` 0.1.10.2 → 0.1.11

### Step 3 exit criteria
跑 `scripts/feature_inspect.py` 能回答 reviewer 的 5 個問題 → ✓ 完成

---

## [v0.1.10.2] — 2026-05-16 — Splits: 改用 raw price 自動偵測 (Taiwan-aware)

### 觸發
v0.1.10.1 跑 `ingest_splits.py` (yfinance source) 拿到 result:
- 0050 **沒抓到** 2025-06-18 真實 1:4 split (yfinance 對台股 ETF split 不全)
- 113 個其他 events 全部是 **stock dividend 1.10-1.50 ratio** (台股無償配股)
- 跟 FinMind `dividend_result` 重疊 → 雙重 adjustment
- 2881 從 0 raw abnormal 變成 1 adj abnormal (+11.25%) ← 證據

→ **yfinance.splits 對台股「既誤報又漏報」**，不能用。

### Changed
- **`scripts/ingest_splits.py`** v0.1.0 → v0.2.0 完全改寫
  - 偵測邏輯：`close[T] / close[T-1] < 0.55` → 識別為真實 split
  - Taiwan-aware:
    - 台股 ±10% 漲跌停 → -10% 永遠不會觸發 0.55 閾值
    - 無償配股 (stock dividend) ratio ~0.85-0.95 → 不會誤抓 (FinMind 已涵蓋)
    - 真實 split 像 0050 1:4 = 0.252, 1:5 = 0.20 → 100% 抓到
  - source 改為 `auto_detected_price_drop`
  - 自動清掉 v0.1.10.1 的 yfinance 殘留 (DELETE WHERE kind='split')
  - Sanity warning: 若偵測到的 split 日同時是 dividend 日，印異常 warning

### 驗證 (workspace mock test)
3 合成案例:
- 0050 1:4 split (ratio=0.2522) → ✓ 偵測
- 2454 純現金股利 (ratio=0.91)  → ✓ 不誤判
- 2881 無償配股 (ratio=0.91)    → ✓ 不誤判

### Bumped
- `pyproject.toml` 0.1.10.1 → 0.1.10.2

---

## [v0.1.10.1] — 2026-05-16 — Splits ingestion (via yfinance) + validation 改進 [SUPERSEDED]

### 觸發
- 0050 在 2025-06-18 split day 顯示 raw -74.78% / adj -74.78% (factor 仍 0.97918)

根因確認：**FinMind `TaiwanStockDividendResult` 不包含 stock splits**。
影響：所有有 split 的 ETF/股票歷史 adjustment 都會殘留該日跳空。

### Added
- **`scripts/ingest_splits.py`** v0.1.0 (新檔)
  - 使用 `yfinance.Ticker(sid).splits` 抓 split history
  - 1:N split → `adjustment_factor = 1/N`
  - 寫入 corporate_actions, kind='split', source='yfinance_splits'
  - 跟 dividend 共表，可組合 cum_factor

### Changed
- **`scripts/validate_adjustments.py`** v0.1.0 → v0.1.1 (採納 reviewer 建議)
  - Per-type threshold:
    - stock = 0.105 (±10% 漲跌停 + buffer)
    - ETF   = 0.20  (ETF 無漲跌停限制)
  - 顯示 max |pct| residual per symbol (count=0 不等於完美)
  - 全市場 max_adj 摘要

### Bumped
- `pyproject.toml` 0.1.10 → 0.1.10.1

---

## [v0.1.10] — 2026-05-16 — Dividend Adjustment (自家還原權息層)

### 觸發
v0.1.9 累積 140 個歷史 dividend events 進 corporate_actions。
features layer 必須吸收這些事件，輸出 indicator-ready 的 adjusted prices。
這是 Step 3 (technical indicators) 的前置條件 — 用 raw 算 RSI/MACD 會被除息日污染。

### Added
- **`features/` 新 module**:
  - `__init__.py` — module docstring
  - `dividend_adjustment.py` v0.1.0:
    - `compute_adjusted(df_raw, df_events) -> AdjustmentResult` — 純函數，可獨立 unit test
    - `build_for_symbol(stock_id)` — DB 讀取 + compute
    - `write_adjusted_to_db(stock_id, result)` — 寫 daily_price_adj + adjustment_state
    - `get_freshness_status()` — 比對 raw / event / state 找出 stale symbols

- **演算法**: canonical backward adjustment
  - `cum_factor[T] = ∏ event_factor[E]` for all events `E.date > T`
  - 除權息日當天的 raw close 已是除息後價，不再乘自己 factor
  - Polars 實作: sort DESC + `shift(1, fill_value=1.0)` + `cum_prod()`

- **`data/database.py`** v0.1.3 → v0.1.4:
  - 新增 `daily_price_adj` 表 (stock_id, date, adj_OHLC, raw_close, cum_factor, volume)
  - 新增 `adjustment_state` 表 (stock_id, last_built_at, last_event_date_used, ...)

- **`scripts/build_adjusted_prices.py`** v0.1.0 (新檔):
  - Freshness check + incremental rebuild
  - `--force` 全量重建; `--symbols` 限定範圍

- **`scripts/validate_adjustments.py`** v0.1.0 (新檔):
  - 比對 raw vs adjusted 的 abnormal returns (|pct| > 10.5%)
  - 預期 absorption rate ≥ 80% (理想 100%)
  - 含 0050 split (2025-06-18) 的 golden case 顯示

### 演算法驗證 (workspace)
用 2454 真實 events (3 個 dividend, factor 0.90953 / 0.90317 / 0.97419) 合成 8 個 raw price 點:
- ✓ 全部 8 個 cum_factor 跟手算結果精確一致 (誤差 < 1e-5)
- ✓ 跨除息日 (2022-06-22 → 2022-06-23) 的 adj_close pct 變化 = **-0.000%**
- ✓ 對應 raw pct 變化 = -9.05% (被完美吸收)

### Bumped
- `pyproject.toml` 0.1.9 → 0.1.10

### Volume 不做調整 (v0.1.10 設計決定)
- Cash dividend 不影響股數 → 不需 volume adjustment
- Split 才需要，但 v0.1 universe 罕見 (僅 0050 一次)
- 若未來加 split-heavy 股，再加 volume / cum_factor 調整

---

## [v0.1.9] — 2026-05-16 — TWSE Truth + Corporate Actions

### 觸發
1. v0.1.8 cross-source audit 確認三家 raw OHLC 完全對齊 → 架構通過
2. 第一次 audit run 出現 1 個 silent missing case → 需要 retry + logging hotfix
3. v0.1.10 dividend_adjustment 需要「除權息事件原料表」 → 必須先有 ingestion

### Added
- **`data/sources/twse_client.py`** v0.1.0 → v0.1.1
  - `company_info()` → `/opendata/t187ap03_L` (~1000+ 上市公司基本資訊)
  - `dividend_forecast()` → `/exchangeReport/TWT48U` (除權息預告)
  - `_parse_western_compact` helper (西元年 YYYYMMDD，跟 ROC compact 區別)
  - `_get_json` 加 **tenacity retry** (3 次 exp backoff 1-8s)
  - `stock_month` 當 stat ≠ "OK" 時 log warning (留 trace)
- **`data/sources/finmind_client.py`** v0.1.3 → v0.1.4
  - `dividend_result()` → `TaiwanStockDividendResult` (免費版可用)
  - 自動計算 `adjustment_factor = after_price / before_price`
- **`data/database.py`** v0.1.2 → v0.1.3
  - 新增 `company_metadata` 表 (TWSE t187ap03_L 來源)
  - 新增 `corporate_actions` 表 (歷史 + 預告共表，PRIMARY KEY (date, stock_id, kind))
- **`scripts/sync_company_info.py`** (新檔)
  - TWSE t187ap03_L → company_metadata (全量重寫)
- **`scripts/ingest_dividends.py`** (新檔)
  - Phase 1: FinMind TaiwanStockDividendResult → corporate_actions (confirmed=true)
  - Phase 2: TWSE TWT48U → corporate_actions (confirmed=false, forecast)
  - 支援 `--historical-only` / `--forecast-only` / `--symbols`

### Changed
- **`scripts/cross_source_audit.py`** v0.1.0 → v0.1.1
  - `get_twse_row` 失敗的三種情況 (TwseError / 空 DF / 該日不在月份) 各自 log warning
  - 解決上次 1 個 missing case 完全 silent 的問題
- **`scripts/validate_install.py`** v0.1.1 → v0.1.2
  - `check_twse_api()`: smoke test company_info (確認 1000+ 公司、2330 listing_date)
  - `check_finmind_dividends()`: smoke test dividend_result (確認 2330 過去 3 年有事件、factor 非 null)

### Bumped
- `pyproject.toml` 0.1.8 → 0.1.9

### Deferred
- TWSE `suspendListing` (3 個 alt path 全 302，無公開 endpoint) → v0.5+ 接 trading 層再挖
- `features/dividend_adjustment.py` → v0.1.10 (corporate_actions 原料先建好)

---

## [v0.1.8] — 2026-05-16 — Multi-source Layer A (TWSE primary for daily ops)

### 觸發
v0.1.7 部署過程中發現：
1. FinMind `TaiwanStockPriceAdj` 是 Sponsor 付費限定（免費版 register tier 拒絕）
2. TWSE 4 個 endpoint 親自驗證後發現比預想能幹（STOCK_DAY_ALL 一次全市場、MI_INDEX 含 30+ 產業類股）
3. 外部 quant review 確認「TWSE = validation layer，不是 FinMind 備胎」

→ 架構重定位：**FinMind 從 primary 降級為 historical bulk + 國際 reference；TWSE 升為 daily ops primary**。

### Added
- **`data/sources/twse_client.py`** v0.1.0 (新檔)
  - 4 個 endpoint：`daily_all` (STOCK_DAY_ALL), `stock_month` (STOCK_DAY), `indices_today` (MI_INDEX), `taiex_recent` (MI_5MINS_HIST)
  - `stock_range` helper：跨多月 historical (慢，只用於 spot-check)
  - Parser 工具：`parse_roc_compact` (民國年連月日), `parse_roc_slashed` (民國年/月/日), `parse_twse_num` (千分號 + null + 帶符號)
  - 自律 rate limit (預設 1 秒間隔)
  - `stock_month` 保留 `twse_note` 欄位（拆分日標記 `**` 是 v0.1.9 corporate_actions 表的輸入）

- **`data/sources/yfinance_client.py`** v0.1.0 (新檔)
  - `daily_price()` / `taiex()` 包 yfinance，輸出 Polars
  - 同時回傳 raw `close` 和 `adj_close` — 後者是 v0.1.9 adjustment layer 的「第三方對照」
  - Helios stock_id ↔ yfinance ticker 自動轉換 (`2330` ↔ `2330.TW`, `TAIEX` ↔ `^TWII`)

- **`scripts/cross_source_audit.py`** v0.1.0 (新檔)
  - 隨機抽樣 N 個 (symbol, date)，三家對比 OHLC
  - Divergence threshold 0.1%
  - 輸出 `cross_source_audit_YYYY-MM-DD.{json,md}`
  - `--skip-yfinance` 選項避免 Yahoo 反爬擋

- **`data/database.py`** v0.1.1 → v0.1.2
  - 新增 `sector_index_daily` 表 (date, index_name, close, change_pct)
  - 來源是 TWSE MI_INDEX
  - 給 sector rotation feature / regime detection 用

### Changed
- **`pyproject.toml`** 0.1.7 → 0.1.8
  - 新增 dep: `yfinance>=0.2.40`
- **`docs/data_sources_catalog.md`** → 重大更新
  - FinMind 角色：primary → historical bulk + 國際 reference
  - TWSE 角色：validation → daily ops primary
  - 新增「FinMind 免費版 vs 付費版」對照表

---

## [v0.1.7] — 2026-05-16 — Data Layer Hardening

### Hotfix (later same day)
- **`data/sources/finmind_client.py`** v0.1.2 → v0.1.3
  - Revert `TaiwanStockPriceAdj` → `TaiwanStockPrice`（Sponsor 限定，免費版 400）
  - adjustment ownership 移到 v0.1.9 features/dividend_adjustment.py
- **`config/universe.yaml`** 加入 10 個權值股（2330, 2317, 2454, 2412, 2308, 2882, 2891, 2881, 2303, 3711）— 永久寫入，下次 tar 解壓不會掉

### 觸發
v0.1.6 第一次跑 16-symbol × 5 年資料後，profile 結果暴露 4 個資料層問題 (詳見 `docs/data_behavior_notes.md::2026-05-16`)：
1. 全市場「missing 80 days」是 trading_calendar 過度樂觀造成的偽陽性
2. 0050 在 2025-06-18 的 1拆4 拆分造成 -74.78% 的「假跳空」
3. 2317 在 2025-07-30 出現 close=0 的 FinMind 資料汙染，造成 +inf% 漲幅
4. 6-7 月台股除權息季造成跨股大量 10%+ 跳空

### Changed
- **`data/sources/finmind_client.py`** v0.1.1 → v0.1.2
  - `daily_price()` 改用 `TaiwanStockPriceAdj` (還原權息價)，解決 dividend / split 跳空
  - TAIEX 維持 `TaiwanStockPrice` (指數本身沒 split/dividend)
- **`data/fetcher.py`** v0.1.1 → v0.1.2
  - `daily_price()` 後串接 `data.sanity.validate_ohlc` 丟壞列
  - 壞列數 + 原因併入 `FetchResult.quality_issues` 並 log warning
- **`scripts/data_quality_report.py`** v0.1.0 → v0.1.1
  - `_count_expected_trading_days()` 改用 TAIEX baseline (DB 內的實際交易日數)
  - `abnormal_returns` 計算先 `filter(close > 0)` 避免零 close 造成 +inf%
  - `fetch_arrow_table()` → `to_arrow_table()` (Polars deprecation 修)

- **`data/cache.py`** v0.1.1 → v0.1.2
  - `CACHE_SCHEMA_VERSION` 1 → 2，舊 raw price cache 自動失效，
    避免拿到舊 cache 而再次寫入 raw price (那就白做 adjustment 切換)

### Added
- **`data/sanity.py`** v0.1.0 (新檔)
  - `validate_ohlc(df)` 回傳 `SanityResult(clean, dropped_count, dropped_reasons)`
  - 規則: close/open/high/low ≤ 0 / high < low / 全 OHLC null
  - 留 audit trail 不修改價格 (不做 imputation)

### Migration (用戶必做)
舊資料是 raw `TaiwanStockPrice`，新版改抓 `TaiwanStockPriceAdj`。**必須 `--full` 重抓覆蓋**：
```bash
uv run python scripts/download_daily.py --full
uv run python scripts/data_quality_report.py
```
預期變化：
- `missing_days` 從 ~80 降到接近 0 (TAIEX baseline)
- `abnormal_returns` count 大幅下降 (還原權息已吸收除權息跳空)
- 0050 跨 2025-06-18 拆分日將不再有 -74.78% (還原價會在所有歷史日同比例下調)
- 2317 的 close=0 那列會被 sanity filter 丟掉並寫進 quality_issues

### Bumped
- `pyproject.toml` 0.1.6 → 0.1.7

---

## [v0.1.6] — 2026-05-16 — Real Data Ingestion + Systematic Profiling

### Added (Step 2.5: 採納 reviewer 建議的「資料行為理解」交付)
- **`scripts/download_daily.py`** — 機械抓取日 K 到 DuckDB
  - 從 `config/universe.yaml` 讀 symbols + 強制加 TAIEX
  - 增量更新 (依 `ingest_watermark`)；`--full` 強制重抓
  - DELETE+INSERT 模式避免 PRIMARY KEY 衝突
  - 事件記錄到 `data_quality_log`，狀態軌跡完整
- **`scripts/data_quality_report.py`** — 系統化資料 profiling (核心交付)
  - per-symbol：rows / 缺日 / 重複 / 零成交 / 最大連續 gap / 異常漲跌幅 / 漲跌停 / 流動性 tier
  - cross-symbol：TAIEX alignment / supplementary table 覆蓋率
  - 輸出 JSON (機讀) + Markdown (人讀)，含「Findings hints」自動推斷異常
- **`notebooks/01_data_behavior.ipynb`** — 視覺探索 stub
  - 含 TAIEX 200MA regime、報酬率分布、探索建議清單
- **`docs/data_behavior_notes.md`** — 累積學習檔
  - 用結構化格式累積觀察 → 成為 Step 3 (indicators) 設計需求依據

### Changed
- `scripts/validate_install.py` v0.1.0 → v0.1.1
  - 修 lifecycle bug：`fetcher.daily_price` 移入 `with` 區塊內 (原本 fetcher 已關閉)
  - 版號改為動態讀 `pyproject.toml`，避免之後忘了更新

### Bumped
- `pyproject.toml` 0.1.5 → 0.1.6
- `scripts/validate_install.py` v0.1.0 → v0.1.1 (lifecycle bug hotfix)

### 工作流程
跑通 v0.1.6 後的標準動作：
```bash
uv run python scripts/download_daily.py --full   # 抓 5 年 (~30 symbols)
uv run python scripts/data_quality_report.py      # 看數字摘要
# 開 notebooks/01_data_behavior.ipynb 看視覺
# 把發現的 patterns 整理到 docs/data_behavior_notes.md
```

---

## [v0.1.5] — 2026-05-16

### Added — 防禦性 hardening (採納外部 review)
- **`data/fetcher.py::FetchResult`** 加 `success: bool` + `error: str | None` 欄位
  - 解決「空 DataFrame 語意混淆」：success=True 空資料 (該期間無交易) vs success=False (fetch 失敗)
  - 下游應檢查 `result.success`，不再用 `result.data.is_empty()` 判斷錯誤
- **`data/sources/finmind_client.py`** 所有 return path 強制 `sort + unique`
  - daily_price / institutional / monthly_revenue / taiex / stock_info 全部加上
  - 主因：FinMind 偶爾回傳重複日（盤後 rerun）或亂序，下游不該被迫處理
- **`data/sources/finmind_client.py`** 數值欄位改用 `cast(strict=False)`
  - API 偶發 null / 空字串時轉為 null 而非整批炸錯
- **`data/cache.py`** 加 `CACHE_SCHEMA_VERSION = 1` 常數，嵌入快取檔名
  - 未來欄位語意/型別變動時 bump 版號，舊 cache 自動失效（hash 不同）
- **`data/cache.py`** 新增 trading-day-aware cache mode
  - `get_for_trading_day()` / `set_for_trading_day()`
  - 用「最後一個 trading day」當 key 一部分，跨 trading day 自動 invalidation
  - 比 TTL 更貼合 market data 性質 (盤後 14:30 後新資料才公佈)
- **`data/cache.py`** 加 `clear_old_schema_versions()` 清理孤兒舊版本檔

### Removed
- `[dependency-groups].features` (即 `pandas-ta>=0.3.14b,<0.4`)
  - 原因：pandas-ta 0.3.x 已從 PyPI 下架，constraint 無法解析
  - Step 3 開工時再評估 indicator 庫選項 (pandas-ta 0.4.x / TA-Lib / Polars-native)

### Changed
- `data/fetcher.py::daily_price` 與 `taiex` 預設 `cache_mode="trading_day"` (legacy TTL 保留)

### Bumped
- `pyproject.toml` 0.1.4 → 0.1.5
- `data/fetcher.py` v0.1.0 → v0.1.1
- `data/sources/finmind_client.py` v0.1.0 → v0.1.1
- `data/cache.py` v0.1.0 → v0.1.1

---

## [v0.1.4] — 2026-05-16

### Fixed
- **依賴問題**：`pandas-ta` (0.4.x) 與 `vectorbt` 透過 `numba` 帶入 `llvmlite`，
  在 Python 3.13/3.14 上 wheel 未跟上、source build 失敗（setuptools API 衝突）
  - `pandas-ta` 從 main `dependencies` 移到 `[dependency-groups].features`，pin `<0.4`
    避開 numba（0.3.x 是純 Python era）
  - `vectorbt` 從 main `dependencies` 移到 `[dependency-groups].backtest`
- **`.python-version`** 新增於專案根，pin Python `3.12` 讓 uv 自動選對版本
  - Python 3.14 上預編 wheel 對 numba/llvmlite 仍不完整，3.12 是最穩的選擇

### Changed
- `uv sync` 預設只裝主依賴 (Step 1+2 所需)，pandas-ta/vectorbt 等 Step 3+ 才裝
- Step 3 開始：`uv sync --group features`
- Step 6 開始：`uv sync --group backtest`

### Bumped
- `pyproject.toml` 0.1.3 → 0.1.4

---

## [v0.1.3] — 2026-05-16

### Added
- **`scripts/validate_install.py`** — 自我診斷腳本，11 項檢查覆蓋 Python 版本、套件、目錄權限、Settings、Logger、DuckDB schema、Storage 端到端、Trading calendar、(可選) FinMind 連線。`uv run python scripts/validate_install.py [--with-api]`

### Code Review 修復 (7 項)

**🔴 Bug fixes:**
- **`storage/signals.py::update_approval`** 改用 `UPDATE...RETURNING` 確保原子性
  - 修掉 UPDATE+SELECT 之間的 race window
  - 同時減少 1 次 round-trip (hot path)
- **`storage/signals.py::expire_drifted`** 改批次處理
  - 原本 N+1 query (100 pending = 200+ DB calls)，改成 1 SELECT + N UPDATE
  - 統一 log 一次，不洗 200 行
- **`storage/orders.py::has_duplicate_recent`** 新增 `exclude_order_id` 參數
  - 修掉「剛 record 完馬上 check 會把自己當 duplicate」的 API 缺陷
  - 讓 runtime 可在 record 後做事後驗證
- **`storage/positions.py::_apply_fill`** 過量賣出處理
  - 賣超過持有量時 clamp 到實際持有量 + log warning
  - 修掉假 realized_pnl（賣 2000 但只有 1000 時錯算成 10× 利潤）

**🟡 Design fixes:**
- **`market/trading_calendar.py`** DB 缺 TAIEX 資料時 log warning
  - 避免使用者誤以為 fallback 規則準確（颱風假可能被誤判為交易日）
  - 同日只 warn 一次，避免回測時瘋狂洗 log
- **`utils/logger.py`** 檔案輪轉用 `settings.timezone`
  - UTC server 上原本 log 檔以 UTC 切日，現在以 Asia/Taipei 切日
  - `_add_timestamp` processor signature 改為 `MutableMapping` 符合 structlog 介面

**🔵 Lint / Style:**
- ruff config 排除 RUF001-003（中文標點 false positive）
- 修 17 個 import 排序、5 個 `__all__` 排序、10 個 `zip(..., strict=True)`、4 個 ternary、1 個 dead variable
- 結果：`ruff check .` 全綠

### Bumped
- `pyproject.toml` 0.1.2 → 0.1.3
- `storage/signals.py`         v0.1.0 → v0.1.1
- `storage/orders.py`          v0.1.0 → v0.1.1
- `storage/positions.py`       v0.1.0 → v0.1.1
- `market/trading_calendar.py` v0.1.0 → v0.1.1
- `utils/logger.py`            v0.1.0 → v0.1.1

### 未處理 (留到 v0.1.4)
- 34 個 mypy strict 嚴格度警告 (`dict` 沒參數化、`fetchone()[0]` 沒 None 檢查、smoke test `__main__` block None access) — 不影響 runtime，留待專門的 type cleanup pass

---

## [v0.1.2] — 2026-05-16

### Changed
- **檔案命名慣例**：每個 code/config 檔案的第一行加上「相對於專案根的路徑註解」
  - 套用範圍：.py / .yaml / .toml / .env.example (共 23 個檔案)
  - 不套用：.md（自身會被閱讀） / .gitignore
- **`docs/versioning.md`** 新增「路徑註解規範」章節
- **`pyproject.toml`** 版本 0.1.1 → 0.1.2

### Note
此為全域格式統一，**未對個別檔案 bump patch** —— 它是慣例採納，非功能變更。

---

## [v0.1.1] — 2026-05-16

### Changed (Review 後升級)
- **`config/risk_limits.yaml`** 結構性重寫
  - 部位上限分 ETF (15%) / 個股 (10%)
  - 取代固定 80% 曝險 → **regime-adjusted exposure** (strong_bull 80% → crisis 0%)
  - 取代二元 `require_regime` → **regime_policy 矩陣** (5 個 regime × asset_types × size multiplier)
  - **Graduated circuit breaker** 三級門檻 (1.5% 警示 / 2% 軟降 / 3% 硬停)
  - 新增 `trade.signal_max_drift_atr` (ATR-based signal expiry)
  - `approval.timeout_minutes` 10 → 30
- **`data/database.py`** schema 升級
  - `signals` 表新增 `entry_atr DOUBLE` (ATR drift 判斷必須)
  - `signals` 表新增 `expired_reason VARCHAR` (區分 timeout / atr_drift / manual_reject)
  - `approval_status` 新增 `EXPIRED_DRIFT` 狀態
- **`config/settings.py`** `telegram_approval_timeout_min` 預設 10 → 30
- **`config/strategy_config.yaml`** 移除 `require_regime` (改由 regime_policy 處理)
- **`.env.example`** TIMEOUT 預設值同步調整
- **`README.md`** 風險與紀律段落改寫

### Added
- **`storage/`** 模組（Step 2 交付）
  - `signals.py` — signal event log + ATR drift expiry
  - `orders.py` — order event log + duplicate detection
  - `positions.py` — 從 orders 計算持倉
  - `snapshots.py` — 每日 EOD 快照 + drawdown 計算
- **`market/`** 模組（Step 2 交付）
  - `trading_calendar.py` — hybrid 交易日曆（DB + fallback holidays）
- **版號規範** — 每個檔案 docstring 內含 Version + Changelog

### Fixed
- `market/calendar.py` 與 Python stdlib `calendar` 命名衝突 → 重命名為 `market/trading_calendar.py`

---

## [v0.1.0] — 2026-05-16

### Added (Step 1 — 4 hours)
- **`config/`** — Pydantic Settings + YAML loader (universe / strategy_config / risk_limits)
- **`data/`** — DuckDB schema + Parquet cache + FinMind client + 統一 fetcher
- **`utils/logger.py`** — structlog JSON 輸出
- **`scripts/init_db.py`** — 初始化資料庫 schema + 載入 stock_info

### 架構決策
- Python 3.12+ + uv
- DuckDB 為主資料庫 (single file, columnar, OLAP-friendly)
- Polars 為主 DataFrame (pandas 輔助)
- pandas-ta 為主指標庫 (v0.1 不裝 TA-Lib)
- structlog JSON logging
- Ubuntu Server x86_64 為目標環境
- systemd 為 v0.3 排程方案 (取代 macOS launchd)
- python-telegram-bot v20+ async (Step 8)
- Human-in-the-loop semi-auto 為預設模式
