"""FastAPI entry point for A-MATS.

Phase 1 surface: health, config introspection, and a synchronous
run-cycle endpoint that drives the walking-skeleton graph so the Next.js
dashboard has real data to render from day one.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import all_configs, get_config
from app.workflows.runner import run_cycle

app = FastAPI(title="A-MATS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "a-mats", "version": app.version}


@app.get("/config/{name}")
def config(name: str) -> dict:
    try:
        return get_config(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/config")
def configs() -> dict:
    return all_configs()


@app.post("/run/{symbol}")
def run(symbol: str) -> dict:
    """Run one trading cycle through the graph for a single symbol."""
    return run_cycle(symbol.upper(), run_id=f"api-{symbol.lower()}")
