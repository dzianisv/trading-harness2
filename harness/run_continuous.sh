#!/usr/bin/env bash
# CONTINUOUS Harness2 loop for the trading harness: propose -> probe -> compose
# -> reflect, back-to-back cycles, powered by pi + OpenRouter (Den's pattern
# from the RFS loop). The agent edits strategies; code (probe.py) judges;
# this runner commits and enforces the protected-file rails.
# Stops on: harness/state/STOP, MAX_CYCLES, or 3 consecutive failed cycles.
set -u
cd "$(dirname "$0")/.."
# OpenRouter key from the unattended store (same one the RFS loop uses)
if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -f "$HOME/.config/rfs/openrouter.key" ]; then
  export OPENROUTER_API_KEY="$(cat "$HOME/.config/rfs/openrouter.key")"
fi
PI="$HOME/workspace/tools/bin/pi"
MODEL="${HARNESS_MODEL:-nvidia/nemotron-3.5-lightning:free}"
FALLBACK_MODEL="google/gemma-4-31b-it:free"
ATTEMPT_TIMEOUT="${HARNESS_ATTEMPT_TIMEOUT:-1800}"
STATE="harness/state"; mkdir -p "$STATE" harness/runs "$STATE/backup"
[ -f "$STATE/next_cycle.txt" ] || echo 3 > "$STATE/next_cycle.txt"
LOG="harness/runs/continuous.log"
exec >> "$LOG" 2>&1
echo "=== trading harness loop start $(date) model=$MODEL pid=$$ ==="
echo $$ > "$STATE/runner.pid"

PROTECTED="src/harness/backtest.py src/harness/risk.py src/harness/paper.py src/harness/data.py scripts/probe.py scripts/improve.py scripts/run_paper.py scripts/report.py harness/TASK.md harness/run_continuous.sh"

cycle_prompt() { # $1 = cycle number
cat <<EOF
You are the trading-research agent running ONE cycle (cycle $1) of a continuous, self-improving PAPER-trading harness for Den (Dzianis Vashchuk). Work inside this repo only. PAPER ONLY: no broker code, no real accounts, no credentials.

READ FIRST: harness/TASK.md (objective + rails), LEARNINGS.md (binding rules + graveyard), config.json, state/trials.json (the graveyard - never re-propose a tried strategy+params pair), state/cycle_report.json, state/paper_account.json.

CYCLE $1 PROCEDURE:
1. BASELINE: run python3 tests/run_tests.py - all tests must pass; if any fails, write harness/runs/cycle$1.md describing the failure and STOP (final line still required). Then run python3 scripts/run_paper.py.
2. PROPOSE ONE EDIT (the single improvement under test this cycle). Choose exactly one:
   (a) a NEW strategy family: implement it in src/harness/strategies.py (strictly causal: the weight at day i uses only closes[0..i]), register it in STRATEGIES, and add a small PARAM_GRIDS entry; or
   (b) a variant of an existing family motivated by a SPECIFIC graveyard kill - cite the trial (strategy, params, kill reasons) it answers.
   Before editing, back up every file you will touch: cp <file> harness/state/backup/cycle$1-<basename>. Write your rationale (evidence, hypothesis, what result would falsify it) into harness/runs/cycle$1.md.
3. PROBE: run python3 tests/run_tests.py again - a failing test kills your edit. Then run: python3 scripts/probe.py --strategy <name> --params '<json>' --rationale '<one or two sentences citing the graveyard evidence>' --channel harness. probe.py applies the adoption gates and records the trial; if it passes, probe.py adopts your candidate as incumbent itself - you cannot adopt anything by hand.
4. COMPOSE: if probe.py killed your candidate, restore the backups (cp harness/state/backup/cycle$1-<basename> <file>) so the killed edit leaves no trace in code, and remove the backups. If adopted, remove the backups.
5. REFLECT: append the outcome to the LEARNINGS.md graveyard (cycle $1: what was proposed, probe verdict + key numbers - median fold Sharpe, folds beating benchmark, trades, deflated Sharpe prob - and a one-line lesson). Complete harness/runs/cycle$1.md with the full summary.
HARD RAILS: never edit protected files (src/harness/backtest.py, risk.py, paper.py, data.py; scripts/probe.py, improve.py, run_paper.py, report.py; tests/; tools/; harness/TASK.md; harness/run_continuous.sh). Never raise risk caps or lower costs in config.json; never hand-edit the incumbent in config.json (only probe.py does that). Never widen the universe beyond SPY/QQQ. Never run git commands (the runner commits). Every claim needs a number from probe or test output.
Final line of your reply must be exactly: CYCLE $1 COMPLETE - 1 proposed, <n> killed, <n> ADOPTED
EOF
}

MAX="${HARNESS_MAX_CYCLES:-8}"
FAILS=0
PRIMARY_FAILS=0
for i in $(seq 1 "$MAX"); do
  [ -f "$STATE/STOP" ] && { echo "STOP file present, exiting $(date)"; break; }
  N=$(cat "$STATE/next_cycle.txt")
  OUT="harness/runs/cycle$N-pi-output.log"
  echo "--- cycle $N attempt $(date) model=$MODEL ---"
  timeout "$ATTEMPT_TIMEOUT" "$PI" -p --provider openrouter --model "$MODEL" "$(cycle_prompt "$N")" > "$OUT" 2>&1
  RC=$?
  if grep -q "429" "$OUT" || grep -qi "rate limit" "$OUT"; then
    echo "cycle $N: quota/rate-limit hit (rc=$RC) - backing off 30 min, same cycle retries"
    sleep 1800; continue
  fi
  if [ $RC -ne 0 ] || ! grep -q "CYCLE $N COMPLETE" "$OUT"; then
    FAILS=$((FAILS+1)); PRIMARY_FAILS=$((PRIMARY_FAILS+1))
    echo "cycle $N: FAILED rc=$RC complete_line=$(grep -c "CYCLE $N COMPLETE" "$OUT") - consecutive fails=$FAILS"
    git checkout -- . >/dev/null 2>&1 || true
    if [ "$MODEL" != "$FALLBACK_MODEL" ] && [ $PRIMARY_FAILS -ge 2 ]; then
      echo "primary model failed $PRIMARY_FAILS times - switching to fallback $FALLBACK_MODEL"
      MODEL="$FALLBACK_MODEL"; PRIMARY_FAILS=0
    fi
    if [ $FAILS -ge 3 ]; then
      echo "3 consecutive failed cycles - PARKING (3-strike rule) $(date)"
      touch "$STATE/STOP"
      echo "Parked $(date): 3 consecutive failed cycles. Last output: $OUT" > "$STATE/PARKED.md"
      break
    fi
    sleep 600; continue
  fi
  FAILS=0; PRIMARY_FAILS=0
  # Protected-file enforcement: revert any protected file the agent touched.
  for f in $PROTECTED; do
    if ! git diff --quiet HEAD -- "$f" 2>/dev/null; then
      echo "cycle $N: PROTECTED file modified by agent, reverting: $f"
      git checkout -- "$f" 2>/dev/null || true
    fi
  done
  # Code safety: the whole test suite must pass on what the agent leaves behind.
  if ! python3 tests/run_tests.py > "$STATE/post-cycle-tests.log" 2>&1; then
    echo "cycle $N: post-cycle tests FAILED - reverting strategies.py"
    git checkout -- src/harness/strategies.py 2>/dev/null || true
  fi
  echo "cycle $N finished $(date)"
  echo $((N+1)) > "$STATE/next_cycle.txt"
  git add -A >/dev/null 2>&1
  git -c user.email=d@vibebrowser.app -c user.name="Den (via trading harness)" commit -q -m "Harness cycle $N (pi/OpenRouter, $MODEL)" >/dev/null 2>&1 || true
done
echo "=== trading harness loop end $(date) ==="
