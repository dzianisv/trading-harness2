"""Risk guardrails. These live OUTSIDE the strategies and the improvement
loop: nothing in this project can override them. All checks are pure code.
"""


def apply_guardrails(target_weights, risk_cfg):
    """Clip per-symbol weights and scale gross exposure down to the caps."""
    max_w = float(risk_cfg["max_weight_per_symbol"])
    max_gross = float(risk_cfg["max_gross"])
    clipped = {s: max(0.0, min(float(w), max_w)) for s, w in target_weights.items()}
    gross = sum(clipped.values())
    if gross > max_gross and gross > 0:
        scale = max_gross / gross
        clipped = {s: w * scale for s, w in clipped.items()}
    return clipped


def halt_status(state, equity_today, risk_cfg):
    """Return (halted, reason). Daily-loss halt: equity fell more than
    daily_loss_halt_pct vs the previous recorded day. Kill switch: drawdown
    from peak beyond max_drawdown_kill_pct -> flatten + halt."""
    if state.get("halted"):
        return True, state.get("halt_reason", "halted previously")
    hist = state.get("equity_history", [])
    if hist:
        prev = hist[-1]["equity"]
        if prev > 0 and equity_today / prev - 1.0 < -float(risk_cfg["daily_loss_halt_pct"]) / 100.0:
            return True, f"daily loss halt: {equity_today / prev - 1.0:+.2%} in one day"
    peak = max(state.get("peak_equity", equity_today), equity_today)
    if peak > 0 and equity_today / peak - 1.0 < -float(risk_cfg["max_drawdown_kill_pct"]) / 100.0:
        return True, f"kill switch: drawdown {equity_today / peak - 1.0:+.2%} from peak"
    return False, ""
