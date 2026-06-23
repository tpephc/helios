# BACKLOG-CORP-ACTIONS-MULTI-SOURCE-001

**Title:** corporate_actions table contains multi-source duplicate rows
           for some (stock_id, date) keys
**Status:** OPEN
**Priority:** Medium
**Owner:** TBD (Helios platform, not Track C)
**Created:** 2026-06-22 (via Track C Step 1-0C anchor verification)
**Track C linkage:** Track C makes no claim about which source wins.
                     PIT-8 sanity check is kind-agnostic and
                     existence-only.

## Finding

The `corporate_actions` table has primary key `(date, stock_id, kind)`,
which legitimately allows multiple rows per `(stock_id, date)` from
different sources. Concrete example surfaced during Step 1-0C anchor
verification on 2026-06-22:

```
2540 / 2022-09-19 / 權息  / adj_factor=0.5918666666666667 / finmind_dividend_result
2540 / 2022-09-19 / split / adj_factor=0.5333333333333333 / auto_detected_price_drop
```

The two sources disagree on the adjustment magnitude by approximately
5.9 percentage points (not rounding-equivalent). Three questions arise:

1. **Which row is canonical for adj_close computation in
   `daily_price_adj`?** Unknown from current documentation.
2. **How widespread is this pattern?** A repo-wide query across the
   1,106 rows in corporate_actions has not been run.
3. **Should `features/dividend_adjustment.py` enforce
   single-source-per-event or formally combine multi-source records?**

## Risk Assessment

**Potential lineage ambiguity:**
- `daily_price_adj.adj_close` may be derived from one row but not the
  other, with no auditable resolution policy
- If the dividend-adjustment pipeline later changes its tie-breaking
  rule, historical `adj_close` values change silently
- Phase 1–6 research artifacts depend on `adj_close`; any silent
  shift is a lineage regression

**No identified P0** because current research has consistently used
whatever `daily_price_adj` produces. The risk is latent, not active.

## Action Plan

### Phase A — Survey

1. Count `(stock_id, date)` pairs with multiple corporate_actions rows
2. Quantify the magnitude distribution of source-to-source
   disagreement
3. Cross-reference against `adjustment_state` table (if exists) to
   determine which row was actually applied historically

### Phase B — Specify

Add a deterministic resolution policy to
`features/dividend_adjustment.py` (or its successor). Options:
- Prefer `finmind_dividend_result` over `auto_detected_price_drop`
  (preference order documented)
- Combine when kinds are non-overlapping (e.g. 權 + 息 = 權息)
- Other documented strategy

Document the policy with worked examples including the 2540
/ 2022-09-19 case.

### Phase C — Audit historical adj_close

For events where the new resolution policy would produce a different
adj_factor than what was applied historically, decide:
- Backfill: rebuild adj_close, invalidate downstream Phase 1–6
  artifacts that depend on the changed values
- Grandfather: lock historical values, apply new policy only to
  future ingestion

This decision has lineage implications for all R8 research and must
be coordinated with active research streams.

## Track C Boundary

Track C Step 1 (ud_ratio_21d) MUST NOT:
- Choose between multiple corporate_actions rows
- Make any claim about which is canonical
- Implement any tie-breaking logic

Track C Step 1 MUST:
- Use whatever adj_close the view provides (per spec §4.1)
- Sanity-check anchor existence kind-agnostically (PIT-8 fixture)

## Acceptance Criteria

- [ ] Phase A survey output committed to
  `docs/audits/corp_actions_multi_source_audit.md`
- [ ] Phase B resolution policy specified and implemented
- [ ] Phase C decision documented; if backfill, downstream artifacts
  re-validated

## References

- `corporate_actions` PK = `(date, stock_id, kind)` (see
  `data/database.py`)
- `features/dividend_adjustment.py` (current adjustment pipeline)
- Track C spec §4 (`docs/features/ud_ratio_21d_spec.md` v0.1.4)
- Concrete example: 2540 on 2022-09-19 (verified 2026-06-22)
