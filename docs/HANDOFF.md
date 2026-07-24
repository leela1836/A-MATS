# A-MATS — Handoff

**Last updated:** 2026-07-25 · **Branch:** `master` · **Head:** `7b441e0` · **Tests:** 158 passing

Autonomous, self-learning multi-agent **paper-trading** system for the Indian
market (NSE). LangGraph orchestration, Gemini reasoning, in-app INR paper
trading, a numpy trade-validator that retrains on its own results, a universe
screener, a persistent journal, and scheduled cloud runs. **Verdict up front:
it does not beat buy-and-hold** (exhaustively tested — see §1) — run it as an
autonomous learning/analysis platform, not an alpha engine.

---

## 1. The one thing to know first

**The strategy is not profitable — and the decisive test is that NOTHING we
built beats BUY-AND-HOLD.** Fair weekly test, same 5y window, 48-symbol
universe, benchmarked properly:

| arm | mean return | mean max DD | beats buy&hold |
|---|---|---|---|
| **buy & hold** | **+94.8%** | 33.9% | — |
| baseline (weekly) | −0.0% | 4.2% | 5/48 |
| Weinstein (weekly) | +0.2% | 3.2% | 6/48 |

Every "positive" result along the way (6-symbol Weinstein +0.36%, weekly
`max`-history +19.9%) evaporated under a fair benchmark. On a like-for-like 5y
window the active strategies return ≈0% while just holding returned +94.8%.
Their only virtue is low drawdown — because they sit in cash. **Do not re-chase
timing signals on NSE large-caps; buy-and-hold beats them.** The only honest
avenues left are genuinely different: cross-sectional/relative-strength
selection (pick the strongest names, not time the market), shorting in bear
regimes, or accepting the agent's job is analysis/education, not alpha.

**Mid-cap dispersion hypothesis — ALSO tested, ALSO failed.** Fair weekly test,
5y, 45 mid-caps vs buy-and-hold: B&H +156.6% (dispersion −44%..+614%), baseline
+1.1%, weinstein +2.4% — each beats B&H on only 6/45. The dispersion is real but
the strategies don't capture it; buy-and-hold dominates even harder than on
large-caps. Timing/screening adds no value on Indian equities, large OR mid cap.
The remaining honest path is cross-sectional selection or reframing as
analysis/education — NOT more timing variants.

**Cross-sectional momentum — tested; the CLOSEST, but still not usable.** 94
names (large+mid), monthly rebalance, 12-1 momentum, top quintile, net of costs:
| approach | CAGR | maxDD |
|---|---|---|
| momentum top 20% | +18.5% | 25.0% |
| market (equal-wt hold all) | +18.0% | 18.5% |
| momentum bottom 20% | +17.6% | 19.7% |
Ordering is correct (top>market>bottom = a real momentum effect), and it's the
FIRST arm to beat the benchmark — but by only +0.5pp CAGR, with HIGHER drawdown,
so risk-adjusted it's not better. Top-minus-bottom spread +0.9pp (a real momentum
market shows 5-15pp). Everything ≈+18% CAGR because the market ripped — that beta
is the whole story.

**FINAL VERDICT of the alpha search: across timing (daily/weekly, EMA/RSI,
Weinstein, filtered), large- and mid-cap, and cross-sectional selection, NOTHING
meaningfully beats holding a diversified basket on Indian equities 2021-2026.
Selection is the right family (momentum ordering is correct) but the edge is
negligible on this universe/period. Honest paths: (a) run the system as the
autonomous paper-learning / analysis / education platform it genuinely is, or
(b) if pursuing momentum, do it properly — NIFTY 500, multi-regime history (not
just a bull run), long-short — expecting a small edge at best.**

Historical note — infrastructure is solid and well-tested; the *signal* is weak.
Early daily measurement over 5 years on six NSE large-caps:

| | mean return / symbol | trades |
|---|---|---|
| without regime filter | −3.004% | 375 |
| with EMA200 regime filter | −2.764% | 335 |

Better on 4 of 6 symbols, but +0.24pp on a 6-name sample is within noise.
Simple EMA/RSI trend-following does not appear to work on Indian large-caps.

Do not add more agent layers expecting profit to appear. Better inputs make
the agent *smarter about a losing strategy*. Profitability is a separate,
unsolved problem.

**Update 2026-07-24 — two measured filters now move it toward break-even,
still not past it.** A/B over the same six large-caps / 5y (mean return/symbol):

| arm | mean ret/symbol | trades | note |
|---|---|---|---|
| baseline | −3.21% | 339 | |
| candlestick gate | −1.01% | 175 | +2.20pp — the workhorse |
| learned NN validator (alone) | −2.71% | 308 | +0.50pp — gentle, low-coverage |
| **NN + candlestick** | **−0.13%** | 132 | +3.08pp — best arm, ≈break-even |

The NN validator (`app/ml/`) is a pure-numpy MLP that scores each candidate
entry P(win) and vetoes the weakest. It has **genuine out-of-sample skill**:
AUC **0.62** on the newest 30% of trades (temporal split), beating both
coin-flip and a logistic baseline (0.45). But the portfolio numbers above for
the *full 5y* are ~70% in-sample and therefore optimistic; the clean OOS
evidence is the per-trade lift (win 36%→40%, mean ret +0.10→+0.67 per trade).
Bottom line unchanged: filters stop the worst bleeding, they do not create a
profitable edge.

**Update 2026-07-24 (later) — Weinstein Stage Analysis: a lead that did NOT
survive validation. READ THIS BEFORE RE-CHASING IT.** A mechanical
trend-following system (`app/strategies/weinstein.py`): buy Stage-2 breakouts
above the base on expanding volume above a rising 150-day MA, let winners run.

On **six** large-caps it looked like a breakthrough — the first *positive* arm:
| arm (6 symbols, 5y) | mean/symbol | trades |
|---|---|---|
| baseline EMA/RSI | −3.21% | 339 |
| weinstein (let run 2/6 ATR) | **+0.36%** | 74 |

Then validated on the **full 49-symbol universe** — and the edge evaporated:
| arm (49 symbols, 5y) | mean/symbol | trades | positive |
|---|---|---|---|
| baseline EMA/RSI | −1.32% | 2638 | 17/49 |
| weinstein (2/6) | **−0.66%** | 587 | 21/49 |
| weinstein 1st half | −0.01% | 246 | 25/49 |
| weinstein 2nd half | −0.76% | 216 | 10/49 |

⚠️ **Lesson (do not forget): a 6-symbol backtest is NOISE.** The +0.36% was
selection luck — those six happened to hold Weinstein's winners. At scale it is
−0.66% (better than baseline by only +0.66pp), **not** positive, and unstable
across time (okay-ish first half, worse second half). Zero symbols reach the
20-trade meaningfulness bar. What is *genuinely* true: Weinstein is a better,
far more efficient base than EMA/RSI (+0.66pp, 21 vs 17 positive, one-fifth the
trades) — quality up, but still not an edge. **Always validate on the whole
universe, never on a handful.** The universe screener (`app/journal/screener.py`)
exists partly for this.

**BUT — stacking the filters on Weinstein reaches ≈break-even at universe scale
(the best broad result yet).** Weinstein + NN + candlestick gates, 46-symbol
universe / 5y:
| arm | mean/symbol | trades |
|---|---|---|
| weinstein alone | −0.60% | 553 |
| + NN gate | −0.15% | 279 |
| + candlestick gate | −0.27% | 186 |
| **+ both** | **−0.009%** | 97 |

From baseline −1.32% to **−0.01%** (≈flat) is ~+1.3pp — losses almost fully
eliminated at scale. STILL NOT POSITIVE, and thin (~2 trades/symbol; 97 pooled).
Before trusting: (a) the NN was trained on BASELINE entries, so gating Weinstein
with it is out-of-distribution — **retrain the NN on Weinstein trades**; (b) no
walk-forward on the exit width. Honest levers to cross zero: NN retrained
in-distribution, walk-forward exit tuning, or a universe/timeframe where trends
persist (mid-caps, weekly). This is the most promising thread — pursue as
*research*, validated on the whole universe, never on 6 names.

**Update 2026-07-24 (later still) — three follow-ups; two dead ends, one live
lead.** All universe-wide.
- **#1 Retrain the NN on Weinstein entries (in-distribution): FAILED.** OOS AUC
  **0.510** (coin-flip; the logistic baseline 0.535 edged it). The stack stays
  ≈break-even either way (baseline-NN +0.06%, weinstein-NN +0.03%). Features
  don't separate Weinstein winners from losers — retraining doesn't help.
- **#2 Walk-forward the exit width: FAILED robustness.** The exit that looks
  best in the older half is the WORST in the newer half (3/9 ATR: +0.28% H1 →
  −1.00% H2; 2/6: −0.01% → −0.76%). Classic overfit / regime-dependence. No
  exit width generalizes; daily Weinstein is not stable.
- **#3 Weekly bars: the ONLY live lead.** On weekly, BOTH baseline (+19.9%) and
  Weinstein (+16.8%) go positive, 41/48 symbols up. ⚠️ NOT yet trustworthy:
  used `max` history (not 5y), NO buy-and-hold benchmark, survivorship. +20%
  over ~20y ≈ 1%/yr and likely lags buy-and-hold. **Decisive next test: weekly
  on a FAIR 5y window vs buy-and-hold.**

**Conclusion: stop tuning the DAILY large-cap strategy — it tops out at
break-even and every refinement fails or overfits. The signal was never the
core problem; the TIMEFRAME is. Pursue weekly (and/or mid-caps) with a fair
benchmark.**

Infra: `fetch_history` now disk-caches OHLCV to `data/cache/` on the D drive —
~40x faster on repeats and serves stale data when Yahoo rate-limits, so
universe sweeps stop flaking.

---

## 2. Run it

```bash
cd d:/Trade

# backend  (Windows: always use the venv python explicitly)
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# frontend
cd frontend && npm run dev        # http://localhost:3000

# tests  (fully offline — never spends API tokens)
./.venv/Scripts/python.exe -m pytest tests/ -q
```

**Windows gotcha:** prefix scripts with `PYTHONIOENCODING=utf-8` when printing
model output, or unicode (`→`, `₹`) raises `UnicodeEncodeError` on cp1252.

### Deploy the autonomous agent (no human in the loop)
The agent runs itself via GitHub Actions (`.github/workflows/scan.yml`) — on
GitHub's servers, laptop off. Each run: screen the universe → reason (LLM on the
top picks if enabled, else deterministic) → paper-trade with a 30% drawdown
survival guard → journal every decision with its features → resolve open trades
to win/loss → (Friday post) retrain the validator on its OWN closed trades →
commit journal + model back. It is BUILT but not DEPLOYED until you:

1. Create a GitHub repo and `git push` this code.
2. **Settings → Actions → General → Workflow permissions → Read and write**
   (so the run can commit the journal + learned model back).
3. Done — it runs at **08:45 / 11:30 / 15:45 IST**, Mon–Fri. The **11:30
   mid-session** run is inside NSE hours, so the paper broker actually FILLS
   there; pre/post journal + resolve + learn. Trigger once via **Actions → Run
   workflow** to smoke-test. Deterministic → needs NO secrets, NO cost.
4. To turn on real LLM reasoning: add repo secret `GOOGLE_API_KEY` and set
   `SCAN_LLM_TOP` (e.g. `3`) in the workflow — the LLM then reasons on the top N
   picks per scan, within the ~20/day quota. (News sentiment also uses the key
   per finalist, so keep `top_n` modest if you enable this.)

Journal/learning are independent of the paper broker: the journal opens/tracks/
resolves/learns from decisions regardless of market hours; only broker FILLS are
hours-gated. Escape hatch to fill any time: `scheduling.trading_hours_only:
false`. Locally you can drive the same loop: `POST /screen` / `POST /learn`, or
`python -m app.journal.scan` (env `SCAN_MODE`, `SCAN_LLM_TOP`, `SCAN_SESSION`).

### API surface
| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /config/{agent\|risk\|market\|trading\|news}` | config introspection |
| `POST /run/{symbol}` | one full trading cycle (e.g. `RELIANCE.NS`) |
| `POST /backtest/{symbol}?period=5y` | historical replay + metrics |
| `GET /portfolio` · `GET /trades` · `POST /portfolio/reset` | paper account |
| `GET /market/status` | NSE session state (IST) |

---

## 3. Pipeline

```
START ─┬─> market (yfinance NSE + pandas indicators)  ─┐
       └─> news   (media RSS + NSE filings)           ─┴─> reasoning (Gemini)
                                                             │
   evaluation gate ──> risk (+ASM screen) ──> decision ──> execution (paper)
        │ halt              │ halt                            │ market-hours gated
        └──> END ───────────┴──────────────────────────────────┘
```

`market` and `news` run **concurrently**; `reasoning` joins them. `AgentState`
carries reducers (`operator.add`, `merge_metrics`) so parallel nodes don't
conflict writing shared keys.

### Layout
```
app/
  collectors/market_collector.py   yfinance + EMA/RSI/ATR + classify()
  collectors/news_collector.py     RSS w/ DOMAIN ALLOWLIST
  collectors/nse_official.py       holidays, ASM, filings, market state
  strategies/candlesticks.py       trend-aware pattern detection + net bias
  ml/mlp.py                        pure-numpy MLP + scaler + AUC + save/load
  ml/features.py                   shared extractor: technical + candle + volume
  ml/dataset.py                    backtest trades -> labelled (features, win)
  ml/train.py                      temporal split, train + OOS eval, save model
  ml/validator.py                  load model, P(win), apply_nn_filter gate
  ml/models/trade_validator.json   trained model artifact (regenerate via train)
  agents/reasoning.py              Gemini + deterministic fallback
  agents/news.py                   sentiment + neutral fallback
  prompts/*_v1.md                  versioned prompts (diffable)
  llm/client.py                    multi-provider + quota fallback chain
  execution/paper_broker.py        virtual INR portfolio (JSON-persisted)
  backtester/engine.py             replay, no lookahead
  backtester/analytics.py          win rate / Sharpe / drawdown / PF
  market_calendar.py               NSE session guard (IST)
  workflows/{graph,nodes,runner}.py
configs/  agent · risk · market · trading · news  (.yaml)
frontend/ Next 16 dashboard
```

---

## 4. Landmines — read before changing anything

**Secrets.** `.env` holds real keys and is gitignored. `.env.example` must stay
empty — keys were once pasted into it, which would have committed them. Always
run before committing:
```bash
git diff --cached | grep -E "sk-proj-[A-Za-z0-9]{20}|AQ\.Ab8"
```
⚠️ The OpenAI and Google keys were pasted into a chat transcript. **Rotate both.**

**LLM quota.** Free Google AI Studio keys allow **~20 requests/DAY per model**.
- `gemini-2.5-flash` — the only model with working quota
- `gemini-3.5-flash` — exists, quota exhausted (20/20)
- `gemini-2.5-flash-lite` — 404, retired for new keys
- Mitigations already in place: **model fallback chain** (each model has its own
  quota, so chaining ≈ triples the budget) and **news sentiment cached per
  symbol** (repeat run = 1 request instead of 2).
- OpenAI key authenticates but the account has **no credits** (429).
- NVIDIA NIM is pre-wired as an OpenAI-compatible provider — set
  `llm.provider: nvidia` + `NVIDIA_API_KEY` when that key arrives.

**Tests must never spend tokens.** `tests/conftest.py` strips *every* provider
key and injects fake market/news/NSE providers. When adding a provider, add its
env var to `no_llm`. A suite that finishes in <10s is proof no live calls ran.

**Vacuous tests.** The original backtester fixture was a monotonic ramp, which
pins RSI above the 68 cut-off → `classify()` holds forever → **zero trades**, so
assertions looped over empty lists and proved nothing. Use `_wave()` and
`_assert_trades()`. The lookahead guard was mutation-tested; keep it that way.

**Backtester warmup.** `WARMUP_BARS = 210` because EMA200 needs it. Dropping it
back to 60 silently distorts every comparison against a barely-converged average.

**Position sizing.** ₹1,00,000 account, 10% per trade. Below ~10%, shares
costing more than the per-trade budget round to **0 units and are silently
skipped** — this is why `^NSEI` (₹24k/unit) yields no trades. `skipped_no_size`
and `sizing_warning` now surface this; don't remove them.

**Market hours.** Orders are blocked outside 09:15–15:30 IST / weekends /
holidays — otherwise the agent fills against a *stale close* and nothing looks
wrong. Analysis still runs. Escape hatch: `scheduling.trading_hours_only: false`.

**NSE holidays.** Fetched live from NSE (20 dates for 2026) and unioned with the
config list. The official feed covers lunar festivals whose dates can't be
derived, plus one-offs (NSE is shut 15-Jan-2026 for a Maharashtra election).
Never hand-maintain these alone — config had 8, NSE has 20.

**News allowlist.** `configs/news.yaml` is the *only* source registry.
`assert_allowed()` gates every fetch, redirects are disabled, off-domain article
links are dropped. Adding a source is a config change. Don't bypass this.

**Frontend.** Next 16 has real breaking changes; `frontend/AGENTS.md` says read
`node_modules/next/dist/docs/` first. Relevant ones: Turbopack default, async
`params`/`searchParams`, `next lint` removed.

---

## 5. Built vs not

**Working:** live NSE data · indicators (EMA20/50/200, RSI14, ATR14) ·
**candlestick patterns (trend-aware) + gate** · **learned NN trade validator
(volume/liquidity-aware, OOS-validated) + gate** · news (6 media RSS + NSE
filings) · Gemini reasoning w/ versioned prompts · evaluation veto gate · risk
+ ASM/restricted screen · in-app INR paper broker · backtester · market-hours
guard · dashboard · token/cost tracing · 127 tests.

**Both new filters are opt-in** (`require_pattern_confirmation`,
`require_nn_confirmation` — default `False`), and both live and backtest call
the *same* gate functions so they cannot diverge. The NN gate **fails open**
(no model / scoring error → signal unchanged), never silently blocking every
trade. Retrain: `./.venv/Scripts/python.exe -m app.ml.train`.

**Not built** (user explicitly asked about these):
- **RAG book knowledge** — ⚠️ *sourcing problem*: most trading books are
  copyrighted and cannot be downloaded. Viable: public-domain classics
  (Livermore, Wyckoff, Gann), SEBI/NSE educational material, or books the user
  supplies.
- **Invalidation reasoning** — thesis must state what would prove it wrong
- **Reflection engine** — backtrack a wrong call, name the missed factor.
  ⚠️ *Partly addressed*: the NN validator (`app/ml/`) already learns from
  **backtest** trade outcomes (hundreds of labelled wins/losses) to score new
  entries. What's still missing is the *narrative* half — naming the missed
  factor per trade — versus the current numeric P(win).
- **Memory** — index reflections so similar setups recall past mistakes
- **Dynamic mini-agent creation** — the user's own plan deliberately deferred
  this post-MVP. Recommend keeping it deferred: self-modifying agents are hard
  to bound and validate.

---

## 5b. Progress against the original 14-phase plan

**7 of 14 complete (~50%), 3 partial, 4 not started.**

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundations, configs | ✅ complete |
| 1 | FastAPI + Next.js dashboard | ✅ complete |
| 2 | Data collectors | ⚠️ ~50% — market ✅ news ✅; **macro ❌ PostgreSQL ❌** |
| 3 | RAG book brain (Qdrant) | ❌ not started |
| 4 | Indicators & strategies | ⚠️ ~65% — EMA/RSI/ATR ✅ candlesticks ✅ volume/liquidity ✅; **MACD ❌ S/R ❌** |
| 5 | State model + orchestrator | ✅ ~90% — no dynamic supervisor node |
| 6 | Reasoning + Evaluation | ✅ complete (evaluation is rule-based, not LLM) |
| 7 | Risk + Decision | ✅ complete (exceeded — ASM/compliance screen) |
| 8 | Replay simulation mode | ❌ not started (backtester overlaps) |
| 9 | Backtester + analytics | ✅ complete (exceeded — A/B harness) |
| 10 | Post-trade reflection | ⚠️ ~40% — NN validator learns from backtest outcomes; narrative reflection ❌ |
| 11 | Long-term memory | ❌ not started |
| 12 | Paper trading | ✅ complete (built early, exceeded) |
| 13 | Live broker + Docker | ❌ not started |

**Built out of order on purpose.** Phases 9 and 12 came early, which is *why*
the profitability problem surfaced now rather than at Week 19.

**Structural deviations:** Evaluation/Risk/Decision are nodes in
`workflows/nodes.py`, not separate `agents/*.py` files — functionally complete,
organised differently. **PostgreSQL was skipped**; the portfolio persists to
JSON. Fine now, needs replacing before multi-symbol scale or stored history.

**Built outside the plan:** `market_calendar.py`, `nse_official.py`,
multi-provider `llm/client.py` with quota fallback, `observability/trace.py`,
the A/B measurement methodology, and the `app/ml/` learned-validator stack
(pure-numpy MLP, no torch/sklearn dependency).

⚠️ Phase count is not the blocker. Phases 3, 10 and 11 make the agent
*smarter*; none make the signal *profitable*. That problem sits outside the
plan entirely.

## 6. Next steps, in priority order

1. **Attack profitability** — still the real blocker. The candlestick + NN
   filters reached ≈break-even by *removing* bad trades; they cannot add an
   edge that isn't there. Options: different strategy family (mean-reversion,
   breakout w/ volume), longer holds, a proper rolling walk-forward.
2. **Rolling walk-forward for the NN gate** — the current model is validated
   OOS on one temporal split (AUC 0.62), but the *portfolio* A/B over full 5y
   is ~70% in-sample. A retrain-then-test-forward loop would give an honest
   portfolio number and expose threshold curve-fit. Do this before trusting
   the NN gate live.
3. **Bigger / broader training set** — 339 trades over 6 names is thin for an
   MLP. Add symbols and years; watch AUC stability, not in-sample fit.
4. **Invalidation reasoning** — cheap prompt change; the narrative half of
   reflection the NN validator doesn't cover.
5. **Memory** — index reflections + validator scores so similar setups recall
   past outcomes.

**Method note:** always A/B a strategy change through the backtester with
`signal_overrides=` before keeping it, and report the number honestly even when
it's bad. That's how the regime filter got its (unflattering) verdict.

---

## 7. Commit history

```
1d8df04  EMA200 regime filter — measured, marginal, does NOT fix profitability
ee51526  Official NSE data — holidays, ASM surveillance, filings, session state
b0bb6ee  Enforce NSE market hours — block orders against a stale close
aad669d  Backtester; account -> Rs 1,00,000 and rescaled sizing
a2d3206  News Agent with a curated-source trust boundary
94a1bde  LLM provider -> Google Gemini; multi-provider client
d890e52  LLM Reasoning Engine with deterministic fallback
d289391  Live NSE market data collector (yfinance)
45b6f5c  In-app paper-trading engine (virtual INR portfolio)
e472510  Retarget system to the Indian market (NSE/BSE)
1f95429  Next.js dashboard — visual agent-pipeline debugger
ff5e818  Walking-skeleton graph
3f0e5b1  Phase 0 scaffold
```
