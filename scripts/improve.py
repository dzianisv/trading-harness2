#!/usr/bin/env python3
"""One Harness2 improvement cycle (Probe + Compose).

Evaluates a bounded grid of candidates on out-of-sample folds, applies the
kill gates from LEARNINGS.md, and adopts a candidate ONLY if it beats the
incumbent and the benchmark on OOS folds, has enough trades, and clears the
deflated-Sharpe gate (which counts every trial ever run). Every trial —
adopted or killed — is recorded in state/trials.json (the graveyard), so the
bar rises monotonically. Prints a JSON summary; Reflect is the agent's job.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness import data  # noqa: E402
from harness.backtest import evaluate  # noqa: E402
from harness.strategies import PARAM_GRIDS  # noqa: E402

TRIALS_PATH = os.path.join(ROOT, "state", "trials.json")
REPORT_PATH = os.path.join(ROOT, "state", "cycle_report.json")


def load_trials():
    if os.path.exists(TRIALS_PATH):
        with open(TRIALS_PATH) as f:
            return json.load(f)
    return []


def kill_reasons(cand, incumbent_eval, cfg):
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


def main():
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    trials = load_trials()
    dates, closes = data.load_universe(cfg["universe"], years=cfg["evaluation"]["history_years"])

    inc = cfg["incumbent"]
    inc_eval = evaluate(inc["strategy"], inc["params"], dates, closes, cfg, len(trials) + 1)

    candidates = []
    for name, grid in PARAM_GRIDS.items():
        for params in grid:
            if name == inc["strategy"] and params == inc["params"]:
                continue
            candidates.append((name, params))
    candidates = candidates[: int(cfg["evaluation"]["max_trials_per_cycle"])]

    results, adopted = [], None
    for name, params in candidates:
        n_trials = len(trials) + len(results) + 1
        ev_result = evaluate(name, params, dates, closes, cfg, n_trials)
        reasons = kill_reasons(ev_result, inc_eval, cfg)
        verdict = "killed" if reasons else "gate_passed"
        record = {"date": date.today().isoformat(), "strategy": name, "params": params,
                  "verdict": verdict, "kill_reasons": reasons,
                  "median_fold_sharpe": ev_result["median_fold_sharpe"],
                  "fold_sharpes": ev_result["fold_sharpes"],
                  "folds_beating_benchmark": ev_result["folds_beating_benchmark"],
                  "trades_in_folds": ev_result["trades_in_folds"],
                  "deflated_sharpe_prob": round(ev_result["deflated_sharpe_prob"], 3),
                  "full_sharpe": round(ev_result["full"]["sharpe"], 3),
                  "full_cagr_pct": round(ev_result["full"]["cagr"] * 100, 2),
                  "benchmark_cagr_pct": round(ev_result["benchmark_full"]["cagr"] * 100, 2)}
        results.append((record, ev_result))
        trials.append(record)

    passing = [(r, e) for r, e in results if r["verdict"] == "gate_passed"]
    if passing:
        passing.sort(key=lambda x: x[1]["median_fold_sharpe"], reverse=True)
        best_record, _ = passing[0]
        adopted = {"strategy": best_record["strategy"], "params": best_record["params"]}
        for r, _e in results:
            if r is best_record:
                r["verdict"] = "adopted"
        cfg["incumbent"] = adopted
        with open(os.path.join(ROOT, "config.json"), "w") as f:
            json.dump(cfg, f, indent=2, sort_keys=True)

    os.makedirs(os.path.dirname(TRIALS_PATH), exist_ok=True)
    with open(TRIALS_PATH, "w") as f:
        json.dump(trials, f, indent=2)
    report = {
        "date": date.today().isoformat(),
        "incumbent_before": inc,
        "incumbent_eval": {"median_fold_sharpe": inc_eval["median_fold_sharpe"],
                           "fold_sharpes": inc_eval["fold_sharpes"],
                           "deflated_sharpe_prob": round(inc_eval["deflated_sharpe_prob"], 3),
                           "full_sharpe": round(inc_eval["full"]["sharpe"], 3),
                           "full_cagr_pct": round(inc_eval["full"]["cagr"] * 100, 2),
                           "benchmark_cagr_pct": round(inc_eval["benchmark_full"]["cagr"] * 100, 2),
                           "benchmark_sharpe": round(inc_eval["benchmark_full"]["sharpe"], 3)},
        "trials_this_cycle": len(results),
        "trials_total": len(trials),
        "adopted": adopted,
        "killed": [r for r, _e in results if r["verdict"] == "killed"],
        "gate_passed_not_adopted": [r for r, _e in results if r["verdict"] == "gate_passed"],
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({"trials_this_cycle": len(results), "trials_total": len(trials),
                      "adopted": adopted,
                      "incumbent_median_fold_sharpe": inc_eval["median_fold_sharpe"],
                      "benchmark_cagr_pct": report["incumbent_eval"]["benchmark_cagr_pct"],
                      "incumbent_cagr_pct": report["incumbent_eval"]["full_cagr_pct"]}, indent=2))


if __name__ == "__main__":
    main()
