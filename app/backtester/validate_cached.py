"""Reproducible, network-free portfolio validation on the local cached universe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from app.backtester.strategy_lab import backtest
from app.collectors.market_collector import _cache_path, normalise_cached_history
from app.journal.screener import load_universe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default="mean_reversion")
    parser.add_argument("--period", default="3y")
    parser.add_argument("--output", default="data/validation-corrected.json")
    args = parser.parse_args()
    frames, missing = {}, []
    for symbol in load_universe():
        path = _cache_path(symbol, args.period, "1d")
        if path.exists():
            df = pd.read_pickle(path)  # project-owned cache only
            frames[symbol] = normalise_cached_history(df)
        else:
            missing.append(symbol)
    print(json.dumps({"loaded": len(frames), "missing": missing,
                      "strategy": args.strategy, "source": "local cache, no downloads"}), flush=True)
    report = backtest(frames=frames, period=args.period, strategies=[args.strategy])
    report["missing_symbols"] = missing
    report["provenance"] = "Previously researched historical cache; NOT an untouched forward test"
    report["timestamp_repair"] = "Legacy naive 18:30 UTC candles restored to Asia/Kolkata before date extraction"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for name, result in report["strategies"].items():
        print(json.dumps({"strategy": name, "return_pct": result["portfolio_return_pct"],
                          "closed_trades": result["trades"], "avg_net_trade_pct": result["avg"],
                          "halt": result["halt"], "months": result["monthly"]}), flush=True)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
