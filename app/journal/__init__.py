"""The system's persistent journal — its memory of what it did and how it went.

The paper broker records fills; this records DECISIONS (including holds and the
reasoning behind them) and a time-series of equity. That is what turns A-MATS
from a thing you poke by hand into a system that accumulates a track record —
the honest evidence you need before trusting any change, or any real money.

SQLite on purpose: a real database with zero infrastructure, so the journal
works today on a laptop and can migrate to Postgres later without changing the
call sites.
"""
