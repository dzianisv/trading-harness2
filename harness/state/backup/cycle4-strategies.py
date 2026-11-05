"""Strategy library. Every strategy maps (dates, closes_by_symbol, params)
to a list of per-day target-weight dicts.

Causality contract: the weight at index i is computed ONLY from closes[0..i].
The backtester applies weight[i] to the return from day i to day i+1, so no
lookahead is possible if this contract holds. tests/run_tests.py enforces it.
"""


def _sma(values, n):
    out = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def _rsi(values, period):
    out = [None] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    for i in range(period, len(values)):
        g = gains[i - period:i]
        l = losses[i - period:i]
        avg_l = sum(l) / period
        avg_g = sum(g) / period
        if avg_l == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def sma_trend(dates, closes, params):
    """Long a symbol (equal share of the book) while its fast SMA > slow SMA."""
    fast, slow = int(params["fast"]), int(params["slow"])
    symbols = sorted(closes)
    n = len(symbols)
    on = {}
    for s in symbols:
        f, sl = _sma(closes[s], fast), _sma(closes[s], slow)
        on[s] = [1.0 if (f[i] is not None and sl[i] is not None and f[i] > sl[i]) else 0.0
                 for i in range(len(dates))]
    return [{s: on[s][i] / n for s in symbols} for i in range(len(dates))]


def donchian_breakout(dates, closes, params):
    """Long while close is above the prior `entry`-day high (close-based channel);
    exit when close falls below the prior `exit`-day low."""
    n_in, n_out = int(params["entry"]), int(params["exit"])
    symbols = sorted(closes)
    n = len(symbols)
    series = {}
    for s in symbols:
        c = closes[s]
        w = [0.0] * len(dates)
        state = 0.0
        for i in range(len(dates)):
            if i >= n_in:
                hi = max(c[i - n_in:i])
                if c[i] > hi:
                    state = 1.0
            if state > 0 and i >= n_out:
                lo = min(c[i - n_out:i])
                if c[i] < lo:
                    state = 0.0
            w[i] = state
        series[s] = w
    return [{s: series[s][i] / n for s in symbols} for i in range(len(dates))]


def rsi_meanrev(dates, closes, params):
    """Buy oversold (RSI < entry), hold until overbought (RSI > exit)."""
    period, entry, exit_ = int(params["period"]), float(params["entry"]), float(params["exit"])
    symbols = sorted(closes)
    n = len(symbols)
    series = {}
    for s in symbols:
        r = _rsi(closes[s], period)
        w = [0.0] * len(dates)
        state = 0.0
        for i in range(len(dates)):
            if r[i] is not None:
                if state == 0.0 and r[i] < entry:
                    state = 1.0
                elif state > 0 and r[i] > exit_:
                    state = 0.0
            w[i] = state
        series[s] = w
    return [{s: series[s][i] / n for s in symbols} for i in range(len(dates))]


def buy_hold(dates, closes, params):
    symbols = sorted(closes)
    n = len(symbols)
    return [{s: 1.0 / n for s in symbols} for _ in dates]


STRATEGIES = {
    "sma_trend": sma_trend,
    "donchian_breakout": donchian_breakout,
    "rsi_meanrev": rsi_meanrev,
    "buy_hold": buy_hold,
}

# Bounded candidate grid for the improvement loop. Deliberately small:
# every extra trial raises the deflated-Sharpe bar for everyone.
PARAM_GRIDS = {
    "sma_trend": [
        {"fast": f, "slow": s}
        for f in (10, 20, 50) for s in (100, 150, 200) if f < s
    ],
    "donchian_breakout": [
        {"entry": e, "exit": x}
        for e in (20, 55) for x in (10, 20)
    ],
    "rsi_meanrev": [
        {"period": p, "entry": e, "exit": 70}
        for p in (2, 14) for e in (10, 30)
    ],
}
