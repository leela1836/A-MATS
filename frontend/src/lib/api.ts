// Typed client for the A-MATS FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export interface MarketAnalysis {
  symbol: string;
  last_price: number | null;
  trend: string;
  signal: string;
  confidence: number;
  indicators: Record<string, number | null>;
}

export interface ReasonedAnalysis {
  symbol: string;
  thesis: string;
  direction: string;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
}

export interface EvaluationScores {
  passed: boolean;
  overall_score: number;
  dimensions: Record<string, number>;
  reason: string;
}

export interface RiskAssessment {
  approved: boolean;
  position_size_percent: number;
  risk_per_trade_percent: number;
  reason: string;
}

export interface TradingDecision {
  symbol: string;
  action: string;
  size_percent: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  rationale: string;
}

export interface ExecutionResult {
  symbol: string;
  filled: boolean;
  action: string;
  qty: number;
  fill_price: number | null;
  size_percent: number;
  mode: string;
  note: string;
}

export interface OpenPosition {
  symbol: string;
  qty: number;
  avg_price: number;
  mark_price: number;
  unrealized_pnl: number;
}

export interface Portfolio {
  currency: string;
  starting_cash: number;
  cash: number;
  positions_value: number;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  return_percent: number;
  open_positions: OpenPosition[];
  trade_count: number;
}

export interface PaperTrade {
  seq: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  commission: number;
  realized_pnl: number;
  cash_after: number;
  note: string;
}

export interface NodeTrace {
  node: string;
  duration_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  note: string;
}

export interface RunTrace {
  run_id: string;
  total_ms: number;
  total_tokens: number;
  total_cost_usd: number;
  nodes: NodeTrace[];
}

export interface RunResult {
  run_id: string;
  symbol: string;
  halted: boolean;
  halt_reason: string;
  market_analysis: MarketAnalysis | null;
  reasoned_analysis: ReasonedAnalysis | null;
  evaluation_scores: EvaluationScores | null;
  risk_assessment: RiskAssessment | null;
  decision: TradingDecision | null;
  execution_result: ExecutionResult | null;
  portfolio: Portfolio;
  trace: RunTrace;
}

export async function runCycle(symbol: string): Promise<RunResult> {
  const res = await fetch(`${API_BASE}/run/${encodeURIComponent(symbol)}`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(`Run failed (${res.status}): ${await res.text()}`);
  }
  return res.json();
}

export async function getPortfolio(): Promise<Portfolio> {
  const res = await fetch(`${API_BASE}/portfolio`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Portfolio fetch failed (${res.status})`);
  return res.json();
}

export async function getTrades(limit = 20): Promise<PaperTrade[]> {
  const res = await fetch(`${API_BASE}/trades?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Trades fetch failed (${res.status})`);
  return (await res.json()).trades;
}

export async function resetPortfolio(): Promise<Portfolio> {
  const res = await fetch(`${API_BASE}/portfolio/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`Reset failed (${res.status})`);
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}
