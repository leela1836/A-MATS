# Trading-agent remediation — 2026-09-27

The engineering defects can be fixed. Positive returns every month cannot be
guaranteed, and this work does not establish a profitable strategy.

## Implemented

- One continuous paper account supplies portfolio, fills and marked equity to the
  APIs and dashboard export. Research ideas remain explicitly separate. Missing
  account data is unavailable, rather than a fabricated starting balance or return.
- Realized P&L deducts commissions once; realized plus unrealized reconciles to
  equity minus starting cash. Monthly returns use each month's opening equity.
- Daily, monthly and peak-drawdown limits persist across restarts. Entry controls
  enforce shared cash, reserve, position caps and stop risk. Holding-period exits
  are active. A stale quote cannot create a fill; missing holding marks block entries.
- Backtests handle entry-bar protection, opening gaps and next-open signal exits.
  The strategy lab now replays one shared-capital portfolio with frozen rules,
  rather than pooling independently funded trades across stocks.
- ML labels use net returns without double-charging backtest costs. Chronological
  splits keep simultaneous timestamps together and purge overlapping outcome windows.
  Training writes candidate files; neither a new model nor a positive research
  score automatically promotes itself to active trading.
- Upstox is the default data adapter, using the existing account. No FYERS account
  or paid LLM is required. The collector preserves Indian trading dates; legacy
  daily caches with the old naive-UTC timestamps are repaired on read.
- Legacy scan execution is disabled by default; scans continue to generate research
  ideas. This prevents stale daily scan prices becoming a second paper account.

## Verification

- Python suite: 225 passed. One existing FastAPI/httpx deprecation warning.
- Frontend TypeScript check passed; Python dependency consistency check passed.
- Existing Upstox token authenticated: 495 daily bars, latest completed session
  September 25, and a successful WebSocket connection. The September 27 closed-market
  snapshot was stale and unsuitable for a paper fill. No broker orders were sent.
- Historical validation: `python -m app.backtester.validate_cached` uses only the
  local cached universe and writes `data/validation-corrected.json`. It freezes
  mean reversion and evaluates the chronological tail with shared capital.

The corrected replay across 49 cached stocks produced **-5.11%**, ending at
**INR 94,890.25** from INR 100,000, with **39 closed trades**. January, February,
March, June and July were losing recorded months; May was flat. December and August
are boundary periods, and all monthly rows retain the coverage-review flag.
TATAMOTORS.NS was missing from the local cache. These results reject a claim of
consistent monthly profits for the current strategy; parameters were not tuned
to turn this validation positive.

## What remains unproven

The historical cache was used in earlier research; its tail is not an untouched
forward test. The current universe can contain survivorship bias. Daily-bar replay
cannot recover tick ordering, uses conservative stop-first handling, and the real
order-spacing guard permits at most one simultaneous opening entry per day.
Open positions stay marked at the last available close rather than being silently
discarded. Full execution is assumed; costs are flat commissions and slippage,
not a complete Indian tax/fee, order-book, settlement or corporate-action model.

Market-open fresh-tick execution still needs observation. Months are marked partial
until session coverage is reviewed. A halt needs review; it never silently resets
to erase losses. Stop fills can exceed the configured loss threshold after gaps.
Software stops cannot protect holdings while the process or feed is unavailable.

The active historical model and stored strategy roster were retained for traceability;
their presence is not approval or evidence of edge. Before any real-money consideration,
freeze a candidate and evaluate a new prospective paper period against a matching
benchmark, recording costs, drawdown and losing months without tuning on that period.

See [runner setup](realtime-paper.md). The runner is not installed as a background
service; starting it requires keeping the local process running.
