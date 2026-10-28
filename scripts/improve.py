#!/usr/bin/env python3
"""One Harness2 improvement cycle (Probe + Compose).

Candidates come from three Propose channels, all judged by the same gates:
  grid     — the bounded baseline parameter sweep;
  mutation — Edit A: one-rung parameter steps of the closest past kills;
  agent    — Edit B: candidates the daily agent proposed in
             state/proposals.json, each with a written evidence-based
             rationale (no rationale -> never evaluated).
Adoption requires beating the incumbent and the benchmark on out-of-sample
folds, enough trades, and the deflated-Sharpe gate (which counts every trial
ever run). Every trial — adopted or killed — is recorded in
state/trials.json (the graveyard), so the bar rises monotonically.
Prints a JSON summary; Reflect is the agent's job.
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from harness import data  # noqa: E402
from harness.backtest import evaluate  # noqa: E402
from harness.strategies import PARAM_GRIDS, STRATEGIES  # noqa: E402

TRIALS_PATH = os.path.join(ROOT, "state", "trials.json")
REPORT_PATH = os.path.join(ROOT, "state", "cycle_report.json")
PROPOSALS_PATH = os.path.join(ROOT, "state", "proposals.json")

# Parameter ladders for near-miss mutations (Edit A of the Harness2 protocol):
# a mutation steps ONE parameter of a close kill to an adjacent rung.
LADDERS = {
    "sma_trend": {"fast": [5, 10, 20, 35, 50, 75], "slow": [100, 125, 150, 175, 200, 250]},
    "donchian_breakout": {"entry": [14, 20, 34, 55, 89], "exit": [8, 10, 14, 20, 34]},
    "rsi_meanrev": {"period": [2, 3, 5, 14, 21], "entry": [5, 10, 15, 20, 25, 30, 35, 40],
                    "exit": [60, 70, 80]},
}


def load_trials():
    if os.path.exists(TRIALS_PATH):
        with open(TRIALS_PATH) as f:
            return json.load(f)
    return []


def _key(name, params):
    return name, json.dumps(params, sort_keys=True)


def load_agent_proposals(cap=4):
    """Edit B channel: candidates the daily agent wrote to state/proposals.json
    with a written rationale each. No rationale -> not evaluated (LEARNINGS)."""
    if not os.path.exists(PROPOSALS_PATH):
        return [], False
    try:
        with open(PROPOSALS_PATH) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return [], True
    out = []
    for item in raw if isinstance(raw, list) else []:
        name, params, rationale = item.get("strategy"), item.get("params"), item.get("rationale")
        if name in STRATEGIES and name != "buy_hold" and isinstance(params, dict) \
                and isinstance(rationale, str) and len(rationale.strip()) >= 20:
            out.append({"strategy": name, "params": params, "channel": "agent",
                        "rationale": rationale.strip()})
        if len(out) >= cap:
            break
    return out, True


def generate_mutations(trials, seen, cap=4):
    """Edit A channel: one-rung mutations of the closest kills (highest median
    fold Sharpe first), skipping anything already tried in any past cycle."""
    sources = [t for t in trials if t.get("verdict") in ("killed", "gate_passed")
               and t["strategy"] in LADDERS]
    sources.sort(key=lambda t: t.get("median_fold_sharpe", 0.0), reverse=True)
    out = []
    for src in sources:
        if len(out) >= cap:
            break
        before = len(out)
        name, params = src["strategy"], src["params"]
        for param, ladder in LADDERS[name].items():
            if param not in params or params[param] not in ladder:
                continue
            idx = ladder.index(params[param])
            for step in (1, -1):
                j = idx + step
                if not (0 <= j < len(ladder)):
                    continue
                new_params = dict(params)
                new_params[param] = ladder[j]
                if name == "sma_trend" and new_params["fast"] >= new_params["slow"]:
                    continue
                if name == "rsi_meanrev" and new_params["entry"] >= new_params["exit"]:
                    continue
                if _key(name, new_params) in seen:
                    continue
                seen.add(_key(name, new_params))
                died = src.get("kill_reasons", ["gates"])[0]
                out.append({"strategy": name, "params": new_params, "channel": "mutation",
                            "rationale": f"Near-miss mutation of {name} {params} "
                                         f"(median fold Sharpe {src.get('median_fold_sharpe')}, "
                                         f"died on: {died}); step {param} {params[param]}->{ladder[j]}."})
                break  # one mutation per source per param-step found
            if len(out) > before:
                break  # one mutation per source candidate
    return out


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

    # Three proposal channels, one shared trial budget (LEARNINGS rule 11):
    # agent proposals and near-miss mutations are hypothesis-driven, so they
    # are deduplicated against ALL history; the grid is the baseline sweep and
    # re-runs as folds shift with new data.
    cap_total = int(cfg["evaluation"]["max_trials_per_cycle"])
    history = {_key(t["strategy"], t["params"]) for t in trials}
    history.add(_key(inc["strategy"], inc["params"]))
    agent_props, proposals_file_seen = load_agent_proposals()
    candidates = []
    for c in agent_props:
        k = _key(c["strategy"], c["params"])
        if k not in history:
            history.add(k)
            candidates.append(c)
    candidates += generate_mutations(trials, history, cap=4)
    for name, grid in PARAM_GRIDS.items():
        for params in grid:
            if name == inc["strategy"] and params == inc["params"]:
                continue
            candidates.append({"strategy": name, "params": params, "channel": "grid",
                               "rationale": "Bounded grid sweep (baseline channel)."})
    candidates = candidates[:cap_total]

    results, adopted = [], None
    for cand in candidates:
        name, params = cand["strategy"], cand["params"]
        n_trials = len(trials) + len(results) + 1
        ev_result = evaluate(name, params, dates, closes, cfg, n_trials)
        reasons = kill_reasons(ev_result, inc_eval, cfg)
        verdict = "killed" if reasons else "gate_passed"
        record = {"date": date.today().isoformat(), "strategy": name, "params": params,
                  "channel": cand["channel"], "rationale": cand["rationale"],
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
    if proposals_file_seen and os.path.exists(PROPOSALS_PATH):
        archive = os.path.join(ROOT, "state", f"proposals_used_{date.today().isoformat()}.json")
        os.replace(PROPOSALS_PATH, archive)
    channels = {}
    for r, _e in results:
        channels[r["channel"]] = channels.get(r["channel"], 0) + 1
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
        "channels": channels,
        "adopted": adopted,
        "killed": [r for r, _e in results if r["verdict"] == "killed"],
        "gate_passed_not_adopted": [r for r, _e in results if r["verdict"] == "gate_passed"],
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({"trials_this_cycle": len(results), "trials_total": len(trials),
                      "channels": channels,
                      "adopted": adopted,
                      "incumbent_median_fold_sharpe": inc_eval["median_fold_sharpe"],
                      "benchmark_cagr_pct": report["incumbent_eval"]["benchmark_cagr_pct"],
                      "incumbent_cagr_pct": report["incumbent_eval"]["full_cagr_pct"]}, indent=2))


if __name__ == "__main__":
    main()
