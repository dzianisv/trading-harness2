#!/usr/bin/env python3
"""Integrity tests. Plain asserts, no pytest needed: python3 tests/run_tests.py
1. No lookahead: mutating future bars never changes past weights.
2. Costs always hurt: same path with costs ends below the same path without.
3. Risk guardrails clip weights to the configured caps.
4. Paper fills: a 50% target from all cash invests ~50% minus slippage.
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness.backtest import run_backtest  # noqa: E402
from harness.risk import apply_guardrails  # noqa: E402
from harness.strategies import STRATEGIES  # noqa: E402


def synthetic(n=600, seed=7):
    rnd = random.Random(seed)
    dates = [f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}#{i}" for i in range(n)]
    closes = {}
    for sym in ("SPY", "QQQ"):
        px, series = 100.0, []
        for _ in range(n):
            px *= math.exp(rnd.gauss(0.0004, 0.01))
            series.append(px)
        closes[sym] = series
    return dates, closes


def test_no_lookahead():
    dates, closes = synthetic()
    for name, params in [("sma_trend", {"fast": 20, "slow": 100}),
                         ("donchian_breakout", {"entry": 20, "exit": 10}),
                         ("rsi_meanrev", {"period": 14, "entry": 30, "exit": 70})]:
        base = STRATEGIES[name](dates, closes, params)
        cut = 400
        mutated = {s: c[:cut] + [x * 3.0 for x in c[cut:]] for s, c in closes.items()}
        after = STRATEGIES[name](dates, mutated, params)
        for i in range(cut):
            assert base[i] == after[i], f"{name}: weight at {i} changed when the future changed"
    print("ok - no lookahead in any strategy")


def test_costs_hurt():
    dates, closes = synthetic()
    weights = STRATEGIES["sma_trend"](dates, closes, {"fast": 20, "slow": 100})
    free, _ = run_backtest(dates, closes, weights, cost_bps=0.0)
    costly, _ = run_backtest(dates, closes, weights, cost_bps=50.0)
    assert costly[-1] < free[-1], "costs must reduce final equity"
    print("ok - costs reduce returns")


def test_guardrails():
    out = apply_guardrails({"SPY": 0.9, "QQQ": 0.9},
                           {"max_weight_per_symbol": 0.7, "max_gross": 1.0})
    assert all(w <= 0.7 + 1e-9 for w in out.values()), out
    assert sum(out.values()) <= 1.0 + 1e-9, out
    print("ok - guardrails clip per-symbol weight and gross")


def test_paper_fill_math():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import harness.paper as paper
    cfg = {"start_capital": 100.0, "slippage_bps": 5.0}
    state = {"cash": 100.0, "positions": {}, "equity_history": [], "peak_equity": 100.0,
             "halted": False, "halt_reason": "", "inception": "2026-01-01", "last_run": None}
    prices = {"SPY": 100.0, "QQQ": 100.0}
    fills = paper.rebalance(state, {"SPY": 0.5, "QQQ": 0.0}, prices, cfg)
    assert len(fills) == 1 and fills[0]["side"] == "buy"
    value = state["positions"]["SPY"] * prices["SPY"]
    assert 49.0 < value < 50.0, value  # ~50 invested, a hair under after slippage on entry price
    assert abs(state["cash"] - 50.0) < 0.5, state["cash"]
    print("ok - paper fill math (fractional, slippage applied)")


if __name__ == "__main__":
    test_no_lookahead()
    test_costs_hurt()
    test_guardrails()
    test_paper_fill_math()
    print("ALL TESTS PASSED")
