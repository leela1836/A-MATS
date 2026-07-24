"use client";

import { useState } from "react";
import type { Candle } from "@/lib/api";
import { C, inr, ticks, useMeasure } from "./chart-kit";

export interface Levels {
  entry?: number | null;
  stop?: number | null;
  target?: number | null;
}

const PAD = { top: 14, right: 56, bottom: 22, left: 8 };
const VOL_H = 34; // volume strip height at the bottom of the price area

export function CandleChart({
  candles,
  levels,
  height = 340,
}: {
  candles: Candle[];
  levels?: Levels;
  height?: number;
}) {
  const [ref, width] = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  if (candles.length === 0) {
    return (
      <div ref={ref} className="grid place-items-center text-sm text-muted" style={{ height }}>
        No price data — run a cycle.
      </div>
    );
  }
  if (width === 0) {
    // First paint before measurement; reserve the space to avoid layout jump.
    return <div ref={ref} style={{ height }} />;
  }

  const plotW = width - PAD.left - PAD.right;
  const priceH = height - PAD.top - PAD.bottom - VOL_H;

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const emas = candles.flatMap((c) => [c.ema20, c.ema50, c.ema200]);
  const levelVals = [levels?.entry, levels?.stop, levels?.target].filter(
    (v): v is number => typeof v === "number",
  );
  const pMax = Math.max(...highs, ...emas, ...levelVals);
  const pMin = Math.min(...lows, ...emas, ...levelVals);
  const span = pMax - pMin || 1;
  const padSpan = span * 0.06;
  const lo = pMin - padSpan;
  const hi = pMax + padSpan;

  const maxVol = Math.max(...candles.map((c) => c.volume), 1);

  const n = candles.length;
  const slot = plotW / n;
  const bodyW = Math.max(1.5, Math.min(slot * 0.62, 9));

  const x = (i: number) => PAD.left + slot * (i + 0.5);
  const y = (p: number) => PAD.top + (hi - p) / (hi - lo) * priceH;
  const volY = (v: number) => PAD.top + priceH + VOL_H - (v / maxVol) * VOL_H;

  const line = (key: "ema20" | "ema50" | "ema200") =>
    candles.map((c, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(c[key]).toFixed(1)}`).join(" ");

  const priceTicks = ticks(lo, hi, 4);
  const hc = hover !== null ? candles[hover] : null;

  return (
    <div ref={ref} className="relative select-none" style={{ height }}>
      <svg
        width={width}
        height={height}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.floor((e.clientX - rect.left - PAD.left) / slot);
          setHover(i >= 0 && i < n ? i : null);
        }}
        onMouseLeave={() => setHover(null)}
      >
        {/* horizontal gridlines + price axis */}
        {priceTicks.map((p, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={PAD.left + plotW} y1={y(p)} y2={y(p)} stroke={C.gridSoft} strokeWidth={1} />
            <text x={PAD.left + plotW + 6} y={y(p) + 3} fill={C.muted} fontSize={10} fontFamily="var(--font-mono)">
              {p.toFixed(0)}
            </text>
          </g>
        ))}

        {/* volume strip */}
        {candles.map((c, i) => (
          <rect
            key={`v${i}`}
            x={x(i) - bodyW / 2}
            y={volY(c.volume)}
            width={bodyW}
            height={PAD.top + priceH + VOL_H - volY(c.volume)}
            fill={c.close >= c.open ? C.up : C.down}
            opacity={0.22}
          />
        ))}

        {/* EMA overlays */}
        <path d={line("ema200")} fill="none" stroke={C.ema200} strokeWidth={1.75} opacity={0.9} />
        <path d={line("ema50")} fill="none" stroke={C.ema50} strokeWidth={1.75} opacity={0.9} />
        <path d={line("ema20")} fill="none" stroke={C.ema20} strokeWidth={1.75} opacity={0.9} />

        {/* candles */}
        {candles.map((c, i) => {
          const up = c.close >= c.open;
          const col = up ? C.up : C.down;
          const bodyTop = y(Math.max(c.open, c.close));
          const bodyBot = y(Math.min(c.open, c.close));
          return (
            <g key={i}>
              <line x1={x(i)} x2={x(i)} y1={y(c.high)} y2={y(c.low)} stroke={col} strokeWidth={1} />
              <rect
                x={x(i) - bodyW / 2}
                y={bodyTop}
                width={bodyW}
                height={Math.max(1, bodyBot - bodyTop)}
                fill={col}
              />
              {c.pattern_dir && (
                <circle
                  cx={x(i)}
                  cy={c.pattern_dir === "bullish" ? y(c.low) + 8 : y(c.high) - 8}
                  r={2.6}
                  fill={c.pattern_dir === "bullish" ? C.up : C.down}
                  stroke={C.surface}
                  strokeWidth={1}
                />
              )}
            </g>
          );
        })}

        {/* reasoning levels */}
        {(["entry", "stop", "target"] as const).map((k) => {
          const v = levels?.[k];
          if (typeof v !== "number") return null;
          const col = k === "entry" ? C.accent : k === "stop" ? C.fail : C.pass;
          return (
            <g key={k}>
              <line x1={PAD.left} x2={PAD.left + plotW} y1={y(v)} y2={y(v)} stroke={col} strokeWidth={1} strokeDasharray="4 3" opacity={0.8} />
              <text x={PAD.left + plotW + 6} y={y(v) + 3} fill={col} fontSize={9} fontFamily="var(--font-mono)">
                {k[0]}
              </text>
            </g>
          );
        })}

        {/* crosshair */}
        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + priceH} stroke={C.muted} strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
        )}

        {/* EMA legend */}
        <g fontFamily="var(--font-mono)" fontSize={10}>
          {[["EMA20", C.ema20], ["EMA50", C.ema50], ["EMA200", C.ema200]].map(([label, col], i) => (
            <g key={label as string} transform={`translate(${PAD.left + 4 + i * 66}, ${PAD.top + 2})`}>
              <rect width={9} height={2.5} y={-2} rx={1} fill={col as string} />
              <text x={13} y={2} fill={C.muted}>{label}</text>
            </g>
          ))}
        </g>
      </svg>

      {/* tooltip */}
      {hc && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-border bg-surface-2/95 px-2.5 py-1.5 text-[11px] font-mono shadow-lg"
          style={{
            left: Math.min(Math.max(x(hover!) + 10, 4), width - 150),
            top: PAD.top + 4,
          }}
        >
          <div className="text-muted mb-0.5">{hc.date}</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <span className="text-muted">O</span><span className="text-foreground text-right">{hc.open}</span>
            <span className="text-muted">H</span><span className="text-foreground text-right">{hc.high}</span>
            <span className="text-muted">L</span><span className="text-foreground text-right">{hc.low}</span>
            <span className="text-muted">C</span>
            <span className={`text-right ${hc.close >= hc.open ? "text-pass" : "text-fail"}`}>{hc.close}</span>
            <span className="text-muted">Vol</span>
            <span className="text-foreground text-right">{(hc.volume / 1e6).toFixed(1)}M</span>
          </div>
          {hc.pattern && (
            <div className={`mt-1 ${hc.pattern_dir === "bullish" ? "text-pass" : "text-fail"}`}>
              {hc.pattern}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
