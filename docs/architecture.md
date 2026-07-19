# A-MATS Architecture Document

## Autonomous Multi-Agent Trading System — MVP v1.0

---

## 1. System Overview

A-MATS is an enterprise-grade autonomous multi-agent trading system that uses a **LangGraph-based state machine** to orchestrate specialized AI agents. Each agent performs a distinct function in the trading pipeline, from market analysis to post-trade reflection.

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Web Dashboard (Next.js)                      │
│                    Real-time UI / Configuration / Monitoring          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ REST API / WebSocket
┌───────────────────────────▼─────────────────────────────────────────┐
│                       FastAPI Backend Server                         │
│              REST Endpoints + WebSocket + Background Tasks            │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                    LangGraph State Machine (Orchestrator)             │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │Supervisor│  │  Market  │  │   News   │  │Knowledge │             │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │             │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│        │            │             │             │                    │
│        └────────────┴─────────────┴─────────────┘                    │
│                            │                                         │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Reasoning Engine                          │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Evaluation Engine                         │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Risk Engine                               │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Decision Engine                           │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │         Execution / Simulation Engine                  │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Reflection Engine                         │            │
│  └────────────────────────┬─────────────────────────────┘            │
│  ┌────────────────────────▼─────────────────────────────┐            │
│  │              Learning Engine                           │            │
│  └───────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                         Data Layer                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  PostgreSQL   │  │    Qdrant    │  │    Redis     │               │
│  │  + pgvector   │  │  Vector DB   │  │   Cache/QS   │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent State Machine (LangGraph)

The core orchestration is a **LangGraph state machine** with the following node topology:

### 2.1 State Graph

```mermaid
stateDiagram-v2
    [*] --> Supervisor
    Supervisor --> MarketAgent: analyze_market
    Supervisor --> NewsAgent: gather_news
    Supervisor --> KnowledgeAgent: retrieve_knowledge
    Supervisor --> MemoryAgent: load_context
    MarketAgent --> ReasoningEngine: market_data
    NewsAgent --> ReasoningEngine: news_signals
    KnowledgeAgent --> ReasoningEngine: learned_patterns
    MemoryAgent --> ReasoningEngine: historical_context
    ReasoningEngine --> EvaluationEngine: reasoned_analysis
    EvaluationEngine --> RiskEngine: scored_proposals
    RiskEngine --> DecisionEngine: risk_assessed
    DecisionEngine --> ExecutionEngine: approved_decision
    DecisionEngine --> Supervisor: insufficient_confidence
    ExecutionEngine --> ReflectionEngine: trade_result
    ReflectionEngine --> LearningEngine: lessons
    LearningEngine --> [*]: consolidated
    RiskEngine --> Supervisor: risk_override
```

### 2.2 State Schema

```python
class AgentState(TypedDict):
    """Shared state passed between all agents in the graph."""
    # Input
    symbols: List[str]
    analysis_type: str  # "technical", "news", "combined"
    user_preferences: Optional[Dict]

    # Agent outputs
    market_analysis: Optional[MarketAnalysis]
    news_signals: Optional[NewsSignals]
    knowledge_insights: Optional[KnowledgeInsights]
    memory_context: Optional[MemoryContext]

    # Reasoning & Evaluation
    reasoned_analysis: Optional[ReasonedAnalysis]
    evaluation_scores: Optional[EvaluationScores]

    # Risk & Decision
    risk_assessment: Optional[RiskAssessment]
    decision: Optional[TradingDecision]

    # Execution
    execution_result: Optional[ExecutionResult]

    # Reflection
    reflection: Optional[Reflection]
    lessons: Optional[List[Lesson]]

    # Metadata
    errors: List[str]
    warnings: List[str]
    metrics: Dict[str, Any]
    timestamp: datetime
```

---

## 3. Component Architecture

### 3.1 Agent Layer

| Agent | Responsibility | LLM Model | Input | Output |
|-------|---------------|-----------|-------|--------|
| **Supervisor** | Orchestrates workflow, routes between agents | GPT-4o | User request, system state | Workflow plan, routing decisions |
| **Market Agent** | Technical analysis, pattern recognition | GPT-4o | Price data, indicators | MarketAnalysis (trends, patterns, support/resistance) |
| **News Agent** | News aggregation, sentiment analysis | GPT-4o-mini | News articles, RSS feeds | NewsSignals (sentiment scores, key events) |
| **Knowledge Agent** | Retrieves insights from books & history | GPT-4o-mini | Vector DB queries | KnowledgeInsights (relevant lessons, patterns) |
| **Memory Agent** | Manages short/long-term context | GPT-4o-mini | Session state, history | MemoryContext (relevant memories) |

### 3.2 Engine Layer

| Engine | Responsibility | LLM Model | Input | Output |
|--------|---------------|-----------|-------|--------|
| **Reasoning** | Synthesizes all agent outputs into coherent analysis | GPT-4o | All agent outputs | ReasonedAnalysis (chain-of-thought) |
| **Evaluation** | Scores and ranks trading proposals | GPT-4o | ReasonedAnalysis | EvaluationScores (multi-dimension scoring) |
| **Risk** | Assesses risk parameters, enforces limits | GPT-4o-mini | EvaluationScores, Risk config | RiskAssessment (approved/rejected, sizing) |
| **Decision** | Makes final trading decision | GPT-4o | RiskAssessment | TradingDecision (buy/sell/hold, size, price) |
| **Reflection** | Analyzes trade outcomes, extracts lessons | GPT-4o | ExecutionResult | Reflection (what worked, what didn't) |
| **Learning** | Consolidates patterns, updates knowledge base | GPT-4o | Reflections | Lessons (stored patterns, strategy updates) |

### 3.3 Data Layer

| Store | Technology | Purpose |
|-------|-----------|---------|
| **Relational DB** | PostgreSQL + pgvector | Trades, accounts, users, configs, vector embeddings |
| **Vector DB** | Qdrant | Book knowledge, historical trades, reflections, patterns |
| **Cache** | Redis | Live prices, session state, rate limiting, pub/sub |
| **File Store** | Local filesystem | Logs, exports, backups |

---

## 4. Data Flow

### 4.1 Trading Cycle (End-to-End)

```
1. TRIGGER: Time-based (every 15 min) or event-based (news spike)
     │
2. SUPERVISOR: Determines which agents to invoke
     │
3. PARALLEL AGENTS:
     ├── Market Agent → Fetch prices → Compute indicators → Identify patterns
     ├── News Agent → Fetch articles → Analyze sentiment → Extract events
     ├── Knowledge Agent → Query vector DB → Retrieve relevant lessons
     └── Memory Agent → Load session context → Recall recent trades
     │
4. REASONING ENGINE: Synthesize all inputs → Chain-of-thought analysis
     │
5. EVALUATION ENGINE: Score proposals across 5 dimensions
     │
6. RISK ENGINE: Check limits → Apply position sizing → Approve/reject
     │
7. DECISION ENGINE: Make final call → Generate order
     │
8. EXECUTION: Route to broker (or simulation engine)
     │
9. REFLECTION ENGINE: Analyze outcome → Extract lessons
     │
10. LEARNING ENGINE: Store patterns → Update knowledge base
```

### 4.2 Scoring Dimensions (Evaluation Engine)

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Risk/Reward | 25% | Risk-reward ratio, probability of success |
| Technical Alignment | 20% | How well the setup matches technical indicators |
| Fundamental Alignment | 15% | Alignment with broader market conditions |
| News Sentiment | 15% | News and sentiment analysis support |
| Market Condition | 25% | Overall market regime suitability |

---

## 5. Database Schema (PostgreSQL)

### 5.1 Core Tables

```sql
-- Users & Accounts
users (id, username, email, created_at, preferences JSONB)
accounts (id, user_id, balance, equity, currency, created_at)

-- Trades
trades (id, account_id, symbol, side, quantity, price, status,
        entry_time, exit_time, pnl, pnl_percent, strategy,
        confidence_score, risk_score, metadata JSONB)

-- Decisions
decisions (id, trade_id, decision_type, agent_outputs JSONB,
           reasoning TEXT, evaluation_scores JSONB,
           risk_assessment JSONB, created_at)

-- Reflections
reflections (id, trade_id, lessons TEXT[], patterns JSONB,
             sentiment, created_at)

-- Performance Metrics
performance (id, account_id, date, total_pnl, win_rate,
             sharpe_ratio, max_drawdown, trades_count, metadata JSONB)
```

### 5.2 Vector Collections (Qdrant)

| Collection | Vector Dimension | Content | Use Case |
|-----------|-----------------|---------|----------|
| `book_knowledge` | 1536 | Trading book excerpts | Semantic retrieval of principles |
| `historical_trades` | 1536 | Past trade patterns | Similar trade lookup |
| `reflections` | 1536 | Post-trade lessons | Pattern recognition |
| `market_patterns` | 1536 | Identified patterns | Pattern matching |

---

## 6. API Endpoints

### 6.1 REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze` | Trigger full analysis cycle |
| POST | `/api/v1/trade` | Execute a trade decision |
| GET | `/api/v1/trades` | List trades with filters |
| GET | `/api/v1/trades/{id}` | Trade details |
| GET | `/api/v1/portfolio` | Portfolio summary |
| GET | `/api/v1/performance` | Performance metrics |
| GET | `/api/v1/agents/status` | Agent health & status |
| POST | `/api/v1/agents/configure` | Update agent config |
| GET | `/api/v1/market/data` | Current market data |
| GET | `/api/v1/reflections` | Recent reflections |
| GET | `/api/v1/metrics` | System metrics (Prometheus) |

### 6.2 WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `trade.update` | Server → Client | Real-time trade updates |
| `agent.status` | Server → Client | Agent state changes |
| `market.price` | Server → Client | Live price updates |
| `system.alert` | Server → Client | Alerts & warnings |
| `command.execute` | Client → Server | User commands |

---

## 7. Configuration Management

Configuration is managed via YAML files in `configs/`:

```
configs/
├── market.yaml     # Market data sources, symbols, timeframes
├── risk.yaml       # Risk parameters, position sizing, limits
├── agent.yaml      # Agent behavior, LLM settings, prompts
└── trading.yaml    # Trading modes, execution, strategies
```

Environment-specific overrides via `.env` file:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/amats
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
```

---

## 8. Observability

### 8.1 Metrics (Prometheus)

| Metric | Type | Description |
|--------|------|-------------|
| `trades_total` | Counter | Total trades executed |
| `trade_win_rate` | Gauge | Rolling win rate |
| `portfolio_value` | Gauge | Current portfolio value |
| `agent_latency_seconds` | Histogram | Agent execution time |
| `llm_calls_total` | Counter | LLM API call count |
| `llm_tokens_total` | Counter | Token usage |
| `errors_total` | Counter | Error count by type |

### 8.2 Logging (Loguru)

- **DEBUG**: Detailed agent reasoning, LLM prompts/responses
- **INFO**: Trade executions, agent state transitions
- **WARNING**: Risk limit approaches, unusual patterns
- **ERROR**: Failed operations, API errors
- **CRITICAL**: System halts, data corruption

### 8.3 Tracing

- OpenTelemetry-compatible spans for each agent execution
- Trace IDs correlate across the full trading cycle
- Exportable to Jaeger/Zipkin for visualization

---

## 9. Deployment Architecture

### 9.1 Docker Services

```yaml
services:
  api:          # FastAPI backend
  frontend:     # Next.js dashboard
  postgres:     # Database with pgvector
  qdrant:       # Vector database
  redis:        # Cache & message broker
  prometheus:   # Metrics collection
  grafana:      # Metrics visualization
```

### 9.2 Directory Structure

```
d:\Trade\
├── app/                    # Python backend
│   ├── agents/            # Agent implementations
│   ├── engines/           # Engine implementations
│   ├── models/            # Pydantic schemas
│   ├── db/                # Database models & migrations
│   ├── api/               # FastAPI routes
│   ├── services/          # Business logic services
│   ├── prompts/           # Versioned prompt templates
│   ├── observability/     # Logging, metrics, tracing
│   └── config/            # Config loader
├── frontend/               # Next.js dashboard
├── configs/                # YAML configuration files
├── docs/                   # Documentation
├── tests/                  # Test suite
├── docker/                 # Dockerfiles
├── scripts/                # Utility scripts
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## 10. Success Metrics (MVP)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Win Rate | > 55% | (Winning trades / Total trades) × 100 |
| Sharpe Ratio | > 1.0 | (Portfolio return - Risk-free rate) / Std deviation |
| Max Drawdown | < 15% | Peak-to-trough decline |
| Avg Return per Trade | > 0.5% | Mean PnL % per trade |
| Decision Latency | < 30s | Time from trigger to decision |
| System Uptime | > 99.5% | (Uptime / Total time) × 100 |
| Reflection Coverage | 100% | Every trade has a reflection |
| False Positive Rate | < 30% | Rejected trades that would have been profitable |

---

## 11. Rate Limiting & Constraints

- **Assistant (Copilot)**: Max 35 tool calls per minute
- **LLM API**: Max 500 requests per minute, 100K tokens per minute
- **Market Data**: Max 5 API calls per minute per source (free tier)
- **Trading Frequency**: Max 20 trades per day (compliance)
- **Concurrent Analysis**: Max 5 symbols per analysis cycle

---

## 12. Security Considerations

- API keys stored in environment variables, never in code
- JWT-based authentication for API endpoints
- Rate limiting on all external API calls
- Input validation via Pydantic schemas
- SQL injection prevention via SQLAlchemy ORM
- No live trading without explicit user confirmation
- All decisions logged for audit trail