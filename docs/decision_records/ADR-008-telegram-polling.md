# ADR-008: Telegram polling over webhook

**Status**: Accepted
**Date**: 2026-05-17
**Version**: v0.1.14.2-b

## Context

For the human approval flow required by ADR-004, Helios needs to receive operator
responses (`/approve <id>`, `/reject <id>`) from Telegram. The Telegram Bot API
offers two delivery mechanisms:

**Option A: Webhook**
- Telegram POSTs updates to a public HTTPS URL when they arrive
- Requires: public IP, TLS certificate, reverse proxy, long-running web server
- Latency: ~instant
- Always-on listener

**Option B: Long polling**
- Bot calls `getUpdates?timeout=30` synchronously; Telegram holds connection up to 30s
- No inbound infrastructure required
- Latency: 0-30s typical
- Listener can be ephemeral (run only during approval window)

Helios is a daily-batch system running on a single home/cloud machine without
public-facing infrastructure. ADR-001 explicitly rejects webserver / always-on
listener patterns.

## Decision

**Helios uses Telegram long polling, not webhooks.**

Implementation:
- `communication/telegram/bot.py` wraps `requests` calls to Bot API (no SDK dependency)
- `communication/telegram/listener.py` polls `getUpdates` in a 30-min window
  triggered from `daily_run.py` Step 5 (after entry signals pushed)
- After 30 min the listener exits; any remaining pending signals are expired by
  `execution/expiry.py` on next `daily_run` invocation

## Consequences

**Positive**
- Zero inbound infrastructure: no public IP, no TLS, no reverse proxy
- Listener is ephemeral — starts when needed, exits cleanly
- Process model matches ADR-001 (daily batch, no always-on server)
- Trivially testable: mock `getUpdates` responses, no network setup
- Operates behind NAT / firewall transparently

**Negative**
- 0-30s latency on approval response (vs. webhook ~instant)
- Approval window must be bounded (30 min default) — operator can't approve at
  3am if listener already exited
- Listener consumes process memory during its 30-min run

**Risks**
- Telegram rate-limits getUpdates if too aggressive. **Mitigation**: long-poll
  timeout=30s means ~1 request per 30s during quiet periods, well within limits.
- If `daily_run` runs before market open and operator works during market hours,
  approval window must be timed appropriately. **Mitigation**: configurable
  listener duration; operator schedules cron to match availability.

## Why not python-telegram-bot library

Considered but rejected:
- One additional dependency for ~80 lines we'd write ourselves with `requests`
  (which is already a dependency)
- python-telegram-bot is async-first (recent versions), conflicting with ADR-001
  synchronous-only stance
- Per §0.5 Simplicity Doctrine three-test:
  1. **Alpha contribution**: zero — it's plumbing
  2. **Operational necessity**: no — `requests.get/post` is sufficient
  3. **Maintenance sustainability**: each new dep is forever-cost; this one we'd
     own for years to save ~80 LOC

## Alternatives considered

1. **Webhook + ngrok/cloudflared tunnel** — rejected. Tunnel adds operational
   surface (auth, tunnel-uptime, ngrok TOS), violates "no inbound infra".
2. **python-telegram-bot library** — rejected (above).
3. **Email-based approval** — rejected. SMTP polling is uglier than Telegram
   polling, and SMTP message ordering is unreliable for paired /approve commands.
4. **Always-on listener daemon (systemd)** — rejected. Violates ADR-001 daily-
   batch model; introduces uptime / restart / log-rotation concerns.

## Forever-rule

If a future feature proposes webhook delivery, real-time inbound events, or any
always-on listener pattern, it requires a new ADR that supersedes ADR-008 with
explicit reasoning about where the latency improvement contributes alpha (it
won't for a 26-day average-holding-period trend system).

Until then: **polling is sufficient, and sufficient is better than fancy**.
