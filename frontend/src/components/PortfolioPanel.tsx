import type { PaperTrade, Portfolio } from "@/lib/api";

const inr = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);

const inr2 = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(n);

function pnlClass(n: number) {
  return n > 0 ? "text-pass" : n < 0 ? "text-fail" : "text-muted";
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      <span className={`text-sm font-mono ${tone ?? "text-foreground"}`}>{value}</span>
    </div>
  );
}

export function PortfolioPanel({
  portfolio,
  trades,
  onReset,
}: {
  portfolio: Portfolio;
  trades: PaperTrade[];
  onReset: () => void;
}) {
  const p = portfolio;
  const sign = (n: number) => (n > 0 ? "+" : "");

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
        <div>
          <div className="font-medium text-sm">Paper Portfolio</div>
          <div className="text-xs text-muted mt-0.5">
            in-app · virtual {p.currency}
          </div>
        </div>
        <button
          onClick={onReset}
          className="text-xs font-mono text-muted hover:text-fail border border-border rounded px-2 py-1 transition-colors"
        >
          reset
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 px-4 py-4 border-b border-border/60">
        <Stat label="Equity" value={inr(p.equity)} />
        <Stat label="Cash" value={inr(p.cash)} />
        <Stat
          label="Total P&L"
          value={`${sign(p.total_pnl)}${inr(p.total_pnl)}`}
          tone={pnlClass(p.total_pnl)}
        />
        <Stat
          label="Return"
          value={`${sign(p.return_percent)}${p.return_percent.toFixed(2)}%`}
          tone={pnlClass(p.return_percent)}
        />
        <Stat
          label="Realized"
          value={`${sign(p.realized_pnl)}${inr(p.realized_pnl)}`}
          tone={pnlClass(p.realized_pnl)}
        />
        <Stat
          label="Unrealized"
          value={`${sign(p.unrealized_pnl)}${inr(p.unrealized_pnl)}`}
          tone={pnlClass(p.unrealized_pnl)}
        />
        <Stat label="Positions" value={String(p.open_positions.length)} />
        <Stat label="Trades" value={String(p.trade_count)} />
      </div>

      {p.open_positions.length > 0 && (
        <div className="px-4 py-3 border-b border-border/60">
          <div className="text-xs text-muted mb-2">Open positions</div>
          <div className="space-y-1 font-mono text-xs">
            {p.open_positions.map((pos) => (
              <div key={pos.symbol} className="flex items-center justify-between gap-3">
                <span className="text-foreground">{pos.symbol}</span>
                <span className="text-muted">
                  {pos.qty} @ {inr2(pos.avg_price)} → {inr2(pos.mark_price)}
                </span>
                <span className={pnlClass(pos.unrealized_pnl)}>
                  {sign(pos.unrealized_pnl)}
                  {inr2(pos.unrealized_pnl)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {trades.length > 0 && (
        <div className="px-4 py-3">
          <div className="text-xs text-muted mb-2">Recent trades</div>
          <div className="space-y-1 font-mono text-xs">
            {trades.map((t) => (
              <div key={t.seq} className="flex items-center justify-between gap-3">
                <span className={t.side === "buy" ? "text-accent" : "text-halt"}>
                  {t.side.toUpperCase()} {t.qty}
                </span>
                <span className="text-foreground">{t.symbol}</span>
                <span className="text-muted">@ {inr2(t.price)}</span>
                <span className={pnlClass(t.realized_pnl)}>
                  {t.realized_pnl !== 0
                    ? `${sign(t.realized_pnl)}${inr2(t.realized_pnl)}`
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
