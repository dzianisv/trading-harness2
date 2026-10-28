#!/usr/bin/env python3
"""Daily digest (markdown): paper equity vs buy&hold SPY from the same start,
current position, incumbent strategy, and the latest improvement verdicts."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness import data, paper  # noqa: E402


def main():
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    state = paper.load_state(cfg)
    dates, closes = data.load_universe(cfg["universe"] + [cfg["benchmark"]])
    prices = {s: closes[s][-1] for s in closes}
    eq = paper.equity_of(state, prices)
    start = float(cfg["start_capital"])

    bench_ret = None
    hist = state.get("equity_history", [])
    if hist:
        inception_date = hist[0]["date"]
        if inception_date in dates:
            i0 = dates.index(inception_date)
            bench_ret = closes[cfg["benchmark"]][-1] / closes[cfg["benchmark"]][i0] - 1.0

    lines = [f"**Trading Harness² — daily digest ({dates[-1]})**", ""]
    lines.append(f"- Paper equity: **${eq:.2f}** ({(eq / start - 1.0) * 100:+.2f}% since inception "
                 f"{state.get('inception')})")
    if bench_ret is not None:
        lines.append(f"- Buy&hold {cfg['benchmark']} over the same window: {bench_ret * 100:+.2f}%")
    pos = {s: round(sh * prices[s], 2) for s, sh in state["positions"].items() if sh > 0}
    lines.append(f"- Positions: {pos if pos else 'all cash'} · cash ${state['cash']:.2f}")
    inc = cfg["incumbent"]
    lines.append(f"- Incumbent strategy: `{inc['strategy']}` {inc['params']}")
    if state.get("halted"):
        lines.append(f"- ⚠️ HALTED: {state.get('halt_reason')}")
    rp = os.path.join(ROOT, "state", "cycle_report.json")
    if os.path.exists(rp):
        with open(rp) as f:
            rep = json.load(f)
        ie = rep["incumbent_eval"]
        lines.append(f"- Improvement cycle {rep['date']}: {rep['trials_this_cycle']} trials "
                     f"({rep['trials_total']} total), adopted: {rep['adopted'] or 'none'}")
        lines.append(f"- Incumbent backtest (8y, after costs): CAGR {ie['full_cagr_pct']}% vs "
                     f"buy&hold {ie['benchmark_cagr_pct']}%; Sharpe {ie['full_sharpe']} vs "
                     f"{ie['benchmark_sharpe']}; deflated-Sharpe prob {ie['deflated_sharpe_prob']}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
