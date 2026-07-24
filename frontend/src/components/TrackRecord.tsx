"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getJournalDecisions,
  getJournalEquity,
  triggerLearn,
  type EquityPoint,
  type JournalDecision,
  type JournalStats,
} from "@/lib/api";
import { EquityChart } from "./charts/EquityChart";

const DIR: Record<string, string> = { long: "text-pass", short: "text-fail", hold: "text-muted" };
const OUT: Record<string, string> = { win: "text-pass", loss: "text-fail", none: "text-muted", flat: "text-muted" };

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className={`text-sm font-mono ${tone ?? "text-foreground"}`}>{value}</div>
      <div className="text-[10px] text-muted">{label}</div>
    </div>
  );
}

export function TrackRecord() {
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [decisions, setDecisions] = useState<JournalDecision[]>([]);
  const [learning, setLearning] = useState(false);
  const [learnMsg, setLearnMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [eq, decs] = await Promise.all([getJournalEquity(), getJournalDecisions(30)]);
      setEquity(eq.equity_curve);
      setStats(eq.stats);
      setDecisions(decs);
    } catch {
      /* backend offline — keep last known */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const learn = async () => {
    setLearning(true);
    setLearnMsg(null);
    try {
      const r = await triggerLearn();
      setLearnMsg(
        r.trained
          ? `retrained on ${r.experience_samples} lived + ${r.bootstrap_samples} bootstrap trades · OOS AUC ${r.oos_auc}`
          : `not enough data yet (${r.experience_samples} lived trades)`,
      );
      refresh();
    } catch (e) {
      setLearnMsg(e instanceof Error ? e.message : "learn failed");
    } finally {
      setLearning(false);
    }
  };

  const curve = equity.map((p) => ({ date: p.ts.slice(0, 10), equity: p.equity }));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-sm font-medium">Track record</span>
          <span className="text-xs text-muted ml-2">the agent's own history — watch it learn</span>
        </div>
        <button
          onClick={learn}
          disabled={learning}
          className="rounded-md border border-accent/50 text-accent px-3 py-1 text-xs font-medium hover:bg-accent/10 disabled:opacity-40 transition-colors"
        >
          {learning ? "Learning…" : "Learn now"}
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-3">
          <Tile label="scans" value={String(stats.scans)} />
          <Tile label="decisions" value={String(stats.decisions)} />
          <Tile label="open" value={String(stats.open)} />
          <Tile label="resolved" value={String(stats.closed_resolved)} />
          <Tile label="wins" value={String(stats.wins)} tone="text-pass" />
          <Tile
            label="win rate"
            value={stats.win_rate_pct === null ? "—" : `${stats.win_rate_pct}%`}
            tone={stats.win_rate_pct && stats.win_rate_pct >= 50 ? "text-pass" : "text-foreground"}
          />
        </div>
      )}

      {learnMsg && <div className="text-[11px] text-muted font-mono mb-3">↳ {learnMsg}</div>}

      {curve.length >= 2 ? (
        <EquityChart points={curve} height={140} />
      ) : (
        <div className="grid place-items-center text-xs text-muted h-[120px]">
          No equity history yet — run scans (or the scheduled job) to build it.
        </div>
      )}

      {decisions.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-muted mb-1">Recent decisions</div>
          <div className="max-h-56 overflow-y-auto">
            <table className="w-full text-[11px] font-mono">
              <thead className="text-muted sticky top-0 bg-surface">
                <tr className="text-left">
                  <th className="py-1 pr-2">symbol</th>
                  <th className="pr-2">dir</th>
                  <th className="pr-2 text-right">entry</th>
                  <th className="pr-2 text-right">P(win)</th>
                  <th className="pr-2">status</th>
                  <th className="text-right">P&L%</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d) => (
                  <tr key={d.id} className="border-t border-border/40">
                    <td className="py-1 pr-2 text-foreground">{d.symbol}</td>
                    <td className={`pr-2 ${DIR[d.direction] ?? "text-muted"}`}>{d.direction}</td>
                    <td className="pr-2 text-right text-muted">{d.entry_price ?? "—"}</td>
                    <td className="pr-2 text-right text-muted">{d.nn_score ?? "—"}</td>
                    <td className={`pr-2 ${OUT[d.outcome ?? "none"] ?? "text-muted"}`}>
                      {d.status === "closed" && d.outcome && d.outcome !== "flat" ? d.outcome : d.status}
                    </td>
                    <td className={`text-right ${d.pnl_pct && d.pnl_pct > 0 ? "text-pass" : d.pnl_pct && d.pnl_pct < 0 ? "text-fail" : "text-muted"}`}>
                      {d.pnl_pct === null || d.pnl_pct === undefined ? "—" : `${d.pnl_pct > 0 ? "+" : ""}${d.pnl_pct}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
