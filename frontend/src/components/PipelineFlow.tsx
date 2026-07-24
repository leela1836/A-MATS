"use client";

import type { Status } from "./StageCard";

const DOT: Record<Status, string> = {
  pass: "bg-pass",
  halt: "bg-halt",
  skipped: "bg-muted/50",
  idle: "bg-muted/30",
};
const RING: Record<Status, string> = {
  pass: "border-pass/50",
  halt: "border-halt/60",
  skipped: "border-border",
  idle: "border-border",
};
const TEXT: Record<Status, string> = {
  pass: "text-foreground",
  halt: "text-halt",
  skipped: "text-muted",
  idle: "text-muted",
};

export interface Stage {
  key: string;
  label: string;
  status: Status;
  value?: string;
}

export function PipelineFlow({
  stages,
  selected,
  onSelect,
}: {
  stages: Stage[];
  selected?: string;
  onSelect?: (key: string) => void;
}) {
  return (
    <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
      {stages.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onSelect?.(s.key)}
            className={`flex flex-col items-start gap-1 rounded-lg border bg-surface px-3 py-2 min-w-[92px] text-left transition-colors hover:bg-surface-2 ${RING[s.status]} ${
              selected === s.key ? "ring-1 ring-accent/60" : ""
            }`}
          >
            <div className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${DOT[s.status]}`} />
              <span className={`text-xs font-medium ${TEXT[s.status]}`}>{s.label}</span>
            </div>
            <span className="text-[11px] font-mono text-muted truncate max-w-[80px]">
              {s.value ?? "—"}
            </span>
          </button>
          {i < stages.length - 1 && (
            <span className={`text-sm ${stages[i + 1].status === "idle" ? "text-border" : "text-muted"}`}>›</span>
          )}
        </div>
      ))}
    </div>
  );
}
