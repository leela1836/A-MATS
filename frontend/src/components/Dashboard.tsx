"use client";

import { useCallback, useEffect, useState } from "react";
import {
  API_BASE,
  checkHealth,
  getPortfolio,
  getTrades,
  resetPortfolio,
  runCycle,
  type PaperTrade,
  type Portfolio,
  type RunResult,
} from "@/lib/api";
import { Field, StageCard, type Status } from "./StageCard";
import { PortfolioPanel } from "./PortfolioPanel";

function fmt(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

export function Dashboard() {
  const [symbol, setSymbol] = useState("RELIANCE.NS");
  const [result, setResult] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<PaperTrade[]>([]);

  const refreshPortfolio = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([getPortfolio(), getTrades(20)]);
      setPortfolio(p);
      setTrades(t);
    } catch {
      /* backend offline — leave last known state */
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
    const id = setInterval(ping, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [refreshPortfolio]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await runCycle(symbol.trim().toUpperCase());
      setResult(res);
      setPortfolio(res.portfolio);
      await refreshPortfolio();
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

  // Derive per-stage status from the run result.
  const stage = (present: boolean, halted: boolean): Status =>
    !r ? "idle" : halted ? "halt" : present ? "pass" : "skipped";

  const evalStatus: Status = !r
    ? "idle"
    : r.evaluation_scores
      ? r.evaluation_scores.passed
        ? "pass"
        : "halt"
      : "skipped";
  const riskStatus: Status = !r
    ? "idle"
    : r.risk_assessment
      ? r.risk_assessment.approved
        ? "pass"
        : "halt"
      : "skipped";

  return (
    <div className="min-h-screen max-w-3xl mx-auto px-6 py-10">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">A-MATS</h1>
          <p className="text-sm text-muted">Agent pipeline debugger</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono">
          <span
            className={`h-2 w-2 rounded-full ${
              online === null
                ? "bg-muted/40"
                : online
                  ? "bg-pass"
                  : "bg-fail"
            }`}
          />
          <span className="text-muted">
            {online === null ? "…" : online ? "backend online" : "backend offline"}
          </span>
        </div>
      </header>

      <div className="flex gap-2 mb-6">
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
          className="rounded-md bg-accent px-5 py-2 text-sm font-medium text-background disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          {loading ? "Running…" : "Run cycle"}
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-md border border-fail/40 bg-fail/10 px-4 py-3 text-sm text-fail">
          {error}
          <div className="text-xs text-muted mt-1">
            Is the backend running at {API_BASE}?
          </div>
        </div>
      )}

      {portfolio && (
        <div className="mb-6">
          <PortfolioPanel portfolio={portfolio} trades={trades} onReset={reset} />
        </div>
      )}

      {r && (
        <>
          {r.halted && (
            <div className="mb-6 rounded-md border border-halt/40 bg-halt/10 px-4 py-3 text-sm">
              <span className="text-halt font-medium">Run halted:</span>{" "}
              <span className="font-mono text-foreground">{r.halt_reason}</span>
            </div>
          )}

          <div className="space-y-3">
            <StageCard
              title="Market"
              subtitle="technical read"
              status={stage(!!r.market_analysis, false)}
            >
              {r.market_analysis && (
                <>
                  <Field label="last_price" value={fmt(r.market_analysis.last_price)} />
                  <Field label="trend" value={r.market_analysis.trend} />
                  <Field label="signal" value={r.market_analysis.signal} />
                  <Field label="confidence" value={fmt(r.market_analysis.confidence)} />
                  {Object.entries(r.market_analysis.indicators).map(([k, v]) => (
                    <Field key={k} label={k} value={v === null ? "—" : fmt(v)} />
                  ))}
                </>
              )}
            </StageCard>

            <StageCard
              title="News"
              subtitle="curated Indian financial sources"
              status={r.news_signals ? "pass" : "skipped"}
            >
              {r.news_signals && (
                <>
                  <Field
                    label="sentiment"
                    value={
                      <span
                        className={
                          r.news_signals.sentiment_score > 0.15
                            ? "text-pass"
                            : r.news_signals.sentiment_score < -0.15
                              ? "text-fail"
                              : "text-muted"
                        }
                      >
                        {r.news_signals.sentiment_score > 0 ? "+" : ""}
                        {fmt(r.news_signals.sentiment_score)} ({r.news_signals.sentiment_label})
                      </span>
                    }
                  />
                  <Field label="confidence" value={fmt(r.news_signals.confidence)} />
                  <Field label="articles" value={String(r.news_signals.article_count)} />
                  {r.news_signals.key_events.length > 0 && (
                    <div className="pt-1">
                      <div className="text-muted mb-1">key_events</div>
                      {r.news_signals.key_events.map((e, i) => (
                        <div key={i} className="text-foreground pl-2">· {e}</div>
                      ))}
                    </div>
                  )}
                  {r.news_signals.articles.length > 0 && (
                    <details className="pt-2">
                      <summary className="cursor-pointer text-muted hover:text-foreground">
                        headlines ({r.news_signals.articles.length})
                      </summary>
                      <div className="pt-2 space-y-1">
                        {r.news_signals.articles.map((a, i) => (
                          <div key={i} className="flex gap-2">
                            <span
                              className={
                                a.relevance === "direct" ? "text-accent" : "text-muted"
                              }
                            >
                              [{a.relevance}]
                            </span>
                            <span className="text-foreground flex-1">{a.title}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )}
            </StageCard>

            <StageCard
              title="Reasoning"
              subtitle="thesis + levels"
              status={stage(!!r.reasoned_analysis, false)}
            >
              {r.reasoned_analysis && (
                <>
                  <div className="text-foreground pb-1">{r.reasoned_analysis.thesis}</div>
                  <Field label="direction" value={r.reasoned_analysis.direction} />
                  <Field label="entry" value={fmt(r.reasoned_analysis.entry_price)} />
                  <Field label="stop_loss" value={fmt(r.reasoned_analysis.stop_loss)} />
                  <Field label="take_profit" value={fmt(r.reasoned_analysis.take_profit)} />
                </>
              )}
            </StageCard>

            <StageCard
              title="Evaluation"
              subtitle="veto gate"
              status={evalStatus}
            >
              {r.evaluation_scores && (
                <>
                  <Field label="overall_score" value={fmt(r.evaluation_scores.overall_score)} />
                  {Object.entries(r.evaluation_scores.dimensions).map(([k, v]) => (
                    <Field key={k} label={k} value={fmt(v)} />
                  ))}
                  <Field label="reason" value={r.evaluation_scores.reason} />
                </>
              )}
            </StageCard>

            <StageCard title="Risk" subtitle="sizing gate" status={riskStatus}>
              {r.risk_assessment ? (
                <>
                  <Field label="size_%" value={fmt(r.risk_assessment.position_size_percent)} />
                  <Field label="risk/trade_%" value={fmt(r.risk_assessment.risk_per_trade_percent)} />
                  <Field label="reason" value={r.risk_assessment.reason} />
                </>
              ) : (
                <span className="text-xs">not reached</span>
              )}
            </StageCard>

            <StageCard
              title="Decision"
              status={r.decision ? "pass" : "skipped"}
            >
              {r.decision ? (
                <>
                  <Field label="action" value={r.decision.action} />
                  <Field label="size_%" value={fmt(r.decision.size_percent)} />
                </>
              ) : (
                <span className="text-xs">not reached</span>
              )}
            </StageCard>

            <StageCard
              title="Execution"
              subtitle={r.execution_result?.mode ?? "simulation"}
              status={r.execution_result ? "pass" : r ? "skipped" : "idle"}
            >
              {r.execution_result ? (
                <>
                  <Field label="filled" value={String(r.execution_result.filled)} />
                  <Field label="fill_price" value={fmt(r.execution_result.fill_price)} />
                  <Field label="note" value={r.execution_result.note} />
                </>
              ) : (
                <span className="text-xs">not reached</span>
              )}
            </StageCard>
          </div>

          <div className="mt-6 flex flex-wrap gap-x-8 gap-y-2 rounded-md border border-border bg-surface-2 px-4 py-3 text-xs font-mono text-muted">
            <span>run_id: <span className="text-foreground">{r.trace.run_id}</span></span>
            <span>duration: <span className="text-foreground">{fmt(r.trace.total_ms)}ms</span></span>
            <span>tokens: <span className="text-foreground">{r.trace.total_tokens}</span></span>
            <span>cost: <span className="text-foreground">${fmt(r.trace.total_cost_usd, 6)}</span></span>
          </div>
        </>
      )}

      {!r && !error && (
        <p className="text-sm text-muted text-center py-16">
          Enter a symbol and run a cycle to trace the agent pipeline.
        </p>
      )}
    </div>
  );
}
