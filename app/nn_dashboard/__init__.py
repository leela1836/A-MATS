"""Standalone Neural-Network Health Dashboard.

A read-only viewer over the trained trade-validator MLP (`app/ml/`). Runs as
its own FastAPI app on port 8100, entirely separate from the main A-MATS
service on 8000/3000 — no shared routes, no shared process, no LLM calls.

Run: ./.venv/Scripts/python.exe -m uvicorn app.nn_dashboard.server:app --port 8100
"""
