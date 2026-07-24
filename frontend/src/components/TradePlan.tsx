"use client";

import type { ReasonedAnalysis } from "@/lib/api";

const inr = (n: number | null) =>
  n === null || n === undefined
    ? "—"
    : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n);

const DIR: Record<string, { text: string; label: string }> = {
  long: { text: "text-pass", label: "LONG" },
  short: { text: "text-fail", label: "SHORT" },
  hold: { text: "text-muted", label: "HOLD / WAIT" },
};

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-2 border-b border-border/50 last:border-0">
      <div className="text-[11px] uppercase tracking-wide text-muted mb-0.5">{label}</div>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  );
}

export function TradePlan({ r }: { r: ReasonedAnalysis | null }) {
  if (!r) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4">
        <div className="text-sm font-medium mb-1">Trade plan</div>
        <div className="text-xs text-muted">Run a cycle to generate the plan.</div>
      </div>
    );
  }

  const dir = DIR[r.direction] ?? DIR.hold;
  const isHold = r.direction === "hold";

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">Trade plan</span>
        <span className={`text-sm font-semibold ${dir.text}`}>{dir.label}</span>
      </div>

      {isHold ? (
        <>
          <Line label="Why no trade">{r.entry_rationale}</Line>
          <Line label="What would confirm an entry">{r.confirmation}</Line>
          <p className="text-xs text-muted mt-2">{r.thesis}</p>
        </>
      ) : (
        <>
          {/* entry / exits / duration at a glance */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <Stat label="Entry" value={inr(r.entry_price)} tone="text-foreground" />
            <Stat label="Stop (exit)" value={inr(r.stop_loss)} tone="text-fail" />
            <Stat label="Target (exit)" value={inr(r.take_profit)} tone="text-pass" />
            <Stat
              label="Reward : Risk"
              value={r.risk_reward ? `${r.risk_reward.toFixed(1)} : 1` : "—"}
              tone={r.risk_reward >= 2 ? "text-pass" : r.risk_reward >= 1.5 ? "text-halt" : "text-fail"}
            />
          </div>
          <div className="mb-2 text-xs text-muted">
            Est. holding duration:{" "}
            <span className="text-foreground font-mono">
              {r.est_hold_days ? `~${r.est_hold_days} trading day${r.est_hold_days === 1 ? "" : "s"}` : "—"}
            </span>{" "}
            <span className="text-muted/70">(ATR-based estimate; real holds often run longer)</span>
          </div>

          <Line label="Why this is the entry">{r.entry_rationale}</Line>
          <Line label="Confirmation trigger">{r.confirmation}</Line>
          <Line label="Invalidation (thesis is wrong if)">{r.invalidation}</Line>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`text-sm font-mono ${tone}`}>{value}</div>
    </div>
  );
}
