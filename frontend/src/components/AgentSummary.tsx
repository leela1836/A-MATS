"use client";

import { useCallback, useEffect, useState } from "react";
import { getAgentSummary, type AgentSummary as Summary } from "@/lib/api";

const inr = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : "₹" + Math.round(n).toLocaleString("en-IN");
const pct = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className={`text-sm font-mono ${tone ?? "text-foreground"}`}>{value}</div>
      <div className="text-[10px] text-muted uppercase tracking-wide">{label}</div>
    </div>
  );
}

function EdgeTile({ label, b, tone }: { label: string; b: { trades: number; win_rate: number | null; net_pct: number | null }; tone?: string }) {
  return (
    <div className="border border-border/50 rounded-md px-2 py-1.5">
      <div className={tone ?? "text-foreground"}>{b.win_rate == null ? "—" : `${b.win_rate}%`}</div>
      <div className="text-[9px] text-muted uppercase tracking-wide">{label}</div>
      <div className="text-[10px] text-muted">
        {b.trades} tr{b.net_pct != null ? ` · ${b.net_pct >= 0 ? "+" : ""}${b.net_pct}%` : ""}
      </div>
    </div>
  );
}

/** Plain-English "what is the agent doing" readout — mirrors the GitHub Pages panel. */
export function AgentSummary() {
  const [s, setS] = useState<Summary | null>(null);
  const [showFactors, setShowFactors] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setS(await getAgentSummary());
    } catch {
      /* backend offline — keep last known */
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);

  if (!s) return null;
  const t = s.today;
  const dayTone = t.realized_pnl_pct == null ? "text-foreground" : t.realized_pnl_pct >= 0 ? "text-pass" : "text-fail";
  const retTone = (s.portfolio.return_percent ?? 0) >= 0 ? "text-pass" : "text-fail";
  const model = s.learning.model;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">What the agent is doing</span>
        <span className="text-[10px] text-muted font-mono">today · {t.date}</span>
      </div>

      {/* the one-sentence answer */}
      <p className="text-sm text-foreground leading-relaxed mb-3">{s.headline}</p>

      {/* the honest yardstick: agent vs just holding */}
      {s.benchmark.return_percent != null && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-3 text-[11px] font-mono">
          <span className="text-muted uppercase tracking-wide text-[10px]">vs buy &amp; hold</span>
          <span>agent <span className={(s.portfolio.return_percent ?? 0) >= 0 ? "text-pass" : "text-fail"}>{pct(s.portfolio.return_percent)}</span></span>
          <span className="text-muted">hold {pct(s.benchmark.return_percent)}</span>
          {s.benchmark.spread_pct != null && (
            <span>spread <span className={s.benchmark.spread_pct >= 0 ? "text-pass" : "text-fail"}>{s.benchmark.spread_pct >= 0 ? "+" : ""}{s.benchmark.spread_pct.toFixed(2)}%</span></span>
          )}
        </div>
      )}

      {/* today's numbers */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-4">
        <Tile label="scans today" value={String(t.scans)} />
        <Tile label="opened" value={`${t.opened}`} />
        <Tile label="long / short" value={`${t.longs}/${t.shorts}`} />
        <Tile label="closed" value={String(t.closed)} />
        <Tile label="win / loss" value={`${t.wins}/${t.losses}`} tone={t.wins > t.losses ? "text-pass" : t.losses > t.wins ? "text-fail" : "text-foreground"} />
        <Tile label="today P&L" value={pct(t.realized_pnl_pct)} tone={dayTone} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* left: holdings + learning */}
        <div>
          <div className="text-xs text-muted mb-1">
            Open positions ({s.open_positions.length})
          </div>
          {s.open_positions.length ? (
            <div className="max-h-44 overflow-y-auto pr-1 space-y-1.5">
              {s.open_positions.map((p, i) => (
                <div key={i} className="text-[11px] border border-border/50 rounded-md px-2 py-1.5">
                  <div className="flex items-center justify-between font-mono">
                    <span>
                      <span className={p.direction === "long" ? "text-pass" : "text-fail"}>{p.direction}</span>
                      <span className="text-foreground ml-1.5 font-semibold">{p.symbol.replace(".NS", "")}</span>
                      {p.reasoned && <span className="text-accent ml-1.5">✦</span>}
                    </span>
                    <span className="text-muted">
                      {p.entry ?? "—"} → {p.target ?? "—"} · stop {p.stop ?? "—"}
                    </span>
                  </div>
                  {p.thesis && <div className="text-muted mt-1 leading-snug">{p.thesis}</div>}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-muted py-2">Flat — no open positions right now.</div>
          )}
        </div>

        {/* right: learning + memory */}
        <div className="space-y-3">
          <div>
            <div className="text-xs text-muted mb-1">What it has learned</div>
            <div className="text-[11px] text-foreground leading-snug">
              {s.learning.last ? (
                <>
                  Last retrain: <span className="font-mono">{s.learning.last.note}</span>
                  {s.learning.last.oos_auc != null && (
                    <> · OOS AUC <span className="font-mono">{s.learning.last.oos_auc}</span></>
                  )}
                </>
              ) : (
                <>Nothing learned from its own trades yet — it needs closed trades first.</>
              )}
            </div>
            <div className="text-[11px] text-muted mt-1">
              {s.learning.experience_available} of its own trades available to learn from ·{" "}
              model {model.available ? `updated ${(model.updated_at ?? "").slice(0, 10)}` : "not built"}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted mb-1">Memory</div>
            <div className="text-[11px] text-muted leading-snug">{s.memory.what_it_is}</div>
            <div className="text-[11px] text-foreground font-mono mt-1">
              journal: {s.memory.journal_decisions_total} decisions · {s.memory.journal_experiences} experiences · weights: {s.memory.model_path}
            </div>
          </div>
        </div>
      </div>

      {/* what the agent is actually good & bad at — persisted insights */}
      {s.insights && s.insights.overall.resolved > 0 && (
        <div className="mt-3 border-t border-border/50 pt-3">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs text-muted">What it's good &amp; bad at <span className="text-[10px]">(edge, stored each scan)</span></div>
            {s.regime && (
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${s.regime.regime === "bull" ? "text-pass border-pass/40" : s.regime.regime === "bear" ? "text-fail border-fail/40" : "text-muted border-border"}`} title={s.regime.note}>
                regime: {s.regime.regime}{s.regime.regime === "bull" ? " · shorts gated" : ""}
              </span>
            )}
          </div>
          <p className="text-[11px] text-foreground leading-snug mb-1">{s.insights.headline}</p>
          {s.insights.caveat && (
            <p className={`text-[10px] leading-snug mb-2 ${s.insights.significant ? "text-muted" : "text-[#f0883e]"}`}>⚠ {s.insights.caveat}</p>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2 text-[11px] font-mono">
            <EdgeTile label="long win" b={s.insights.by_direction.long} tone="text-pass" />
            <EdgeTile label="short win" b={s.insights.by_direction.short} tone="text-fail" />
            <EdgeTile label={`NN≥${s.insights.nn_gate.threshold}`} b={s.insights.nn_gate.hi} tone="text-pass" />
            <EdgeTile label={`NN<${s.insights.nn_gate.threshold}`} b={s.insights.nn_gate.lo} tone="text-muted" />
          </div>
          {s.insights.suggestion && (
            <div className="text-[11px] text-accent leading-snug">↳ {s.insights.suggestion}</div>
          )}
        </div>
      )}

      {/* factors the agent tracks (and what's missing) */}
      <div className="mt-3 border-t border-border/50 pt-2">
        <button
          onClick={() => setShowFactors((v) => !v)}
          className="text-[11px] text-accent hover:underline"
        >
          {showFactors ? "▾" : "▸"} Factors it tracks ({s.factors.tracked.length}) & what's missing
        </button>
        {showFactors && (
          <div className="mt-2">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {s.factors.tracked.map((f) => (
                <span key={f} className="text-[10px] font-mono text-muted border border-border rounded px-1.5 py-0.5">
                  {f}
                </span>
              ))}
            </div>
            <div className="text-[11px] text-muted leading-snug">{s.factors.note}</div>
          </div>
        )}
      </div>
    </div>
  );
}
