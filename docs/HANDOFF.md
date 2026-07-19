# A-MATS — Handoff

**Last updated:** 2026-07-19 · **Branch:** `master` · **Head:** `1d8df04` · **Tests:** 90 passing

Autonomous multi-agent trading system for the **Indian market (NSE)**. LangGraph
orchestration, Gemini reasoning, in-app paper trading in INR.

---

## 1. The one thing to know first

**The strategy is not profitable.** Infrastructure is solid and well-tested;
the *signal* is weak. Measured over 5 years on six NSE large-caps:

| | mean return / symbol | trades |
|---|---|---|
| without regime filter | −3.004% | 375 |
| with EMA200 regime filter | −2.764% | 335 |

Better on 4 of 6 symbols, but +0.24pp on a 6-name sample is within noise.
Simple EMA/RSI trend-following does not appear to work on Indian large-caps.

Do not add more agent layers expecting profit to appear. Better inputs make
the agent *smarter about a losing strategy*. Profitability is a separate,
unsolved problem.

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

**Working:** live NSE data · indicators (EMA20/50/200, RSI14, ATR14) · news
(6 media RSS + NSE filings) · Gemini reasoning w/ versioned prompts · evaluation
veto gate · risk + ASM/restricted screen · in-app INR paper broker · backtester
· market-hours guard · dashboard · token/cost tracing · 90 tests.

**Not built** (user explicitly asked about these):
- **Candlestick patterns** — engulfing/hammer/doji/star + trend context
- **RAG book knowledge** — ⚠️ *sourcing problem*: most trading books are
  copyrighted and cannot be downloaded. Viable: public-domain classics
  (Livermore, Wyckoff, Gann), SEBI/NSE educational material, or books the user
  supplies.
- **Invalidation reasoning** — thesis must state what would prove it wrong
- **Reflection engine** — backtrack a wrong call, name the missed factor.
  ⚠️ *needs closed trades*; the paper book has none. Train it against
  **backtest** trades, which give hundreds of known outcomes immediately.
- **Memory** — index reflections so similar setups recall past mistakes
- **Dynamic mini-agent creation** — the user's own plan deliberately deferred
  this post-MVP. Recommend keeping it deferred: self-modifying agents are hard
  to bound and validate.

---

## 6. Next steps, in priority order

1. **Attack profitability** — the real blocker. Options: different strategy
   family (mean-reversion, breakout w/ volume), longer holds, walk-forward
   validation to avoid curve-fitting. Everything else is polish until this moves.
2. **Candlestick patterns** — concrete, backtestable, no sourcing/quota issues.
3. **Invalidation reasoning** — cheap prompt change; prerequisite for (4).
4. **Reflection engine** — train against backtest trades.
5. **Memory** — only after reflections exist to index.

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
