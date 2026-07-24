"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  checkHealth,
  getBacktest,
  getCandles,
  getPortfolio,
  getTrades,
  resetPortfolio,
  runCycle,
  type BacktestResponse,
  type Candle,
  type SRLevel,
  type PaperTrade,
  type Portfolio,
  type RunResult,
} from "@/lib/api";
import { Field, StageCard, type Status } from "./StageCard";
import { PortfolioPanel } from "./PortfolioPanel";
import { PipelineFlow, type Stage } from "./PipelineFlow";
import { SignalPanel } from "./SignalPanel";
import { TradePlan } from "./TradePlan";
import { CandleChart } from "./charts/CandleChart";
import { EquityChart } from "./charts/EquityChart";

function fmt(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

export function Dashboard() {
  const [symbol, setSymbol] = useState("RELIANCE.NS");
  const [result, setResult] = useState<RunResult | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [sr, setSr] = useState<{ levels: SRLevel[]; support: number | null; resistance: number | null }>({
    levels: [],
    support: null,
    resistance: null,
  });
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingBt, setLoadingBt] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [selected, setSelected] = useState<string>("reasoning");

  const refreshPortfolio = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([getPortfolio(), getTrades(20)]);
      setPortfolio(p);
      setTrades(t);
    } catch {
      /* backend offline — keep last known */
    }
  }, []);

  const loadCandles = useCallback(async (sym: string) => {
    try {
      const c = await getCandles(sym);
      setCandles(c.bars);
      setSr({ levels: c.levels, support: c.support, resistance: c.resistance });
      return true;
    } catch (e) {
      setCandles([]);
      setSr({ levels: [], support: null, resistance: null });
      setError(e instanceof Error ? e.message : `Could not load price data for ${sym}`);
      return false;
    }
  }, []);

  const loadBacktest = useCallback(async (sym: string) => {
    setLoadingBt(true);
    try {
      setBacktest(await getBacktest(sym));
    } catch {
      setBacktest(null);
    } finally {
      setLoadingBt(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const ping = async () => {
      const ok = await checkHealth();
      if (active) setOnline(ok);
    };
    ping();
    refreshPortfolio();
    loadCandles(symbol);
    const id = setInterval(ping, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshPortfolio, loadCandles]);

  const run = async () => {
    // Yahoo tickers have no spaces: "NTPC GREEN.NS" is a typo for "NTPCGREEN.NS".
    const sym = symbol.replace(/\s+/g, "").toUpperCase();
    if (sym !== symbol) setSymbol(sym);
    setLoading(true);
    setError(null);
    try {
      const [res] = await Promise.all([runCycle(sym), loadCandles(sym)]);
      setResult(res);
      setPortfolio(res.portfolio);
      setSelected(res.halted ? "market" : "reasoning");
      await refreshPortfolio();
      loadBacktest(sym); // non-blocking; equity panel fills a beat later
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const reset = async () => {
    try {
      setPortfolio(await resetPortfolio());
      setTrades([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const r = result;

  const evalStatus: Status = !r
    ? "idle"
    : r.evaluation_scores
      ? r.evaluation_scores.passed ? "pass" : "halt"
      : "skipped";
  const riskStatus: Status = !r
    ? "idle"
    : r.risk_assessment
      ? r.risk_assessment.approved ? "pass" : "halt"
      : "skipped";

  const stages: Stage[] = useMemo(() => {
    const has = (b: boolean): Status => (!r ? "idle" : b ? "pass" : "skipped");
    return [
      { key: "market", label: "Market", status: has(!!r?.market_analysis), value: r?.market_analysis?.signal },
      { key: "news", label: "News", status: has(!!r?.news_signals), value: r?.news_signals?.sentiment_label },
      { key: "reasoning", label: "Reasoning", status: has(!!r?.reasoned_analysis), value: r?.reasoned_analysis?.direction },
      { key: "evaluation", label: "Evaluation", status: evalStatus, value: r?.evaluation_scores ? fmt(r.evaluation_scores.overall_score) : undefined },
      { key: "risk", label: "Risk", status: riskStatus, value: r?.risk_assessment ? `${fmt(r.risk_assessment.position_size_percent)}%` : undefined },
      { key: "decision", label: "Decision", status: has(!!r?.decision), value: r?.decision?.action },
      { key: "execution", label: "Execution", status: has(!!r?.execution_result), value: r?.execution_result ? (r.execution_result.filled ? "filled" : "no fill") : undefined },
    ];
  }, [r, evalStatus, riskStatus]);

  const dayChange = useMemo(() => {
    if (candles.length < 2) return null;
    const a = candles[candles.length - 2].close;
    const b = candles[candles.length - 1].close;
    return { abs: b - a, pct: ((b - a) / a) * 100 };
  }, [candles]);

  const lastClose = candles.length ? candles[candles.length - 1].close : r?.market_analysis?.last_price ?? null;

  return (
    <div className="min-h-screen mx-auto max-w-6xl px-5 py-6">
      {/* header */}
      <header className="flex items-center justify-between mb-5">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">A-MATS</h1>
          <span className="text-xs text-muted">agent trading dashboard · NSE</span>
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          {r && (
            <span className={r.market_status.is_open ? "text-pass" : "text-halt"}>
              {r.market_status.is_open ? "● market open" : "● market closed"}
            </span>
          )}
          <span className="flex items-center gap-1.5 text-muted">
            <span className={`h-2 w-2 rounded-full ${online === null ? "bg-muted/40" : online ? "bg-pass" : "bg-fail"}`} />
            {online === null ? "…" : online ? "online" : "offline"}
          </span>
        </div>
      </header>

      {/* controls */}
      <div className="flex gap-2 mb-4">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Symbol (e.g. RELIANCE.NS)"
          className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm font-mono outline-none focus:border-accent"
        />
        <button
          onClick={run}
          disabled={loading || !symbol.trim()}
          className="rounded-md bg-accent px-6 py-2 text-sm font-medium text-background disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          {loading ? "Running…" : "Run cycle"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-fail/40 bg-fail/10 px-4 py-3 text-sm text-fail">
          {error}
          <div className="text-xs text-muted mt-1">Is the backend running at {API_BASE}?</div>
        </div>
      )}

      {/* row A — price chart + signals */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div className="lg:col-span-2 rounded-lg border border-border bg-surface p-4">
          <div className="flex items-baseline justify-between mb-2">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-medium">{r?.symbol ?? symbol.toUpperCase()}</span>
              <span className="text-lg font-mono">{lastClose !== null ? lastClose.toFixed(2) : "—"}</span>
              {dayChange && (
                <span className={`text-xs font-mono ${dayChange.abs >= 0 ? "text-pass" : "text-fail"}`}>
                  {dayChange.abs >= 0 ? "+" : ""}{dayChange.abs.toFixed(2)} ({dayChange.pct.toFixed(2)}%)
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-[11px] font-mono">
              {sr.support !== null && (
                <span style={{ color: "#3fb9a0" }}>S {sr.support.toFixed(2)}</span>
              )}
              {sr.resistance !== null && (
                <span style={{ color: "#e0996a" }}>R {sr.resistance.toFixed(2)}</span>
              )}
              <span className="text-muted">{candles.length} bars · daily</span>
            </div>
          </div>
          <CandleChart
            candles={candles}
            sr={sr.levels}
            levels={
              r?.reasoned_analysis
                ? {
                    entry: r.reasoned_analysis.entry_price,
                    stop: r.reasoned_analysis.stop_loss,
                    target: r.reasoned_analysis.take_profit,
                  }
                : undefined
            }
          />
        </div>
        <SignalPanel market={r?.market_analysis ?? null} news={r?.news_signals ?? null} />
      </div>

      {/* row B — pipeline flow + selected stage detail */}
      <div className="rounded-lg border border-border bg-surface p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium">Agent pipeline</span>
          {r?.halted && <span className="text-xs text-halt font-mono">halted · {r.halt_reason}</span>}
        </div>
        <PipelineFlow stages={stages} selected={selected} onSelect={setSelected} />
        <div className="mt-4">
          <StageDetail selected={selected} r={r} />
        </div>
      </div>

      {/* reasoning thesis + full trade plan */}
      {r?.reasoned_analysis && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          <div className="rounded-lg border border-border bg-surface px-4 py-3">
            <div className="text-xs text-muted mb-1">Thesis</div>
            <p className="text-sm text-foreground leading-relaxed">{r.reasoned_analysis.thesis}</p>
          </div>
          <TradePlan r={r.reasoned_analysis} />
        </div>
      )}

      {/* row C — portfolio + equity/backtest */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {portfolio && <PortfolioPanel portfolio={portfolio} trades={trades} onReset={reset} />}
        <div className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Strategy backtest</span>
            <span className="text-[11px] text-muted font-mono">
              {loadingBt ? "running…" : backtest ? backtest.metrics.period : "run a cycle"}
            </span>
          </div>
          {backtest ? (
            <>
              <div className="grid grid-cols-4 gap-2 mb-3 text-center">
                <BtStat label="return" value={`${backtest.metrics.total_return_pct.toFixed(1)}%`} tone={backtest.metrics.total_return_pct >= 0 ? "text-pass" : "text-fail"} />
                <BtStat label="win rate" value={`${backtest.metrics.win_rate_pct.toFixed(0)}%`} />
                <BtStat label="max DD" value={`${backtest.metrics.max_drawdown_pct.toFixed(1)}%`} tone="text-halt" />
                <BtStat label="trades" value={String(backtest.metrics.total_trades)} />
              </div>
              <EquityChart points={backtest.equity_curve} />
            </>
          ) : (
            <div className="grid place-items-center text-xs text-muted h-[210px]">
              {loadingBt ? "Replaying history…" : "Backtest loads after a cycle runs."}
            </div>
          )}
        </div>
      </div>

      {/* trace footer */}
      {r && (
        <div className="flex flex-wrap gap-x-8 gap-y-2 rounded-md border border-border bg-surface-2 px-4 py-3 text-xs font-mono text-muted">
          <span>run_id <span className="text-foreground">{r.trace.run_id}</span></span>
          <span>duration <span className="text-foreground">{fmt(r.trace.total_ms)}ms</span></span>
          <span>tokens <span className="text-foreground">{r.trace.total_tokens}</span></span>
          <span>cost <span className="text-foreground">${fmt(r.trace.total_cost_usd, 6)}</span></span>
        </div>
      )}

      {!r && !error && (
        <p className="text-sm text-muted text-center py-8">
          Enter a symbol and run a cycle to drive the full agent pipeline.
        </p>
      )}
    </div>
  );
}

function BtStat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className={`text-sm font-mono ${tone ?? "text-foreground"}`}>{value}</div>
      <div className="text-[10px] text-muted">{label}</div>
    </div>
  );
}

/** Detail for the currently selected pipeline stage. */
function StageDetail({ selected, r }: { selected: string; r: RunResult | null }) {
  if (!r) return <div className="text-xs text-muted">Run a cycle to inspect each stage.</div>;

  const wrap = (title: string, sub: string, status: Status, body: React.ReactNode) => (
    <StageCard title={title} subtitle={sub} status={status}>{body}</StageCard>
  );

  switch (selected) {
    case "market":
      return wrap("Market", "technical read", r.market_analysis ? "pass" : "skipped",
        r.market_analysis && (
          <>
            <Field label="last_price" value={fmt(r.market_analysis.last_price)} />
            <Field label="trend / signal" value={`${r.market_analysis.trend} / ${r.market_analysis.signal}`} />
            <Field label="confidence" value={fmt(r.market_analysis.confidence)} />
            <Field label="nn P(win)" value={r.market_analysis.nn_score === null ? "—" : fmt(r.market_analysis.nn_score)} />
            <Field label="support" value={r.market_analysis.support === null ? "—" : fmt(r.market_analysis.support)} />
            <Field label="resistance" value={r.market_analysis.resistance === null ? "—" : fmt(r.market_analysis.resistance)} />
            {Object.entries(r.market_analysis.indicators).map(([k, v]) => (
              <Field key={k} label={k} value={v === null ? "—" : fmt(v)} />
            ))}
          </>
        ));
    case "news":
      return wrap("News", "curated Indian sources", r.news_signals ? "pass" : "skipped",
        r.news_signals && (
          <>
            <Field label="sentiment" value={`${r.news_signals.sentiment_score > 0 ? "+" : ""}${fmt(r.news_signals.sentiment_score)} (${r.news_signals.sentiment_label})`} />
            <Field label="confidence" value={fmt(r.news_signals.confidence)} />
            <Field label="articles" value={String(r.news_signals.article_count)} />
            {r.news_signals.key_events.slice(0, 4).map((e, i) => (
              <div key={i} className="text-foreground pl-2">· {e}</div>
            ))}
          </>
        ));
    case "reasoning":
      return wrap("Reasoning", "thesis + levels", r.reasoned_analysis ? "pass" : "skipped",
        r.reasoned_analysis && (
          <>
            <Field label="direction" value={r.reasoned_analysis.direction} />
            <Field label="confidence" value={fmt(r.reasoned_analysis.confidence)} />
            <Field label="entry" value={fmt(r.reasoned_analysis.entry_price)} />
            <Field label="stop_loss" value={fmt(r.reasoned_analysis.stop_loss)} />
            <Field label="take_profit" value={fmt(r.reasoned_analysis.take_profit)} />
          </>
        ));
    case "evaluation":
      return wrap("Evaluation", "veto gate",
        r.evaluation_scores ? (r.evaluation_scores.passed ? "pass" : "halt") : "skipped",
        r.evaluation_scores && (
          <>
            <Field label="overall_score" value={fmt(r.evaluation_scores.overall_score)} />
            {Object.entries(r.evaluation_scores.dimensions).map(([k, v]) => (
              <Field key={k} label={k} value={fmt(v)} />
            ))}
            <Field label="reason" value={r.evaluation_scores.reason} />
          </>
        ));
    case "risk":
      return wrap("Risk", "sizing gate",
        r.risk_assessment ? (r.risk_assessment.approved ? "pass" : "halt") : "skipped",
        r.risk_assessment ? (
          <>
            <Field label="size_%" value={fmt(r.risk_assessment.position_size_percent)} />
            <Field label="risk/trade_%" value={fmt(r.risk_assessment.risk_per_trade_percent)} />
            <Field label="reason" value={r.risk_assessment.reason} />
          </>
        ) : <span className="text-xs">not reached</span>);
    case "decision":
      return wrap("Decision", "final call", r.decision ? "pass" : "skipped",
        r.decision ? (
          <>
            <Field label="action" value={r.decision.action} />
            <Field label="size_%" value={fmt(r.decision.size_percent)} />
            <Field label="rationale" value={r.decision.rationale} />
          </>
        ) : <span className="text-xs">not reached</span>);
    case "execution":
      return wrap("Execution", r.execution_result?.mode ?? "paper", r.execution_result ? "pass" : "skipped",
        r.execution_result ? (
          <>
            <Field label="filled" value={String(r.execution_result.filled)} />
            <Field label="fill_price" value={fmt(r.execution_result.fill_price)} />
            <Field label="note" value={r.execution_result.note} />
          </>
        ) : <span className="text-xs">not reached</span>);
    default:
      return null;
  }
}
