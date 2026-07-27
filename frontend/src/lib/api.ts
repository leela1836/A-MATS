// Typed client for the A-MATS FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export interface CandlePattern {
  name: string;
  direction: string;
  strength: number;
  bars: number;
  note: string;
}

export interface MarketAnalysis {
  symbol: string;
  last_price: number | null;
  trend: string;
  signal: string;
  confidence: number;
  indicators: Record<string, number | null>;
  patterns: CandlePattern[];
  pattern_bias: string;
  pattern_score: number;
  nn_score: number | null;
  support: number | null;
  resistance: number | null;
}

export interface SRLevel {
  price: number;
  kind: string; // "support" | "resistance"
  strength: number;
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number;
  ema50: number;
  ema200: number;
  pattern: string | null;
  pattern_dir: string | null;
}

export interface CandlesResponse {
  symbol: string;
  period: string;
  bars: Candle[];
  levels: SRLevel[];
  support: number | null;
  resistance: number | null;
}

export interface NewsArticleRef {
  title: string;
  source: string;
  url: string;
  relevance: string;
  age_hours: number | null;
}

export interface NewsSignals {
  symbol: string;
  sentiment_score: number;
  sentiment_label: string;
  confidence: number;
  key_events: string[];
  summary: string;
  article_count: number;
  sources_used: string[];
  articles: NewsArticleRef[];
}

export interface ReasonedAnalysis {
  symbol: string;
  thesis: string;
  direction: string;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  entry_rationale: string;
  confirmation: string;
  invalidation: string;
  risk_reward: number;
  est_hold_days: number | null;
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

export interface MarketStatus {
  is_open: boolean;
  reason: string;
  now_ist: string;
  session: string;
  next_open_ist: string | null;
}

export interface RunResult {
  run_id: string;
  symbol: string;
  halted: boolean;
  halt_reason: string;
  market_analysis: MarketAnalysis | null;
  news_signals: NewsSignals | null;
  reasoned_analysis: ReasonedAnalysis | null;
  evaluation_scores: EvaluationScores | null;
  risk_assessment: RiskAssessment | null;
  decision: TradingDecision | null;
  execution_result: ExecutionResult | null;
  portfolio: Portfolio;
  market_status: MarketStatus;
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

export async function getCandles(symbol: string, bars = 130): Promise<CandlesResponse> {
  const res = await fetch(
    `${API_BASE}/candles/${encodeURIComponent(symbol)}?bars=${bars}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`Candles fetch failed (${res.status})`);
  return res.json();
}

export interface BacktestMetrics {
  symbol: string;
  period: string;
  total_return_pct: number;
  total_trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  max_drawdown_pct: number;
  sharpe: number | null;
  sample_warning?: string;
}

export interface BacktestResponse {
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number }[];
}

export async function getBacktest(symbol: string, period = "2y"): Promise<BacktestResponse> {
  const res = await fetch(
    `${API_BASE}/backtest/${encodeURIComponent(symbol)}?period=${period}&include_trades=false`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`Backtest failed (${res.status})`);
  return res.json();
}

export interface JournalStats {
  scans: number;
  decisions: number;
  directional_calls: number;
  open: number;
  closed_resolved: number;
  wins: number;
  win_rate_pct: number | null;
}

export interface JournalDecision {
  id: number;
  ts: string;
  symbol: string;
  direction: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  nn_score: number | null;
  screen_score: number | null;
  screen_rank: number | null;
  status: string;
  outcome: string | null;
  pnl_pct: number | null;
}

export interface EquityPoint {
  ts: string;
  equity: number;
  return_percent: number | null;
  open_positions: number;
  benchmark: number | null;
}

export async function getJournalEquity(): Promise<{ equity_curve: EquityPoint[]; stats: JournalStats }> {
  const res = await fetch(`${API_BASE}/journal/equity`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Journal equity fetch failed (${res.status})`);
  return res.json();
}

export async function getJournalDecisions(limit = 30): Promise<JournalDecision[]> {
  const res = await fetch(`${API_BASE}/journal/decisions?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Journal decisions fetch failed (${res.status})`);
  return (await res.json()).decisions;
}

export interface AgentSummary {
  generated_at: string;
  headline: string;
  today: {
    date: string;
    scans: number;
    opened: number;
    longs: number;
    shorts: number;
    closed: number;
    wins: number;
    losses: number;
    realized_pnl_pct: number | null;
  };
  track_record: JournalStats;
  benchmark: {
    equity: number | null;
    return_percent: number | null;
    spread_pct: number | null;
    label: string;
  };
  portfolio: {
    equity: number | null;
    total_pnl: number | null;
    return_percent: number | null;
    cash: number | null;
    realized_pnl: number | null;
    unrealized_pnl: number | null;
  };
  open_positions: {
    symbol: string;
    direction: string;
    entry: number | null;
    stop: number | null;
    target: number | null;
    nn_score: number | null;
    reasoned: boolean;
    thesis: string;
  }[];
  learning: {
    events: {
      ts: string;
      trained: number;
      experience_samples: number | null;
      bootstrap_samples: number | null;
      oos_auc: number | null;
      note: string;
    }[];
    last: {
      ts: string;
      trained: number;
      oos_auc: number | null;
      note: string;
    } | null;
    experience_available: number;
    model: {
      available: boolean;
      updated_at?: string;
      trained_on?: string | null;
      oos_auc?: number | null;
    };
  };
  memory: {
    what_it_is: string;
    journal_experiences: number;
    journal_decisions_total: number;
    model_path: string;
    model_updated: string | null;
  };
  factors: { note: string; tracked: string[] };
}

export async function getAgentSummary(): Promise<AgentSummary> {
  const res = await fetch(`${API_BASE}/agent/summary`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Agent summary fetch failed (${res.status})`);
  return res.json();
}

export async function triggerLearn(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/learn`, { method: "POST" });
  if (!res.ok) throw new Error(`Learn failed (${res.status})`);
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
