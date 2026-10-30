#!/usr/bin/env python3
"""Probe ONE candidate through the exact gates of the improvement loop.

This is the standalone harness's Probe primitive: the harness agent proposes
an edit (often a brand-new strategy family in strategies.py), then calls

    python3 scripts/probe.py --strategy NAME --params '{"k": v}' \
        --rationale "evidence-based reason" [--channel harness]

probe.py evaluates the candidate on the OOS folds, applies
backtest.gate_failures (the same function improve.py uses), records the
trial in state/trials.json, and — only if every gate passes — adopts the
candidate as the incumbent in config.json. The agent cannot adopt anything
by itself; adoption happens here, in code, or not at all.
"""
import argparse
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness import data  # noqa: E402
from harness.backtest import evaluate, gate_failures  # noqa: E402
from harness.strategies import STRATEGIES  # noqa: E402

TRIALS_PATH = os.path.join(ROOT, "state", "trials.json")
CONFIG_PATH = os.path.join(ROOT, "config.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--params", required=True, help="JSON object of strategy params")
    ap.add_argument("--rationale", required=True)
    ap.add_argument("--channel", default="harness")
    args = ap.parse_args()

    if args.strategy not in STRATEGIES or args.strategy == "buy_hold":
        print(json.dumps({"error": f"unknown strategy: {args.strategy}"}))
        return 2
    params = json.loads(args.params)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    trials = []
    if os.path.exists(TRIALS_PATH):
        with open(TRIALS_PATH) as f:
            trials = json.load(f)

    dates, closes = data.load_universe(cfg["universe"], years=cfg["evaluation"]["history_years"])
    inc = cfg["incumbent"]
    inc_eval = evaluate(inc["strategy"], inc["params"], dates, closes, cfg, len(trials) + 1)
    cand = evaluate(args.strategy, params, dates, closes, cfg, len(trials) + 1)
    reasons = gate_failures(cand, inc_eval, cfg)

    adopted = None
    verdict = "killed" if reasons else "adopted"
    if not reasons:
        adopted = {"strategy": args.strategy, "params": params}
        cfg["incumbent"] = adopted
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2, sort_keys=True)

    record = {"date": date.today().isoformat(), "strategy": args.strategy, "params": params,
              "channel": args.channel, "rationale": args.rationale,
              "verdict": verdict, "kill_reasons": reasons,
              "median_fold_sharpe": cand["median_fold_sharpe"],
              "fold_sharpes": cand["fold_sharpes"],
              "folds_beating_benchmark": cand["folds_beating_benchmark"],
              "trades_in_folds": cand["trades_in_folds"],
              "deflated_sharpe_prob": round(cand["deflated_sharpe_prob"], 3),
              "full_sharpe": round(cand["full"]["sharpe"], 3),
              "full_cagr_pct": round(cand["full"]["cagr"] * 100, 2),
              "benchmark_cagr_pct": round(cand["benchmark_full"]["cagr"] * 100, 2)}
    trials.append(record)
    with open(TRIALS_PATH, "w") as f:
        json.dump(trials, f, indent=2)

    print(json.dumps({"verdict": verdict, "kill_reasons": reasons, "adopted": adopted,
                      "median_fold_sharpe": cand["median_fold_sharpe"],
                      "incumbent_median_fold_sharpe": inc_eval["median_fold_sharpe"],
                      "folds_beating_benchmark": cand["folds_beating_benchmark"],
                      "trades_in_folds": cand["trades_in_folds"],
                      "deflated_sharpe_prob": round(cand["deflated_sharpe_prob"], 3),
                      "trials_total": len(trials)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
