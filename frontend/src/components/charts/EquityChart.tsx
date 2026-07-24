"use client";

import { useState } from "react";
import { C, inr, useMeasure } from "./chart-kit";

const PAD = { top: 10, right: 10, bottom: 18, left: 46 };

/** Strategy equity curve (from /backtest) — single series line + crosshair. */
export function EquityChart({
  points,
  height = 170,
}: {
  points: { date: string; equity: number }[];
  height?: number;
}) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  if (points.length < 2) {
    return (
      <div ref={ref} className="grid place-items-center text-xs text-muted" style={{ height }}>
        No backtest yet.
      </div>
    );
  }
  if (width === 0) return <div ref={ref} style={{ height }} />;

  // Downsample to at most ~240 points for a clean line.
  const stride = Math.max(1, Math.ceil(points.length / 240));
  const pts = points.filter((_, i) => i % stride === 0);
  if (pts[pts.length - 1] !== points[points.length - 1]) pts.push(points[points.length - 1]);

  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const eq = pts.map((p) => p.equity);
  const lo = Math.min(...eq);
  const hi = Math.max(...eq);
  const span = hi - lo || 1;

  const x = (i: number) => PAD.left + (i / (pts.length - 1)) * plotW;
  const y = (v: number) => PAD.top + (hi - v) / span * plotH;

  const start = pts[0].equity;
  const endV = pts[pts.length - 1].equity;
  const up = endV >= start;
  const col = up ? C.pass : C.fail;

  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(" ");
  const area = `${path} L${x(pts.length - 1).toFixed(1)},${(PAD.top + plotH).toFixed(1)} L${x(0).toFixed(1)},${(PAD.top + plotH).toFixed(1)} Z`;
  const hp = hover !== null ? pts[hover] : null;

  return (
    <div ref={ref} className="relative select-none" style={{ height }}>
      <svg
        width={width}
        height={height}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - rect.left - PAD.left) / plotW) * (pts.length - 1));
          setHover(i >= 0 && i < pts.length ? i : null);
        }}
        onMouseLeave={() => setHover(null)}
      >
        {[hi, (hi + lo) / 2, lo].map((v, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={PAD.left + plotW} y1={y(v)} y2={y(v)} stroke={C.gridSoft} strokeWidth={1} />
            <text x={PAD.left - 5} y={y(v) + 3} textAnchor="end" fill={C.muted} fontSize={9} fontFamily="var(--font-mono)">
              {(v / 1000).toFixed(0)}k
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={PAD.left + plotW} y1={y(start)} y2={y(start)} stroke={C.muted} strokeWidth={1} strokeDasharray="3 3" opacity={0.4} />
        <defs>
          <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={col} stopOpacity={0.22} />
            <stop offset="100%" stopColor={col} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#eqfill)" />
        <path d={path} fill="none" stroke={col} strokeWidth={1.75} />
        {hover !== null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke={C.muted} strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
            <circle cx={x(hover)} cy={y(pts[hover].equity)} r={3} fill={col} stroke={C.surface} strokeWidth={1.5} />
          </>
        )}
      </svg>
      {hp && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-border bg-surface-2/95 px-2 py-1 text-[11px] font-mono shadow-lg"
          style={{ left: Math.min(x(hover!) + 8, width - 130), top: PAD.top }}
        >
          <div className="text-muted">{hp.date}</div>
          <div className="text-foreground">{inr(hp.equity)}</div>
        </div>
      )}
    </div>
  );
}
