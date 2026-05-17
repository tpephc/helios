# Helios Architecture

> Last updated: 2026-05-17 (v0.1.14.1.2)
> Co-developed by Trade Agent + Claude
> Reviewer-blessed structure (see RESEARCH_JOURNAL.md for review history)

---

## §0  Identity

**Helios IS:**
- **Regime-filtered** — trades only when market structure permits
- **Trend-following** — captures persistence, not reversals or fair value
- **Portfolio-constrained** — disciplined capital allocation with sector / ETF caps
- **Medium-frequency** — 1-3 month holding period, daily-batch cadence
- **Taiwan-specific** — TWSE universe, 台股 cost model, Taiwan corporate-action semantics
- **Systematic** — deterministic rules end-to-end, no discretion at signal level
- **Human-supervised** — Telegram approval required for every entry; no autopilot

**Helios IS NOT:**
- An AI / LLM stock predictor
- A high-frequency / intraday system
- A multi-strategy alpha factory
- A research notebook
- A general-purpose trading framework
- A signal generator for someone else's execution
- A black box (every signal has reasons + audit trail)

> **Identity is the system's complexity firewall.** Every future feature must pass:
> "Does this serve a Regime-filtered + Trend-following + Portfolio-constrained + Medium-frequency + Taiwan-specific + Systematic + Human-supervised trading engine?"
> If no, it does not belong in Helios — fork it into another project.

---

## §1  Mission

A personal-grade institutional Taiwan equity trend system for medium-term holdings.

Capital scale: NTD 300k–1M (single account). Universe: 15 symbols (5 ETFs + 10 large-cap stocks). Operator: single user, manual approval workflow.

The goal is **steady risk-adjusted returns through disciplined trend capture in healthy markets and disciplined non-participation in unhealthy ones** — not maximum CAGR.

---

## §2  Why Helios is intentionally NOT HFT

> Every line below is a deliberate architecture decision. Each closes off a complexity vector.

| Property | Helios Choice | Closed-off complexity |
|---|---|---|
| Cadence | Daily batch (one cron per day) | No event loop, no websocket, no message queue |
| Latency | ~26-day average holding → seconds don't matter | No co-location, no sub-millisecond execution |
| Fill model | Close-based (T+0 close, paper trade T+1 open) | No tick data, no order-book reconstruction |
| Indicator math | Polars expressions in batch | No streaming-window state, no incremental computation |
| Regime classification | Daily snapshot of TAIEX | No real-time regime tracking, no HMM particle filter |
| Approval | Telegram, human in loop | No autopilot risk model, no kill-switch ladder |
| Decision speed | "End of trading day → review → next morning fill" | No microstructure modeling, no spread-capture logic |
| Position size | 20% of equity per name | No Kelly, no covariance optimization, no allocation solver |

**Alpha hypothesis explicitly does not depend on:**
- Microsecond execution precision
- Intraday momentum bursts
- Microstructure features (spread, depth, imbalance)
- News sentiment / NLP signals
- Real-time alternative data

**Alpha hypothesis explicitly does depend on:**
- Trend persistence over multi-week horizons
- Regime stability (bull regimes lasting weeks/months, not minutes)
- Volume confirmation at breakout (daily volume aggregate, not tick prints)
- ATR-scaled risk management (daily volatility)

**Therefore the entire HFT toolchain is dead weight for this system** — and worse, it would slowly erode operational simplicity, the actual moat.

---

## §3  Layer Map

```
┌──────────────────────────────────────────────────────────────────┐
│  Execution Layer (v0.1.14.2)             [next]                  │
│  • execution/paper_broker.py                                     │
│  • communication/telegram/                                       │
│  • scripts/daily_run.py                                          │
│  Explicit non-goals: no websocket, no async, no streaming        │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│  Portfolio Layer (v0.1.14.1)             [done]                  │
│  • portfolio/risk_budget.py     Capital constraints              │
│  • portfolio/selector.py        Sector classification            │
│  • backtest/portfolio_simulator Capital-aware lifecycle          │
│  • scripts/run_portfolio_backtest.py  CLI                        │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│  Strategy + Backtest Layer (v0.1.12-13)  [done]                  │
│  • strategies/{base,trend_breakout}.py                           │
│  • strategies/exit/{regime_exit,trailing_stop}.py                │
│  • backtest/round_trip.py                                        │
│  • scripts/{run_backtest,oos_validation,signal_audit}.py         │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│  Feature Layer (v0.1.11)                  [done]                 │
│  • features/{dividend_adjustment,technical,regime}.py            │
│  • scripts/compute_features.py                                   │
│  • Tables: daily_features, market_regime                         │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│  Data Layer (v0.1.7-10)                   [done]                 │
│  • data/{database,finmind_client,twse_client}.py                 │
│  • Tables: daily_price, daily_price_adj, corporate_actions,      │
│            company_metadata                                      │
└──────────────────────────────────────────────────────────────────┘
                                ▲
┌──────────────────────────────────────────────────────────────────┐
│  Foundation (v0.1.0-6)                    [done]                 │
│  • storage/{signals,orders,positions}.py                         │
│  • utils/logger.py (structlog JSON)                              │
│  • scripts/validate_install.py (44/44 PASS)                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## §4  Data Layer

### Sources (priority order)

| Source | Role | Status |
|---|---|---|
| TWSE OpenAPI | Daily ops primary, company metadata, dividend forecast (TWT48U) | ✓ |
| FinMind free tier | Historical bulk backfill, cash dividends | ✓ |
| Raw price detection | Split events (FinMind 不含 splits) | ✓ v0.1.10.2 |
| yfinance | Cross-validation only | ✓ available |
| TWT49U | Official adjustment ratios | ❌ deferred to v0.2 |
| MOPS | Authoritative corporate actions | ❌ HTML-form fragile |

### Tables (DuckDB) — current row counts

| Table | Rows | Owner |
|---|---|---|
| `daily_price` (raw) | 19,080 | data ingestion (never mutated) |
| `daily_price_adj` | 17,865 | features/dividend_adjustment |
| `corporate_actions` | 141 | data ingestion |
| `company_metadata` | 1,086 | TWSE t187ap03_L |
| `daily_features` | 17,865 | features/technical |
| `market_regime` | 1,215 | features/regime |

### Key data behaviors

See `data_behavior_notes.md` for full §-entries. Highlights:
- §13 FinMind 不含 splits → auto-detect from raw ratio
- §14 yfinance.splits for TW: both false positives AND missed real splits
- §15 TWT49U schema (deferred to v0.2)

---

## §5  Feature Layer

### `features/technical.py` — 9 indicators, Polars-native

- **Trend**: SMA20, SMA50, SMA200, EMA20
- **Momentum**: RSI14 (Wilder), ROC20
- **Volatility**: ATR14 (Wilder, uses adj OHLC)
- **Breakout**: Donchian20 high/low
- **Volume**: Volume_MA20, RelativeVolume20

**Single source of truth.** No duplicate indicator math anywhere else in the codebase.

### `features/regime.py` — 4-state deterministic on TAIEX

- `crisis`: vol_20 > 0.020
- `bull`: close > sma_200 AND vol_20 ≤ 0.020
- `bear`: close < sma_200 AND vol_20 ≤ 0.020
- `neutral`: transitional (crossing SMA200)

Empirically: 56.5% bull / 21.2% bear / 16.4% neutral / 6.0% crisis over 5 years.

---

## §6  Strategy Layer

### Strategy ABC (`strategies/base.py`)

```python
class Strategy(ABC):
    name: str
    @abstractmethod
    def generate_signals(self, as_of: date, symbols=None) -> list[Signal]: ...

@dataclass
class Signal:
    stock_id / signal_date / strategy / side / entry_price / entry_atr
    regime / score (0-1)
    reason: list[str]     # human-readable (Telegram-ready)
    metadata: dict        # structured (audit / AI consumption)
```

### TrendBreakoutStrategy v0.1 — 6 conditions (all AND)

1. `regime == 'bull'` (Helios's true edge)
2. `close > sma_50 > sma_200` (multi-MA trend)
3. `sma_50 > sma_50.shift(5)` (slope filter)
4. `close > donchian_20_high.shift(1)` (conservative breakout)
5. `rel_volume_20 ≥ 1.5` (volume confirmation)
6. `50 ≤ RSI ≤ 75` (momentum without overbought)

### Exit rules (`strategies/exit/`) — priority order

- **`regime_exit.py`** priority=1: regime != 'bull' → exit
- **`trailing_stop.py`** priority=2: close < max_close_since_entry - 2*ATR14

Regime exit > ATR stop. Fixed 2.0 multiplier. NO time stop.

---

## §7  Backtest + Portfolio Layer

### Round-trip (`backtest/round_trip.py`)

Unconstrained — one position per signal, capital not tracked. Used for entry/exit alpha measurement.

### Portfolio (`backtest/portfolio_simulator.py`)

Capital-aware — full daily flow:
1. Update open positions running stats with adj_close[d]
2. Exit check (priority order) → release capital to cash
3. Process today's signals (sorted by score DESC, apply constraints)
4. Record EquitySnapshot

Constraint check order: `symbol_already_held` → `max_positions` → `cash_buffer` → `etf_cap` → `sector_cap_*`

### Risk budget defaults

```python
DEFAULT_RISK_BUDGET = RiskBudget(
    max_positions=5,
    per_position_pct=0.20,
    max_etf_exposure_pct=0.40,
    max_sector_exposure_pct=0.30,
    cash_buffer_pct=0.10,
)
```

Critical: cash_buffer 10% binds before max_positions 5 → effective max ≈ 4 positions.

### Sector classification (v0.1)

Hardcoded in `portfolio/selector.py`:
- etf (5), semi (3), electronics (3), financial (3), telecom (1)

v0.2+: derive from `company_metadata.industry_code`.

---

## §8  Validation Pipeline

| Check | Tool | Frequency |
|---|---|---|
| Install correctness | `scripts/validate_install.py` | Every deploy (44/44 PASS) |
| Dividend absorption | `scripts/validate_adjustments.py` | After bulk adjust (100%) |
| Indicator readiness | `scripts/feature_inspect.py` | Daily (Step 3 exit criteria) |
| Signal audit (5 questions) | `scripts/signal_audit.py` | After strategy change |
| OOS validation | `scripts/oos_validation.py` | After strategy change |
| Round-trip backtest | `scripts/run_backtest.py` | After exit changes |
| Portfolio backtest | `scripts/run_portfolio_backtest.py` | After budget changes |

---

## §9  Operational Assumptions

> The "physics" of the system. Violate any of these and Helios is no longer Helios.

| Assumption | Implication |
|---|---|
| **Single user** | No multi-tenancy, no auth, no permissions model |
| **One run per day** (cron @ 09:00) | T-1 daily ingest → features → entry signals → exit scan → telegram |
| **Daily-batch cadence** | No intraday data, no real-time market hours awareness, no streaming |
| **T+1 settlement** | Signals fire at close[T], approval window 30 min, fill at open[T+1] (paper) |
| **Manual Telegram approval** for every entry | Operator must be reachable; if offline, signal expires |
| **Auto-exit allowed** without approval | Exit signals (regime / trailing) execute on close[T] without delay — protecting capital is the priority |
| **30-min approval timeout** + ATR drift expiry (0.5×ATR) | Stale signals self-cancel |
| **Daily loss limits graduated** (1.5% / 2% / 3%) | Circuit breaker before damage compounds |
| **Read-only DB access from scripts** | Mutations only via well-defined writers in `storage/` |
| **No internet during backtest** | All data pre-ingested; backtests must be reproducible offline |
| **Logs are append-only JSON (structlog)** | Easy grep, easy ingest, never overwritten |

---

## §10  Empirical Findings Snapshot (v0.1.14.1)

| Metric | Value | Source |
|---|---|---|
| Dividend/split absorption rate | 100% | validate_adjustments |
| Strategy hit rate (OOS 20-day fwd) | 65.1% | oos_validation |
| Round-trip PF (unconstrained, net) | 2.50 | run_backtest |
| Round-trip PF (constrained, gross) | 4.13 | run_portfolio_backtest |
| Portfolio max DD (constrained OOS) | -11.01% | run_portfolio_backtest |
| Portfolio CAGR (OOS, net) | +6.71% | run_portfolio_backtest |
| Avg portfolio exposure | 29% | run_portfolio_backtest |
| Crisis-regime signal leakage | 0 (73 crisis days) | signal_audit |
| Verdict | Substantively STRONG PASS | reviewer + user |

---

## §11  Known Limitations

### Current alpha character (these are by design, not bugs)

- **Bull-regime dependent** — strategy delivers strong PF in bull markets, near break-even in bear (regime gate compresses opportunity). This is the trade-off for catastrophic-loss avoidance.
- **Low average exposure** (29%) — capital is "lazy" 71% of the time. Trend systems with regime gating are structurally under-deployed. Sleep-well-at-night profile, not maximum-CAGR profile.
- **ETF + financial momentum bias** — top performers historically. Strategy naturally favors smooth-trending blue chips over high-beta names.
- **NOT designed for sideways markets** — chop kills trend systems. Helios will sit in cash through extended ranges (this is correct).
- **NOT optimized for high-beta semiconductor momentum** — 2454 mean -0.48% in current sample. ATR-trailing stops cut too quickly on volatile names. By design: we prefer trade exit over riding volatile drawdowns.

### Scope limitations (current implementation)

- **15-symbol universe** — not whole TWSE; expansion requires sector classification refactor (v0.2)
- **No intraday data** — close-based decisions only
- **No options / derivatives / margin** — equities long-only
- **Sector classification hardcoded** — `SECTOR_MAP` in `portfolio/selector.py` (v0.2: derive from `company_metadata.industry_code`)
- **No fundamentals layer** — purely price + volume + regime
- **No alternative data** — no sentiment, no news, no insider activity
- **No cross-asset signals** — no TAIEX futures, no USD-NTD, no commodity exposure
- **Backtest assumes close-fill** — real fills will differ at open[T+1] (paper trading will quantify this)
- **In-memory state** — long backtests (10+ years) may hit memory ceilings; current 5-year backtest is fine
- **Single broker** — Shioaji (永豐金) only; no multi-broker reconciliation

### Methodological limitations

- **5-year sample** — robust for v0.1 but limited regime variety (only one mild升息 bear in 2022)
- **TW market only** — strategy logic uses TW-specific cost / regime / volume thresholds
- **No regime transitions backtested in stress** — 2008 / 2020 March crash NOT in sample
- **Sector classification fixed in time** — companies that change business model NOT reclassified

---

## §12  Future Roadmap

### v0.1.14.2 — Paper Trading Execution (next)

**Goals:**
- `execution/paper_broker.py` (simulated fills, T+1 settlement, cost model)
- `storage/positions.py` integration (approved signal → positions table)
- `scripts/daily_run.py` (cron pipeline)
- `communication/telegram/sender.py` (push signals + receive approvals)

**Explicit non-goals (per reviewer + ADR-001):**
- ❌ No websockets / streaming
- ❌ No async runtime / event loop
- ❌ No distributed scheduler (single cron, single host)
- ❌ No real-time market data subscription
- ❌ No order-book modeling
- ❌ No autopilot (human approval is the contract)

### v0.1.15+ — Live trading prep

- Shioaji broker integration (read-only first, paper-validated)
- Reconciliation pipeline (broker state vs internal positions table)
- Graduated daily-loss circuit breakers
- 3+ months paper trading record before any real money

### v0.2 — Data + corporate actions polish

- TWT49U integration (official adjustment ratio cross-check)
- corporate_actions confidence engine (multi-source agreement)
- raw_payload preservation for audit
- Sector classification from `company_metadata.industry_code`

### v0.3+ — Strategy depth (only if v0.1 validated in paper)

- Sector relative strength (when sector_index_daily ingested)
- Multi-strategy framework (mean-revert variant for sideways markets)
- Per-strategy regime sub-classification

### v0.4+ — Real money (only after v0.3 stable in paper)

- Telegram approval flow tested in production
- 3+ months paper record meeting thresholds
- Risk limit enforcement battle-tested
- Explicit go/no-go review with reviewer

### v1.0 — Production stable

---

## §13  Hard Rules (Never Violate)

- Real-money trading **forbidden** until v0.4+
- `.env` **never** committed
- `daily_price` (raw) **never** mutated
- `requires-python = ">=3.12"` (lock 3.12)
- `ruff check .` must pass before tarball
- Single source of truth for indicator math (`features/technical.py`)
- Single source of truth for regime classification (`features/regime.py`)
- Every signal must have `reason` list + `metadata` dict
- No ML / DL / Kelly / HRP / risk parity in v0.1 (see ADR-005)

---

## §14  Decision Records

Major architectural decisions are recorded in `docs/decision_records/` (ADR format).

Current ADRs (read in numbered order to understand Helios's design):

- **ADR-001** — No HFT / intraday infrastructure
- **ADR-002** — Polars-native indicators (no TA-Lib / pandas-ta)
- **ADR-003** — Portfolio layer before paper trading
- **ADR-004** — Human Telegram approval required for entries
- **ADR-005** — Deterministic regime over HMM/ML
- **ADR-006** — Cohesion over abstraction in v0.1

When proposing significant changes (new layer, new dependency, new abstraction), write a new ADR first. If the ADR can't be written cleanly, the change probably doesn't belong in Helios.
