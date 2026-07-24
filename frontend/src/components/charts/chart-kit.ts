"use client";

import { useEffect, useRef, useState } from "react";

/** Measure a container's width so SVG charts render at crisp, real pixels
 *  instead of being scaled (which would distort stroke widths). */
export function useMeasure<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      setWidth(Math.round(entries[0].contentRect.width));
    });
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Validated chart palette. EMA trio passed the dataviz six-checks against the
 *  dark surface; candles use the status green/red (a separate polarity job). */
export const C = {
  up: "#3fb950",
  down: "#f85149",
  ema20: "#2f7ff0",
  ema50: "#b8860b",
  ema200: "#9a6ae0",
  accent: "#4f9dff",
  pass: "#3fb950",
  halt: "#f0883e",
  fail: "#f85149",
  grid: "#232c3d",
  gridSoft: "#1a2130",
  muted: "#8b98ab",
  fg: "#e6edf3",
  surface: "#131824",
} as const;

export const inr = (n: number, digits = 0) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: digits,
  }).format(n);

/** Nice-ish evenly spaced ticks across [min,max]. */
export function ticks(min: number, max: number, count = 4): number[] {
  if (!isFinite(min) || !isFinite(max) || min === max) return [min];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}
