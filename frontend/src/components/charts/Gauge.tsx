"use client";

import { C } from "./chart-kit";

const polar = (cx: number, cy: number, r: number, deg: number): [number, number] => {
  const a = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
};

const arc = (cx: number, cy: number, r: number, from: number, to: number) => {
  const [x0, y0] = polar(cx, cy, r, from);
  const [x1, y1] = polar(cx, cy, r, to);
  const large = Math.abs(from - to) > 180 ? 1 : 0;
  return `M${x0.toFixed(1)},${y0.toFixed(1)} A${r},${r} 0 ${large} 1 ${x1.toFixed(1)},${y1.toFixed(1)}`;
};

/** Semicircle gauge for a single value in [0,1]. */
export function Gauge({
  value,
  label,
  color = C.accent,
  sub,
  size = 118,
}: {
  value: number | null;
  label: string;
  color?: string;
  sub?: string;
  size?: number;
}) {
  const w = size;
  const h = size * 0.62;
  const cx = w / 2;
  const cy = h - 6;
  const r = w / 2 - 10;
  const t = value === null ? 0 : Math.max(0, Math.min(1, value));
  // 180° (left) → 0° (right), sweeping over the top.
  const end = 180 - t * 180;

  return (
    <div className="flex flex-col items-center">
      <svg width={w} height={h + 4} className="overflow-visible">
        <path d={arc(cx, cy, r, 180, 0)} fill="none" stroke={C.grid} strokeWidth={7} strokeLinecap="round" />
        {value !== null && (
          <path d={arc(cx, cy, r, 180, end)} fill="none" stroke={color} strokeWidth={7} strokeLinecap="round" />
        )}
        <text x={cx} y={cy - 6} textAnchor="middle" fill={C.fg} fontSize={19} fontFamily="var(--font-mono)" fontWeight={600}>
          {value === null ? "—" : value.toFixed(2)}
        </text>
      </svg>
      <div className="text-xs text-muted mt-0.5">{label}</div>
      {sub && <div className="text-[10px] text-muted/70">{sub}</div>}
    </div>
  );
}
