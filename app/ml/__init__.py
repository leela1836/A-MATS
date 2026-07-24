"""Learned trade validation.

A small supervised model that scores each candidate entry the rule strategy
would take, so weak setups can be filtered before they cost money. It LEARNS
from the same agent signals the reasoning layer sees (technical structure,
candlestick context, volume/liquidity) and is trained on BACKTEST trade
outcomes — hundreds of labelled examples that exist immediately, unlike the
paper book which has none.

It does not invent a direction. Like the candlestick gate, it only vetoes.
A filter cannot rescue a losing edge; it can only stop bleeding the weakest
slice of it. Every claim here is validated OUT OF SAMPLE (see train.py) — a
model that looks brilliant in-sample and useless after a temporal split is the
default outcome on a few-hundred-row financial dataset, not the exception.
"""
