"""Lightweight per-run tracing: node durations, token usage, and cost.

Real LLM token counts will be reported by each agent once live models are
wired in. The skeleton records durations and zero-cost entries so the
dashboard has a shape to render from day one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class NodeTrace:
    node: str
    duration_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    note: str = ""


@dataclass
class RunTrace:
    run_id: str
    nodes: list[NodeTrace] = field(default_factory=list)

    def record(self, trace: NodeTrace) -> None:
        self.nodes.append(trace)

    @property
    def total_ms(self) -> float:
        return sum(n.duration_ms for n in self.nodes)

    @property
    def total_tokens(self) -> int:
        return sum(n.prompt_tokens + n.completion_tokens for n in self.nodes)

    @property
    def total_cost_usd(self) -> float:
        return sum(n.cost_usd for n in self.nodes)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_ms": round(self.total_ms, 2),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "nodes": [
                {
                    "node": n.node,
                    "duration_ms": round(n.duration_ms, 2),
                    "prompt_tokens": n.prompt_tokens,
                    "completion_tokens": n.completion_tokens,
                    "cost_usd": round(n.cost_usd, 6),
                    "note": n.note,
                }
                for n in self.nodes
            ],
        }


class timed:
    """Context manager returning elapsed milliseconds via `.ms`."""

    def __enter__(self) -> "timed":
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000.0
