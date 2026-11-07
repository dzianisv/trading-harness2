# Design: Paper Trading on Google's Harness²

Build a paper-trading system **on the real framework**: google-research/harness2
(Google Cloud AI Research + Northwestern, arXiv:2610.14224, Apache 2.0).
Not a home-grown loop with the same name — the framework itself, plus one
custom benchmark adapter for trading. Models: **OpenRouter free tier only**.

Paper only. No broker integration, no real account, no credentials in the
environment — same rule as before.

## How Harness² works (the parts we use)

- The model stays frozen. What evolves is the **harness**: 8 editable
  components around the model — system prompt, guardrails, memory, tool
  guidance, subagents, skills, scripts, plugins.
- **Task-level recursion:** per task, an editor proposes two edits (one
  *invariant* — how the agent works; one *domain* — what a practitioner
  knows). Each candidate harness runs the same task (probe), and a composer
  builds the refined harness from the contrast between executions.
- **Harnessing-level recursion:** after each task, a reflector writes the
  adopted harness + evidence-backed lessons into a persistent *improvement
  harness* (memory) that guides the next task.
- Executors ("substrates"): **OpenCode** (default) or Codex. Models are set
  in `.env` in OpenCode `provider/model` syntax:
  `HARNESS2_SOLVER_MODEL` (executor), `HARNESS2_IMPROVER_MODEL` (editor /
  composer / reflector; empty = same as solver), `HARNESS2_JUDGE_MODEL`
  (bare model ID; each adapter supplies its own judge route).
- Runs are benchmark-shaped: `harness2-setup <bench>`, `harness2-check`,
  `harness2 --bench <bench> --k 1 --mode parallel|sequential`,
  `harness2-judge`, `harness2-report`. Stock benchmarks: JobBench, LAB,
  WorkBuddy-Bench. **A custom task domain = a custom benchmark adapter.**
  That adapter is the main thing we build.

## Architecture

```
google-research/harness2 (unmodified, uv-installed)
        │  solver/improver via OpenCode substrate
        ▼
OpenCode ── provider openrouter ──► OpenRouter free model
        │
        ▼
benchmark adapter "papertrade" (new, ours)
  ├─ tasks: trading episodes (see below)
  ├─ environment: deterministic trading core (already in this repo)
  │    data.py (Yahoo daily bars, cached) · backtest.py (costs always on)
  │    paper.py (sim account) · risk.py (caps, halt, kill switch)
  └─ judge: deterministic scorer (code, not an LLM)
        after-cost CAGR/Sharpe vs buy&hold · max drawdown · OOS folds
        deflated Sharpe over ALL trials ever (state/trials.json graveyard)
```

Why a code judge: stock Harness² composes edits from behavioral contrast
with **no ground truth and no correctness check**. Markets have ground
truth (P&L after costs), so the adapter scores probes with the existing
falsification gates. Harness² evolves the *trader*; the gates still decide
what is true. Risk caps live in environment code the agent cannot edit —
Harness² guardrails (c2) are text; ours are also enforced in `risk.py`.

## The trading task

- **Episode (one task):** a fixed window of daily bars, SPY/QQQ, $100 sim
  cash. Probe substrate = historical windows (re-runnable, so candidate
  harnesses can be compared on the *same* task). The most recent window is
  report-only holdout. A live paper day/week is the outer-loop task that
  carries the adopted harness forward.
- **Agent's job inside an episode:** inspect data, design/revise a strategy
  in `strategies.py` via the environment tools, run the backtest tool, and
  deliver the strategy + a short evidence report. Fills simulated at close
  with spread + slippage, strictly causal (no lookahead — integrity-tested).
- **One Harness² step (k=1)** ≈ 4 task executions + editor/composer/
  reflector sessions. On the free quota (~1,000 req/day, shared with the
  RFS loop) that means: **k=1, sequential mode, a few episodes per day.**

## Harness components, trading edition (c1..c8)

| Component | Content |
|---|---|
| system prompt | Trader procedure: episode steps, evidence rules, deliverable format |
| guardrails | Paper-only, no-lookahead, universe SPY/QQQ, risk caps (mirrored in code) |
| memory | Seeded from LEARNINGS.md + the trials graveyard; reflector appends lessons |
| tool guidance | How/when to call the data, backtest and paper tools; cost model notes |
| subagents | Researcher (propose strategies) vs evaluator (attack them) split |
| skills | Strategy-family playbooks (trend, mean reversion, breakout) as on-demand files |
| scripts | Data fetch, scorer, report generators |
| plugins | Halt/kill-switch middleware — outside the agent's editable set |

## Models: OpenRouter free tier

`.env` (Harness² root):

```
HARNESS2_SOLVER_MODEL=openrouter/nvidia/nemotron-3.5-lightning:free
HARNESS2_IMPROVER_MODEL=            # empty → improver uses the solver model
OPENROUTER_API_KEY=<existing key>   # read by OpenCode's openrouter provider
```

- Key: the existing `~/.config/rfs/openrouter.key` (Den approved unattended
  use 2026-10-23). Its limit is $0 → free models only, by construction.
- Fallback model: `openrouter/poolside/laguna-s-2.1:free` — a one-line
  solver change if lightning degrades.
- Caveats, stated plainly:
  - The paper's headline gains used **Claude Opus 4.8 as the editor**. A
    free model as improver is unproven; expect smaller gains. Cost is $0.
  - Stock setup routes judges through Vertex AI and its install checks run
    `gcloud auth … print-access-token`. Our judge is code, so Vertex is
    not on the critical path — but `harness2-check` for a stock bench may
    still demand GCP config. Our adapter defines its own check; verify in
    the smoke step before assuming.
  - Harness² scrubs provider/cloud tokens from the agent env (SCRUB_ENV);
    the agent keeps only the key its own model call needs.

## Safety

- Stock Harness² gives the executor **unrestricted network egress** (and
  Codex runs sandbox-off). For trading: run in this VM with egress limited
  to the data endpoints + OpenRouter; no broker anything exists to reach.
- Protected paths (environment + judge code) live outside the harness tree
  the editor can rewrite. An adopted harness can change how the agent
  trades on paper; it cannot change the scorer, the caps, or the data.

## What stays, what was removed

- **Stays (adapter environment):** `src/` core, `scripts/` CLIs (become
  adapter tools), `tests/`, `config.json` caps, `state/` (graveyard +
  paper account), `LEARNINGS.md` (memory seed).
- **Removed (the home-grown detour):** `harness/` (pi runner + cycle
  protocol), `PLAN.md`, the Muse supervisor cron. Git history keeps them.

## Build steps

1. Install Harness²; run `harness2-demo` (deterministic editors, no
   credentials) — proves the framework runs here.
2. OpenCode + OpenRouter smoke: solver string above answers through
   OpenCode. **Gate:** OpenCode on this VM is currently broken (session
   deadlock, see AGENTS.md) — if the smoke fails, run Harness² where
   OpenCode works (Den's laptop) or fix OpenCode first. No step 3 before
   this passes.
3. Write the `papertrade` adapter: task definitions (episode windows),
   environment wiring to the existing core, code judge, report.
4. Seed the harness tree (table above); first k=1 sequential run on one
   historical episode; verify judge artifacts under `runs/`.
5. Cadence: a thin supervisor cron (launch + digest only) runs one
   sequential step per weekday; live paper state advances daily.

## Open risks

- Free-model improver quality (above). If it flatlines for 3 runs, park
  and report — do not silently switch to a paid editor.
- Free quota contention with the RFS loop (both on one key).
- Adapter effort is real work: Harness² ships no trading adapter, and its
  benchmark plumbing (setup/check/judge/report) must be matched, not
  approximated.
