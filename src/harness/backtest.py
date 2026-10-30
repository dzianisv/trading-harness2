"""Backtesting with honest costs, out-of-sample folds and a deflated Sharpe
ratio that accounts for how many variants have ever been tried.

Weight convention: weights[i] is decided at close of day i and earns the
return from day i to day i+1. Turnover is charged at cost_bps on the day the
weight changes. (Weights are treated as non-drifting between rebalances —
a documented simplification; costs are charged on every change, which keeps
the bias conservative where it matters.)
"""
import math
from statistics import NormalDist, fmean, stdev

from .strategies import STRATEGIES

_ND = NormalDist()
_EULER_GAMMA = 0.5772156649015329


def run_backtest(dates, closes, weights, capital=100.0, cost_bps=7.0):
    symbols = sorted(closes)
    equity = capital
    curve = [capital]
    trades = 0
    prev = {s: 0.0 for s in symbols}
    for i in range(len(dates) - 1):
        w = weights[i]
        turnover = sum(abs(w.get(s, 0.0) - prev.get(s, 0.0)) for s in symbols)
        if turnover > 1e-9:
            trades += 1
            equity *= (1.0 - turnover * cost_bps / 10000.0)
        r = sum(w.get(s, 0.0) * (closes[s][i + 1] / closes[s][i] - 1.0) for s in symbols)
        equity *= (1.0 + r)
        curve.append(equity)
        prev = w
    return curve, trades


def metrics(curve):
    if len(curve) < 3:
        return {"total_return": 0.0, "cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "final": curve[-1] if curve else 0.0}
    rets = [curve[i + 1] / curve[i] - 1.0 for i in range(len(curve) - 1)]
    total = curve[-1] / curve[0] - 1.0
    years = len(rets) / 252.0
    cagr = (curve[-1] / curve[0]) ** (1.0 / years) - 1.0 if years > 0 and curve[-1] > 0 else 0.0
    sd = stdev(rets) if len(rets) > 1 else 0.0
    sharpe = (fmean(rets) / sd * math.sqrt(252)) if sd > 0 else 0.0
    peak, max_dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1.0)
    return {"total_return": total, "cagr": cagr, "sharpe": sharpe,
            "max_drawdown": max_dd, "final": curve[-1]}


def gate_failures(cand, incumbent_eval, cfg):
    """The adoption gates (LEARNINGS rules 3-5). Returns a list of kill
    reasons; an empty list means the candidate passed every gate. Shared by
    scripts/improve.py and scripts/probe.py so every channel faces exactly
    the same bar."""
    ev = cfg["evaluation"]
    reasons = []
    if cand["trades_in_folds"] < int(ev["min_trades"]):
        reasons.append(f"only {cand['trades_in_folds']} trades in folds (< {ev['min_trades']})")
    if cand["folds_beating_benchmark"] < int(ev["min_positive_folds"]):
        reasons.append(f"beat benchmark in {cand['folds_beating_benchmark']}/{cand['n_folds']} folds "
                       f"(< {ev['min_positive_folds']})")
    if cand["median_fold_sharpe"] <= incumbent_eval["median_fold_sharpe"]:
        reasons.append(f"median fold Sharpe {cand['median_fold_sharpe']:.2f} <= incumbent "
                       f"{incumbent_eval['median_fold_sharpe']:.2f}")
    if cand["deflated_sharpe_prob"] < float(ev["min_deflated_sharpe_prob"]):
        reasons.append(f"deflated Sharpe prob {cand['deflated_sharpe_prob']:.2f} "
                       f"< {ev['min_deflated_sharpe_prob']}")
    return reasons


def deflated_sharpe_prob(daily_returns, n_trials):
    """Probability the true Sharpe > 0 given the number of trials ever run
    (Bailey & Lopez de Prado, simplified to skew=0 / kurtosis=3)."""
    t = len(daily_returns)
    if t < 30:
        return 0.0
    sd = stdev(daily_returns)
    if sd == 0:
        return 0.0
    sr = fmean(daily_returns) / sd
    if n_trials <= 1:
        sr0 = 0.0
    else:
        z1 = _ND.inv_cdf(1.0 - 1.0 / n_trials)
        z2 = _ND.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
        sr0 = ((1.0 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2) / math.sqrt(t)
    denom = math.sqrt(max(1e-12, 1.0 + 0.5 * sr * sr))
    return _ND.cdf((sr - sr0) * math.sqrt(t - 1) / denom)


def evaluate(name, params, dates, closes, cfg, n_trials):
    """Evaluate one candidate: full-period metrics, OOS fold metrics vs the
    benchmark, trade count, deflated Sharpe. The final `holdout_days` are
    excluded from the selection folds (report-only holdout)."""
    ev = cfg["evaluation"]
    cost_bps = cfg["spread_bps"] + cfg["slippage_bps"]
    weights = STRATEGIES[name](dates, closes, params)
    bench_weights = STRATEGIES["buy_hold"](dates, closes, {})

    n = len(dates)
    holdout = int(ev["holdout_days"])
    fold_days = int(ev["fold_days"])
    n_folds = int(ev["selection_folds"])
    sel_end = n - holdout
    folds = []
    for k in range(n_folds):
        end = sel_end - k * fold_days
        start = end - fold_days
        if start < 250:  # need indicator warmup before the fold
            break
        folds.append((start, end))
    folds.reverse()

    def fold_metrics(w, start, end):
        curve, tr = run_backtest(dates[start:end], {s: c[start:end] for s, c in closes.items()},
                                 w[start:end - 1] + [w[end - 1]], capital=100.0, cost_bps=cost_bps)
        return metrics(curve), tr

    fold_sharpes, fold_beats, total_trades, daily = [], 0, 0, []
    for (start, end) in folds:
        m, tr = fold_metrics(weights, start, end)
        bm, _ = fold_metrics(bench_weights, start, end)
        fold_sharpes.append(m["sharpe"])
        if m["sharpe"] > bm["sharpe"]:
            fold_beats += 1
        total_trades += tr
        seg_dates = dates[start:end]
        seg_closes = {s: c[start:end] for s, c in closes.items()}
        curve, _ = run_backtest(seg_dates, seg_closes, weights[start:end - 1] + [weights[end - 1]],
                                capital=100.0, cost_bps=cost_bps)
        daily.extend(curve[i + 1] / curve[i] - 1.0 for i in range(len(curve) - 1))

    full_curve, full_trades = run_backtest(dates, closes, weights, capital=100.0, cost_bps=cost_bps)
    full = metrics(full_curve)
    bench_curve, _ = run_backtest(dates, closes, bench_weights, capital=100.0, cost_bps=cost_bps)
    bench = metrics(bench_curve)

    fold_sharpes_sorted = sorted(fold_sharpes)
    median_fold = fold_sharpes_sorted[len(fold_sharpes_sorted) // 2] if fold_sharpes_sorted else 0.0
    return {
        "strategy": name, "params": params,
        "full": full, "benchmark_full": bench,
        "fold_sharpes": [round(x, 3) for x in fold_sharpes],
        "median_fold_sharpe": median_fold,
        "folds_beating_benchmark": fold_beats,
        "n_folds": len(folds),
        "trades_in_folds": total_trades,
        "full_trades": full_trades,
        "deflated_sharpe_prob": deflated_sharpe_prob(daily, max(1, n_trials)),
    }
