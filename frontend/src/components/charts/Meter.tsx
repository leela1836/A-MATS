"use client";

import { C } from "./chart-kit";

/** Diverging meter for a value in [-1,1] — polarity, two hues + neutral mid. */
export function Meter({
  value,
  label,
  caption,
}: {
  value: number;
  label: string;
  caption?: string;
}) {
  const t = Math.max(-1, Math.min(1, value));
  const pct = ((t + 1) / 2) * 100; // 0..100 across the track
  const mid = 50;
  const pos = t >= 0;
  const col = t > 0.15 ? C.pass : t < -0.15 ? C.fail : C.muted;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-xs text-muted">{label}</span>
        <span className="text-xs font-mono" style={{ color: col }}>
          {t > 0 ? "+" : ""}{t.toFixed(2)}{caption ? ` ${caption}` : ""}
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-surface-2 overflow-hidden">
        {/* fill from midpoint toward the value */}
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${pos ? mid : pct}%`,
            width: `${Math.abs(pct - mid)}%`,
            background: col,
          }}
        />
        {/* neutral midpoint tick */}
        <div className="absolute top-0 bottom-0 w-px bg-muted/50" style={{ left: `${mid}%` }} />
      </div>
    </div>
  );
}
