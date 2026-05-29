# Helios Research Roadmap

## Completed
- [x] Phase 0: Feature outcome baseline
- [x] Phase A: Trend quality (distance/slope/spread) — mostly RS proxy
- [x] Per-horizon spacing fix (v4)
- [x] Distance refinement → pullback entry confirmed

## Next
- [ ] **trend_pullback_v1 strategy** — implement RS_T3 + dist<0 + regime≠bear
- [ ] **Phase B: Bearish research** — mirror Phase A for short side
  - [ ] Bearish interaction study (RS_T1 × dist_below × beta)
  - [ ] Bounce fade validation (RS_T1 + above MA20)
  - [ ] RS_T1 trap analysis
  - [ ] Production screener: find_bearish_bounce_fade.py

## Dropped
- [x] ~~Absorption refinement~~ (overturned by v4 spacing fix)
- [x] ~~Compression × RS~~ (no edge)
- [x] ~~Volume breakout × RS~~ (no edge)
