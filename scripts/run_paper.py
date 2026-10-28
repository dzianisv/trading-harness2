#!/usr/bin/env python3
"""One paper-trading cycle: fetch latest data, apply the incumbent strategy,
risk-check, simulate fills, persist state. Prints a JSON summary."""
import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness import data, paper, risk  # noqa: E402
from harness.strategies import STRATEGIES  # noqa: E402


def main():
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    state = paper.load_state(cfg)

    dates, closes = data.load_universe(cfg["universe"])
    prices = {s: closes[s][-1] for s in cfg["universe"]}
    last_date = dates[-1]

    if state.get("last_bar_date") == last_date and state.get("equity_history"):
        print(json.dumps({"status": "no_new_bar", "bar_date": last_date}))
        return

    eq_before = paper.equity_of(state, prices)
    halted, reason = risk.halt_status(state, eq_before, cfg["risk"])

    fills = []
    action = "hold"
    if halted:
        if state["positions"]:
            fills = paper.rebalance(state, {s: 0.0 for s in prices}, prices, cfg)
            action = "flattened_by_kill_switch"
        state["halted"] = True
        state["halt_reason"] = reason
    else:
        inc = cfg["incumbent"]
        weights = STRATEGIES[inc["strategy"]](dates, closes, inc["params"])
        target = risk.apply_guardrails(weights[-1], cfg["risk"])
        current = paper.current_weights(state, prices)
        drift = max(abs(target.get(s, 0.0) - current.get(s, 0.0)) for s in prices)
        if drift > float(cfg["rebalance_threshold"]):
            fills = paper.rebalance(state, target, prices, cfg)
            action = "rebalanced"

    eq_after = paper.equity_of(state, prices)
    state["peak_equity"] = max(state.get("peak_equity", eq_after), eq_after)
    state["last_bar_date"] = last_date
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    if not state["equity_history"] or state["equity_history"][-1]["date"] != last_date:
        state["equity_history"].append({"date": last_date, "equity": round(eq_after, 2)})
    paper.save_state(state)

    if fills:
        log_path = os.path.join(ROOT, "logs", "trades.csv")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        new_file = not os.path.exists(log_path)
        with open(log_path, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["bar_date", "symbol", "side", "shares", "price", "value"])
            for fill in fills:
                w.writerow([last_date, fill["symbol"], fill["side"], fill["shares"], fill["price"], fill["value"]])

    print(json.dumps({
        "status": "ok", "bar_date": last_date, "action": action,
        "equity": round(eq_after, 2),
        "return_since_inception_pct": round((eq_after / cfg["start_capital"] - 1.0) * 100, 2),
        "positions": state["positions"], "cash": round(state["cash"], 2),
        "fills": fills, "halted": state["halted"], "halt_reason": state.get("halt_reason", ""),
        "incumbent": cfg["incumbent"],
    }, indent=2))


if __name__ == "__main__":
    main()
