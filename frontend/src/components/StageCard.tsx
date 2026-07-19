type Status = "pass" | "halt" | "skipped" | "idle";

const STATUS_STYLES: Record<Status, { dot: string; label: string; ring: string }> = {
  pass: { dot: "bg-pass", label: "text-pass", ring: "border-pass/40" },
  halt: { dot: "bg-halt", label: "text-halt", ring: "border-halt/50" },
  skipped: { dot: "bg-muted", label: "text-muted", ring: "border-border" },
  idle: { dot: "bg-muted/40", label: "text-muted", ring: "border-border" },
};

const STATUS_TEXT: Record<Status, string> = {
  pass: "passed",
  halt: "halted",
  skipped: "skipped",
  idle: "—",
};

export function StageCard({
  title,
  subtitle,
  status,
  children,
}: {
  title: string;
  subtitle?: string;
  status: Status;
  children?: React.ReactNode;
}) {
  const s = STATUS_STYLES[status];
  return (
    <div className={`rounded-lg border bg-surface ${s.ring} transition-colors`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
        <div className="flex items-center gap-3">
          <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
          <div>
            <div className="font-medium text-sm">{title}</div>
            {subtitle && (
              <div className="text-xs text-muted mt-0.5">{subtitle}</div>
            )}
          </div>
        </div>
        <span className={`text-xs font-mono uppercase tracking-wide ${s.label}`}>
          {STATUS_TEXT[status]}
        </span>
      </div>
      {children && (
        <div className="px-4 py-3 text-sm font-mono text-muted space-y-1">
          {children}
        </div>
      )}
    </div>
  );
}

export function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className="text-foreground text-right">{value}</span>
    </div>
  );
}

export type { Status };
