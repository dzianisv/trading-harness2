"""Paper account: simulated cash + fractional positions, fills at the latest
close adjusted by slippage. State persists in state/paper_account.json.
There is deliberately NO broker code anywhere in this project.
"""
import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = os.path.join(ROOT, "state", "paper_account.json")


def load_state(cfg):
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "cash": float(cfg["start_capital"]),
        "positions": {},  # symbol -> shares (fractional)
        "inception": date.today().isoformat(),
        "equity_history": [],
        "peak_equity": float(cfg["start_capital"]),
        "halted": False,
        "halt_reason": "",
        "last_run": None,
    }


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def equity_of(state, prices):
    return state["cash"] + sum(sh * prices[s] for s, sh in state["positions"].items() if sh > 0)


def current_weights(state, prices):
    eq = equity_of(state, prices)
    if eq <= 0:
        return {s: 0.0 for s in prices}
    return {s: state["positions"].get(s, 0.0) * prices[s] / eq for s in prices}


def rebalance(state, target_weights, prices, cfg):
    """Move positions to target weights. Returns list of fill dicts.
    Buys fill at close*(1+slippage), sells at close*(1-slippage)."""
    slip = float(cfg["slippage_bps"]) / 10000.0
    eq = equity_of(state, prices)
    fills = []
    for s in sorted(prices):
        target_value = target_weights.get(s, 0.0) * eq
        cur_shares = state["positions"].get(s, 0.0)
        cur_value = cur_shares * prices[s]
        delta_value = target_value - cur_value
        if abs(delta_value) < 0.01:
            continue
        if delta_value > 0:
            fill_px = prices[s] * (1.0 + slip)
            shares = delta_value / fill_px
            cost = shares * fill_px
            if cost > state["cash"]:
                shares = state["cash"] / fill_px
                cost = shares * fill_px
            state["cash"] -= cost
            state["positions"][s] = cur_shares + shares
            fills.append({"symbol": s, "side": "buy", "shares": round(shares, 6),
                          "price": round(fill_px, 4), "value": round(cost, 2)})
        else:
            fill_px = prices[s] * (1.0 - slip)
            shares = min(cur_shares, abs(delta_value) / fill_px)
            proceeds = shares * fill_px
            state["cash"] += proceeds
            state["positions"][s] = cur_shares - shares
            fills.append({"symbol": s, "side": "sell", "shares": round(shares, 6),
                          "price": round(fill_px, 4), "value": round(proceeds, 2)})
    state["positions"] = {s: sh for s, sh in state["positions"].items() if sh > 1e-9}
    if abs(state["cash"]) < 0.005:
        state["cash"] = 0.0  # avoid -0.0 dust in reports
    return fills
