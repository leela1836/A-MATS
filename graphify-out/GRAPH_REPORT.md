# Graph Report - Trade  (2026-09-29)

## Corpus Check
- 129 files · ~89,794 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 4, .example 1, .npz 1)

## Summary
- 1450 nodes · 3354 edges · 69 communities (57 shown, 12 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 166 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `19f95e62`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- detect
- market_collector.py
- test_news.py
- test_strategy_library.py
- run_backtest
- realtime.py
- PaperBroker
- run_cycle
- package.json
- nse_official.py
- market_calendar.py
- get_config
- state.py
- main.py
- test_ml.py
- A-MATS Architecture Document
- upstox_stream.py
- MLP
- Journal
- test_support_resistance.py
- Direction
- test_screener.py
- typing
- conftest.py
- scan.py
- test_realtime.py
- fyers_collector.py
- _resolve_open
- Real-time paper trading and project review
- Dashboard.tsx
- api.ts
- server.py
- compilerOptions
- test_trading_integrity.py
- test_learn.py
- news.py
- train.py
- summary.py
- CandleChart.tsx
- test_reasoning.py
- weinstein_signal
- compute_insights
- A-MATS — Handoff
- roster.py
- RealtimeEngine
- BuyHold
- store.py
- SignalPanel.tsx
- TrackRecord.tsx
- LLMUnavailable
- AgentSummary.tsx
- market
- build_site.py
- TradePlan.tsx
- .__init__
- reasoning_v1.md
- README.md
- AGENTS.md
- journal/__init__.py
- nn_dashboard/__init__.py
- frontend/AGENTS.md
- postcss.config.mjs
- journal
- journal
- test_migration_adds_columns_to_old_db

## God Nodes (most connected - your core abstractions)
1. `Direction` - 70 edges
2. `get_config()` - 58 edges
3. `Journal` - 45 edges
4. `detect()` - 43 edges
5. `run_backtest()` - 36 edges
6. `fetch_history()` - 29 edges
7. `MarketAnalysis` - 29 edges
8. `market_status()` - 26 edges
9. `RealtimeEngine` - 25 edges
10. `extract()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Findings in priority order` --references--> `_check_exit()`  [INFERRED]
  docs/trader-review.md → app/backtester/engine.py
- `1. The one thing to know first` --references--> `fetch_history()`  [INFERRED]
  docs/HANDOFF.md → app/collectors/market_collector.py
- `4. Landmines — read before changing anything` --references--> `fetch_history()`  [INFERRED]
  docs/HANDOFF.md → app/collectors/market_collector.py
- `4. Landmines — read before changing anything` --references--> `assert_allowed()`  [INFERRED]
  docs/HANDOFF.md → app/collectors/news_collector.py
- `3. Pipeline` --references--> `market()`  [INFERRED]
  docs/HANDOFF.md → app/main.py

## Import Cycles
- None detected.

## Communities (69 total, 12 thin omitted)

### Community 0 - "detect"
Cohesion: 0.08
Nodes (52): Candle, _candles(), detect(), _doji(), _engulfing(), _hammer_family(), _harami(), _marubozu() (+44 more)

### Community 1 - "market_collector.py"
Cohesion: 0.07
Nodes (52): Event-driven backtester for the technical strategy. AVOIDING LOOKAHEAD BIAS —…, backtest(), Shared-capital strategy evaluation on a reserved chronological tail. Parameters…, main(), Reproducible, network-free portfolio validation on the local cached universe., apply_pattern_filter(), _atr(), _cache_path() (+44 more)

### Community 2 - "test_news.py"
Cohesion: 0.07
Nodes (48): _age_hours(), allowed_domains(), Article, assert_allowed(), _clean(), _fetch_feed(), filter_for_symbol(), _matches() (+40 more)

### Community 3 - "test_strategy_library.py"
Cohesion: 0.09
Nodes (43): avg_turnover(), build_context(), Context, DataFrame, Shared types for the strategy library: the Context a strategy reads and the…, A concrete trade proposal from one strategy., Everything a strategy needs to judge a symbol — computed once, shared., Propose a trade for this context, or None if the setup doesn't fit. (+35 more)

### Community 4 - "run_backtest"
Cohesion: 0.08
Nodes (49): analyse(), _exit_breakdown(), _max_drawdown(), Any, Performance metrics over a BacktestResult. Sharpe is annualised from daily…, Largest peak-to-trough decline, as a positive percentage., Annualised Sharpe of daily equity returns (risk-free rate assumed 0)., _sharpe() (+41 more)

### Community 5 - "realtime.py"
Cohesion: 0.08
Nodes (30): Chronological, shared-capital daily-bar replay of the continuous paper engine.…, Bounded read-only Upstox diagnostic. Never prints credentials or socket URLs., Loads and caches the YAML config files under configs/. Also loads secrets from…, Read-only reporting from the persisted continuous paper account. Research…, initialize_account(), main(), Bounded paper sessions for GitHub Actions, using the persistent real-time…, Fund a new virtual account once; never reset an existing account. (+22 more)

### Community 6 - "PaperBroker"
Cohesion: 0.06
Nodes (19): _apply_fill(), PaperBroker, Portfolio, Position, Path, Thread-safe façade over a persisted Portfolio., Execute a market paper order. side is 'buy' or 'sell'., Convert a target position size (% of equity) into whole-share qty. (+11 more)

### Community 7 - "run_cycle"
Cohesion: 0.07
Nodes (26): get_broker(), In-app paper-trading engine. A self-contained virtual portfolio in INR. No…, NodeTrace, Lightweight per-run tracing: node durations, token usage, and cost. Real LLM…, Context manager returning elapsed milliseconds via `.ms`., RunTrace, timed, _dump() (+18 more)

### Community 8 - "package.json"
Cohesion: 0.05
Nodes (37): eslintConfig, nextConfig, dependencies, next, react, react-dom, devDependencies, eslint (+29 more)

### Community 9 - "nse_official.py"
Cohesion: 0.09
Nodes (38): Announcement, _cache_path(), _cached(), _fetch(), fetch_announcements(), fetch_asm_symbols(), fetch_market_state(), fetch_trading_holidays() (+30 more)

### Community 10 - "market_calendar.py"
Cohesion: 0.10
Nodes (37): config_holiday_dates(), holiday_dates(), _hours(), is_holiday(), is_weekend(), market_status(), MarketStatus, _next_open() (+29 more)

### Community 11 - "get_config"
Cohesion: 0.09
Nodes (33): get_config(), _load(), Any, Return a parsed config section by short name (agent/risk/market/trading)., api_key(), _base_url(), complete_json(), _cost() (+25 more)

### Community 12 - "state.py"
Cohesion: 0.09
Nodes (34): AgentState, EvaluationScores, ExecutionResult, new_state(), Shared graph state and the Pydantic contracts passed between nodes. The walking…, State threaded through the LangGraph state machine., Construct a fresh state dict with metadata containers initialized., RiskAssessment (+26 more)

### Community 13 - "main.py"
Cohesion: 0.09
Nodes (35): all_configs(), get_journal(), agent_summary(), backtest(), config(), configs(), health(), journal_decisions() (+27 more)

### Community 14 - "test_ml.py"
Cohesion: 0.11
Nodes (28): extract(), DataFrame, ndarray, Relative volume, turnover, and directional volume pressure. Absolute volume is…, Feature vector for a candidate entry decided on the LAST bar of `window`.…, _safe(), _volume_features(), apply_nn_filter() (+20 more)

### Community 15 - "A-MATS Architecture Document"
Cohesion: 0.06
Nodes (31): 10. Success Metrics (MVP), 11. Rate Limiting & Constraints, 12. Security Considerations, 1.1 High-Level Architecture, 1. System Overview, 2.1 State Graph, 2.2 State Schema, 2. Agent State Machine (LangGraph) (+23 more)

### Community 16 - "upstox_stream.py"
Cohesion: 0.10
Nodes (27): main(), validate_history(), _candles_to_df(), fetch_history_upstox(), instrument_key(), _load_instruments(), DataFrame, Upstox market-data collector — real NSE prices that work from the cloud. Yahoo… (+19 more)

### Community 17 - "MLP"
Cohesion: 0.11
Nodes (21): load_model(), MLP, ndarray, Path, A minimal multilayer perceptron in pure numpy. Why not torch/sklearn: the…, One self-describing JSON: weights, scaler, feature order, gate threshold.…, Zero-mean/unit-variance per feature. Fitted on TRAIN only, then frozen., AUC via the rank identity (Mann-Whitney U). No sklearn needed. (+13 more)

### Community 18 - "Journal"
Cohesion: 0.15
Nodes (13): Journal, _now(), Any, Log one retrain of the validator — the agent's memory of *learning*. Called by…, Most-recent retrains, newest first — the agent's learning history., Persist a snapshot of the agent's derived edge, so conclusions (not just raw…, Stored insight snapshots, oldest-first — for trending the agent's edge., Open directional calls with the plan + thesis, so a summary can say plainly… (+5 more)

### Community 19 - "test_support_resistance.py"
Cohesion: 0.14
Nodes (26): _cluster(), detect_levels(), Level, nearest(), _pivot_prices(), Any, DataFrame, Support & resistance detection from swing pivots. A level matters because price… (+18 more)

### Community 20 - "Direction"
Cohesion: 0.17
Nodes (26): _coerce(), _default_confirmation(), _default_entry_rationale(), _default_invalidation(), _finite(), _hold_estimate(), Any, Reasoning Engine: turns a technical read into a trade thesis. Primary path is… (+18 more)

### Community 21 - "test_screener.py"
Cohesion: 0.11
Nodes (24): Screen the whole universe, then run the full pipeline on the shortlist. Stage…, run_screen_scan(), Candidate, Any, qualifies_for_trade(), Tight gate for entries: keep only setups with earned signal quality. The live…, Analyse every symbol; return (top-N ranked candidates, price map for ALL…, screen_universe() (+16 more)

### Community 22 - "typing"
Cohesion: 0.15
Nodes (20): Dataset, Turn backtest trades into a labelled training set. Each row is one entry the…, Split by DATE, not at random. A random split lets the model peek at the same…, temporal_split(), _take(), Feature extraction for the trade validator. ONE extractor, shared by training…, generate(), load_cached() (+12 more)

### Community 23 - "conftest.py"
Cohesion: 0.11
Nodes (19): clear_cache(), pytest, fake_history(), fake_market(), fake_news(), FakeMarketProvider, FakeNewsProvider, isolated_broker() (+11 more)

### Community 24 - "scan.py"
Cohesion: 0.12
Nodes (22): deterministic(), Scope reasoning to its rule-based path (no LLM calls) for a block., _features_json(), _hold_limit(), _holding_days(), Any, datetime, Autonomous watchlist scan — the system's heartbeat. One call sweeps the whole… (+14 more)

### Community 25 - "test_realtime.py"
Cohesion: 0.13
Nodes (18): Read the separate paper runner's heartbeat; this endpoint cannot trade., realtime_status(), parametrize, test_bad_ticks_never_fill(), test_benched_signal_cannot_enter(), test_broker_rejects_invalid_numbers(), test_closed_session_ignores_legacy_override(), test_entry_stop_gap_and_restart() (+10 more)

### Community 26 - "fyers_collector.py"
Cohesion: 0.13
Nodes (19): connect(), received(), credentials(), fetch_completed_history(), fyers_symbol(), parse_tick(), DataFrame, datetime (+11 more)

### Community 27 - "_resolve_open"
Cohesion: 0.10
Nodes (18): _bars_since(), _path_exit(), Close open trades that hit a level, broke their thesis, or timed out. Per…, Daily OHLC bars strictly after the entry date (cached fetch), or None., Did the high/low PATH since entry touch the stop or target? Returns…, _resolve_open(), Journal + autonomous scan tests — fully offline (conftest fakes providers)., End-to-end: a deterministic scan over the fake watchlist journals decisions +… (+10 more)

### Community 28 - "Real-time paper trading and project review"
Cohesion: 0.09
Nodes (20): Free market-data choices, Limits and verification, New runner, Publishing paper-account snapshots to GitHub Pages, Real-time paper trading and project review, Setup and run (PowerShell), Skills evaluated, Stopping entries and reviewing halts (+12 more)

### Community 29 - "Dashboard.tsx"
Cohesion: 0.17
Nodes (19): Home(), BtStat(), Dashboard(), fmt(), StageDetail(), DOT, PipelineFlow(), RING (+11 more)

### Community 30 - "api.ts"
Cohesion: 0.09
Nodes (18): API_BASE, BacktestMetrics, BacktestResponse, CandlePattern, CandlesResponse, EdgeBucket, EvaluationScores, ExecutionResult (+10 more)

### Community 31 - "server.py"
Cohesion: 0.14
Nodes (20): api_model(), api_predict(), api_weights(), dashboard(), forward_with_hidden(), get_bundle(), health(), PredictRequest (+12 more)

### Community 32 - "compilerOptions"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 33 - "test_trading_integrity.py"
Cohesion: 0.16
Nodes (14): DataFrame, replay(), paper_report(), Path, fixture_bars(), test_accounting_detects_unmarked_fill(), test_accounting_reconciles_fees_and_unrealized(), test_entry_bar_stop_is_not_skipped() (+6 more)

### Community 34 - "test_learn.py"
Cohesion: 0.16
Nodes (15): _concat(), dataset_from_journal(), learn(), Any, Path, Retrain the validator on journal experience (+ bootstrap). Returns a summary;…, journal(), fixture (+7 more)

### Community 35 - "news.py"
Cohesion: 0.22
Nodes (14): analyse(), _cache_ttl(), _label(), _neutral(), Any, News Agent: turns curated Indian financial headlines into a sentiment read.…, A deliberately signal-free read — never guess sentiment without a model., Return (signals, usage). Never raises — news is advisory, not critical. (+6 more)

### Community 36 - "train.py"
Cohesion: 0.21
Nodes (15): build_dataset(), Replay each symbol once; emit (features, outcome) for every trade. The SAME…, Eval, _evaluate(), _fit_and_eval(), _param_count(), _pick_threshold(), ndarray (+7 more)

### Community 37 - "summary.py"
Cohesion: 0.23
Nodes (15): agent_summary(), _benchmark(), _headline(), _inr(), _model_meta(), _pct(), Any, Path (+7 more)

### Community 38 - "CandleChart.tsx"
Cohesion: 0.24
Nodes (12): CandleChart(), Levels, PAD, C, inr(), ticks(), useMeasure(), EquityChart() (+4 more)

### Community 39 - "test_reasoning.py"
Cohesion: 0.26
Nodes (13): LLMResult, _ma(), Reasoning Engine tests — fallback, LLM coercion, and gate interaction. No test…, A non-finite feed must never reach the model., An inverted-level LLM proposal must be halted by the evaluation gate., test_bad_feed_short_circuits_before_llm(), test_evaluation_gate_can_veto_the_llm(), fake() (+5 more)

### Community 40 - "weinstein_signal"
Cohesion: 0.27
Nodes (13): _params(), DataFrame, Stan Weinstein's Stage Analysis — a mechanical breakout system. From *Secrets…, (trend, signal, confidence) for the last bar of `window`. Signal is LONG only…, weinstein_signal(), _df(), Weinstein Stage-Analysis signal tests on synthetic multi-year series., test_breakout_without_volume_is_hold() (+5 more)

### Community 41 - "compute_insights"
Cohesion: 0.19
Nodes (13): manage_open(), The fast, light heartbeat for the 10-min intraday loop: re-price every OPEN…, _bucket(), compute_insights(), _narrate(), Any, _rate(), Derive the agent's *insights* from its journal — the conclusions, not just the… (+5 more)

### Community 42 - "A-MATS — Handoff"
Cohesion: 0.14
Nodes (13): merge_metrics(), Reducer so parallel nodes can each contribute their own metrics key., 1. The one thing to know first, 2. Run it, 3. Pipeline, 5. Built vs not, 5b. Progress against the original 14-phase plan, 6. Next steps, in priority order (+5 more)

### Community 43 - "roster.py"
Cohesion: 0.24
Nodes (12): evaluate_and_update(), get_roster(), is_tradable(), _load(), Any, Champion / challenger governance for the strategy library. Every strategy holds…, May this strategy open a trade? (benched strategies only label.), Promote/demote from LIVE closed-trade results. The gate, not vibes: shadow →… (+4 more)

### Community 44 - "RealtimeEngine"
Cohesion: 0.29
Nodes (4): Only complete fresh marks enter the accounting series., RealtimeEngine, engine(), fixture

### Community 45 - "BuyHold"
Cohesion: 0.26
Nodes (5): BuyHold, Path, Value the buy-and-hold basket at the given prices. Initializes the basket…, The buy-and-hold basket initializes on first prices and marks to market., test_benchmark_tracks_buy_and_hold()

### Community 46 - "store.py"
Cohesion: 0.20
Nodes (9): _ist_date(), SQLite-backed decision & equity journal. Two tables: decisions — one row per…, Paper account's starting capital (config-driven, state-independent)., The IST calendar date of a stored UTC timestamp (YYYY-MM-DD), or None., What happened *today* (IST): scans run, trades opened, trades closed and their…, _starting_cash(), today_ist(), contextlib (+1 more)

### Community 47 - "SignalPanel.tsx"
Cohesion: 0.29
Nodes (9): arc(), Gauge(), polar(), Meter(), biasColor(), SIGNAL_STYLE, SignalPanel(), MarketAnalysis (+1 more)

### Community 48 - "TrackRecord.tsx"
Cohesion: 0.25
Nodes (10): DIR, OUT, Tile(), TrackRecord(), EquityPoint, getJournalDecisions(), getJournalEquity(), JournalDecision (+2 more)

### Community 49 - "LLMUnavailable"
Cohesion: 0.29
Nodes (7): LLMUnavailable, ModelUnavailable, RuntimeError, No API key configured, or the provider could not be reached., This specific model is rate-limited (429) or retired (404). Distinct from…, test_fallback_on_provider_error(), boom()

### Community 50 - "AgentSummary.tsx"
Cohesion: 0.39
Nodes (6): AgentSummary(), EdgeTile(), pct(), Tile(), AgentSummary, getAgentSummary()

### Community 51 - "market"
Cohesion: 0.33
Nodes (6): market(), Whether the NSE session is open right now (IST)., Judgement rules — follow these strictly, Output, Your inputs, Your job

### Community 52 - "build_site.py"
Cohesion: 0.43
Nodes (6): build(), _nn_model(), _paper_account(), Dump the journal + trained model to docs/*.json for the GitHub Pages site. Run…, _track_record(), test_cloud_build_preserves_published_account_and_local_export_replaces_it()

### Community 53 - "TradePlan.tsx"
Cohesion: 0.43
Nodes (6): DIR, inr(), Line(), Stat(), TradePlan(), ReasonedAnalysis

### Community 54 - ".__init__"
Cohesion: 0.40
Nodes (3): Path, Add columns introduced after a DB was first created (SQLite has no 'ADD COLUMN…, Connection

### Community 55 - "reasoning_v1.md"
Cohesion: 0.40
Nodes (4): Discipline rules — follow these strictly, Output, Your inputs, Your job

### Community 56 - "README.md"
Cohesion: 0.50
Nodes (3): Deploy on Vercel, Getting Started, Learn More

## Knowledge Gaps
- **130 isolated node(s):** `eslintConfig`, `nextConfig`, `name`, `version`, `private` (+125 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 589 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_config()` connect `get_config` to `market_collector.py`, `test_news.py`, `news.py`, `run_backtest`, `realtime.py`, `PaperBroker`, `run_cycle`, `test_trading_integrity.py`, `market_calendar.py`, `RealtimeEngine`, `main.py`, `store.py`, `state.py`, `Direction`, `conftest.py`, `scan.py`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
- **Why does `Direction` connect `Direction` to `market_collector.py`, `test_trading_integrity.py`, `run_backtest`, `test_reasoning.py`, `weinstein_signal`, `run_cycle`, `state.py`, `test_ml.py`, `LLMUnavailable`, `test_screener.py`, `typing`, `conftest.py`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `Journal` connect `Journal` to `test_migration_adds_columns_to_old_db`, `test_trading_integrity.py`, `test_learn.py`, `test_strategy_library.py`, `summary.py`, `compute_insights`, `roster.py`, `main.py`, `store.py`, `test_screener.py`, `.__init__`, `typing`, `scan.py`, `_resolve_open`, `journal`, `journal`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Are the 49 inferred relationships involving `Direction` (e.g. with `_default_confirmation()` and `_default_entry_rationale()`) actually correct?**
  _`Direction` has 49 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Journal` (e.g. with `manage_open()` and `_resolve_open()`) actually correct?**
  _`Journal` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `eslintConfig`, `nextConfig`, `name` to the rest of the system?**
  _130 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `detect` be split into smaller, more focused modules?**
  _Cohesion score 0.07680491551459294 - nodes in this community are weakly interconnected._