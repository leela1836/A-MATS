# Trader review — 2026-09-27

This is the pre-remediation audit. See [the remediation record](remediation.md)
for subsequent fixes, validation results, and the remaining limitations.

## Verdict

Subjective rating: **4/10 as an autonomous trading system**, **6/10 as a paper
research prototype**, **2/10 for demonstrated trading edge**. These are engineering
and research judgments, not estimated probabilities of success. The current record
does not justify a positive-every-month expectation or deployment with real money.

Scope: reviewed local code, the read-only SQLite journal, saved strategy roster,
model metadata, portfolio file and earlier research notes. No new backtest, live
market connection or trading was performed for this review. The preceding change
had 210 passing tests; test success does not establish profitability.

## Measured evidence

Local journal: 178 decisions, first entry July 27, last entry September 21; equity
snapshots continue through September 25. There are 167 closed directional ideas,
one open short idea and 10 closed HOLD decisions.

Across the 167 closed ideas:

- Mean gross price return: -0.108% per idea.
- Mean net return under the journal's 0.20 percentage-point round-trip allowance:
  **-0.308% per idea**.
- Net winning fraction: **40.72%**.
- Net profit factor: **0.66** (sum of positive net returns / absolute sum of negative
  net returns; equal fixed notional assumption).
- Trend-following: 65 closed ideas, about **-0.938% net per idea**; already benched.
- The other 102 closed ideas have no strategy tag. The stored journal therefore
  cannot establish the promoted mean-reversion strategy's live performance.
- The roster's mean-reversion `live_trades` is zero. Its +0.22 backtest-edge field
  is a stored research claim, not independently revalidated in this review.
- Saved validator: AUC 0.5911 on a temporal holdout from 167 total examples. AUC is
  a ranking metric, not evidence of net portfolio profitability.

### Monthly reconstruction, not actual portfolio returns

Using exactly the journal chart's assumptions: initial capital Rs 100,000, fixed
Rs 10,000 per closed idea, and 0.20 percentage points cost per idea. Grouped by
recorded exit timestamp converted to IST. Monthly percentage uses reconstructed
opening equity, without compounding individual position sizes.

| Recorded period | Closed ideas | Modeled net P&L | Modeled monthly return |
| --- | ---: | ---: | ---: |
| July 2026, partial | 24 | -Rs 355.50 | -0.36% |
| August 2026 | 122 | -Rs 2,986.90 | -3.00% |
| September 2026, partial | 21 | -Rs 1,801.10 | -1.86% |

Reconstructed ending equity: Rs 94,856.50 (-5.14% from starting capital).
These are realized-only research calculations; they exclude the open idea's
unrealized P&L, do not reconcile cash and positions, and must not be reported as
audited account returns. Recorded exit timestamps can be resolution times rather
than the precise historic bar on which a level was hit, so month attribution also
requires care. Two partial months and one full month are insufficient to estimate
a stable probability of positive months.

## Findings in priority order

1. **Performance accounting is not a self-financing portfolio.**
   `app/journal/store.py:398` reconstructs equity from fixed-notional closed ideas.
   Up to 30 directional ideas overlap by their recorded entry/exit timestamps:
   10% allocation each implies up to 300% of starting capital, inconsistent with
   the configured 1x leverage and five-position limit. The local broker file has
   zero trades and Rs 100,000 cash; recent raw equity snapshots also show Rs 100,000.
   Research ideas, synthetic chart returns and actual paper fills are different
   records. They need reconciliation before monthly profitability is measurable.

2. **Existing strategy validation has execution biases.**
   `app/backtester/engine.py:147` opens pending trades after the bar's protective
   exit check, omitting stop/target checks on the entry bar. At line 199, a signal
   calculated using the close exits at that same close, despite a comment promising
   next-open execution. `_check_exit` fills stops at their exact levels even when
   the next open gaps through them. These affect the credibility of historical
   results and labels; the direction and size of the total bias need remeasurement.

3. **The strategy lab is not an independent out-of-sample portfolio validation.**
   `app/backtester/strategy_lab.py` evaluates signals and entries at the same close,
   uses exact stop-level fills and substitutes trailing extrema for the live
   support/resistance implementation. It bypasses liquidity/regime gates and pools
   trade returns across symbols without a shared capital budget. The implementation
   has no explicit chronological train/validation/test partition despite its
   out-of-sample wording. The mean-reversion edge claim needs a stricter retest.

4. **Monthly settings are declarations, not controls.**
   `target_monthly_return_percent: 5.0` and `max_monthly_loss_percent: 8.0` occur in
   `configs/trading.yaml` but are not read by application trading logic. The new
   continuous runner has daily-loss and peak-drawdown controls, not monthly ones.
   Even an implemented monthly stop could limit intended exposure; it cannot
   guarantee its threshold during gaps/outages or turn a losing month positive.

5. **Retraining is not a demonstrated improvement process.**
   The journal labels gross wins rather than cost-adjusted wins. `app/ml/learn.py:100`
   replaces the saved model after fitting without requiring improvement in net
   return, calibration or a separate prospective evaluation. Entry-date splitting
   alone does not purge overlapping trade-label horizons. The modest saved AUC
   and small dataset do not support automatic promotion to a profitable system.

6. **Real-time execution remains unvalidated end to end.**
   The new runner improves freshness checks, persisted protection, sizing and loss
   halts, but currently needs FYERS credentials the user does not want to obtain.
   An Upstox adapter using existing access is still needed. There is no verified
   market-session record from the new runner. Full costs, partial fills, corporate
   actions and exchange circuit constraints remain simplifications.

## What is worth retaining

The modular data/strategy/execution structure, offline tests, explicit recognition
of failed strategies, strategy benching, separate paper mode, and new timestamp,
risk and persistence checks form a useful research base. Avoid adding more agents
or model complexity until measurement and execution agree.

## Recommended order of work

1. One persistent paper account as the accounting source of truth. Log actual
   simulated fills, costs, cash, positions and daily marked equity; retain research
   ideas separately. Monthly P&L must include unrealized losses and any cash flows.
2. Fix replay timing, entry-bar exits, gap fills and cost modeling. Validate the
   exact deployed strategy and risk rules with shared portfolio capital.
3. Re-evaluate mean reversion on unseen chronological periods, multiple market
   regimes and the full intended universe. Purge overlapping labels and retain an
   untouched final test period. Compare net return and drawdown with cash and a
   consistent investable benchmark. Reject strategies lacking a defensible edge.
4. Add a persisted month-opening equity baseline and monthly loss circuit breaker.
   Select risk limits before testing and keep them fixed. Position size must reflect
   stop distance, costs, correlation and total portfolio risk. Never increase risk
   or postpone recognition of losses to force a green month.
5. Connect existing Upstox data access and accumulate prospective paper results
   using frozen strategy/model versions. Report positive-month fraction, worst
   month, maximum drawdown, net expectancy, profit factor and benchmark difference.
   Include flat/no-trade months honestly. Several months can reveal defects;
   evidence across different market regimes is needed for stronger claims.

The defensible objective is **positive net expectancy with controlled drawdowns
and improving monthly consistency**. Positive every calendar month is not a
guarantee that a risky NSE trading algorithm can deliver. SEBI's investor education
also cautions against assured or near-certain return promises:
https://investor.sebi.gov.in/spot-any-scam.html

No strategy, model, risk setting or account state was changed during this review.
