"use client";

import type { MarketAnalysis, NewsSignals } from "@/lib/api";
import { Gauge } from "./charts/Gauge";
import { Meter } from "./charts/Meter";
import { C } from "./charts/chart-kit";

const SIGNAL_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  long: { bg: "bg-pass/15", text: "text-pass", label: "LONG" },
  short: { bg: "bg-fail/15", text: "text-fail", label: "SHORT" },
  hold: { bg: "bg-muted/15", text: "text-muted", label: "HOLD" },
};

function biasColor(bias: string) {
  return bias === "bullish" ? C.pass : bias === "bearish" ? C.fail : C.muted;
}

export function SignalPanel({
  market,
  news,
}: {
  market: MarketAnalysis | null;
  news: NewsSignals | null;
}) {
  const sig = (market?.signal ?? "hold").toLowerCase();
  const s = SIGNAL_STYLE[sig] ?? SIGNAL_STYLE.hold;
  const nn = market?.nn_score ?? null;
  const nnColor = nn === null ? C.muted : nn >= 0.5 ? C.pass : nn >= 0.35 ? C.halt : C.fail;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-muted">Signal</div>
          <div className="text-xs text-muted/70 mt-0.5">
            trend <span className="text-foreground">{market?.trend ?? "—"}</span>
          </div>
        </div>
        <span className={`rounded-md px-3 py-1 text-sm font-semibold tracking-wide ${s.bg} ${s.text}`}>
          {s.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Gauge value={nn} label="P(win) · NN" color={nnColor} sub="learned validator" />
        <Gauge value={market?.confidence ?? null} label="confidence" color={C.accent} sub="rule engine" />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-muted">Candlesticks</span>
          <span className="text-xs font-mono" style={{ color: biasColor(market?.pattern_bias ?? "none") }}>
            {market?.pattern_bias ?? "none"}
            {market && market.pattern_score !== 0 ? ` ${market.pattern_score > 0 ? "+" : ""}${market.pattern_score}` : ""}
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {market?.patterns?.length ? (
            market.patterns.map((p) => (
              <span
                key={p.name}
                className="rounded px-1.5 py-0.5 text-[11px] font-mono"
                style={{
                  color: biasColor(p.direction),
                  background: "var(--surface-2)",
                }}
                title={p.note}
              >
                {p.name}
              </span>
            ))
          ) : (
            <span className="text-[11px] font-mono text-muted">none detected</span>
          )}
        </div>
      </div>

      {news && (
        <Meter
          value={news.sentiment_score}
          label="News sentiment"
          caption={`(${news.sentiment_label}, ${news.article_count})`}
        />
      )}
    </div>
  );
}
