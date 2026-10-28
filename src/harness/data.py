"""Market data: Yahoo Finance chart API (free, no key), Stooq as fallback,
cached locally as CSV. Stdlib only — no third-party dependencies anywhere in
this project, so the daily job can never break on a pip install.

One consistent source feeds signals, backtests and paper fills; the cache is
the single source of truth inside a run.
"""
import csv
import io
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _parse_csv(text):
    bars = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            bars.append({
                "date": row["Date"],
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if row.get("Volume") not in (None, "", "N/D") else 0.0,
            })
        except (ValueError, KeyError, TypeError):
            continue
    bars.sort(key=lambda b: b["date"])
    return bars


def _to_csv(bars):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
    for b in bars:
        w.writerow([b["date"], b["open"], b["high"], b["low"], b["close"], int(b["volume"])])
    return out.getvalue()


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _fetch_yahoo(symbol):
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}?range=10y&interval=1d"
        for attempt in range(2):
            try:
                payload = json.loads(_get(url))
                result = payload["chart"]["result"][0]
                ts = result["timestamp"]
                q = result["indicators"]["quote"][0]
                bars = []
                for i, t in enumerate(ts):
                    if q["close"][i] is None:
                        continue
                    bars.append({
                        "date": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(),
                        "open": q["open"][i], "high": q["high"][i], "low": q["low"][i],
                        "close": q["close"][i], "volume": q["volume"][i] or 0.0,
                    })
                bars.sort(key=lambda b: b["date"])
                if len(bars) >= 300:
                    return bars
                last_err = f"only {len(bars)} bars"
            except Exception as e:  # noqa: BLE001 - any failure -> retry/fallback
                last_err = str(e)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Yahoo fetch failed for {symbol}: {last_err}")


def _fetch_stooq(symbol):
    text = _get(f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d")
    if text.lstrip().startswith("<"):
        raise RuntimeError("Stooq served a bot-check page")
    bars = _parse_csv(text)
    if len(bars) < 300:
        raise RuntimeError(f"Stooq returned {len(bars)} bars")
    return bars


def fetch_daily(symbol, max_age_hours=6):
    """Daily bars for a US ticker, ascending by date. Cached on disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{symbol}.csv")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_hours * 3600:
        with open(path) as f:
            bars = _parse_csv(f.read())
        if len(bars) >= 300:
            return bars
    errors = []
    for source in (_fetch_yahoo, _fetch_stooq):
        try:
            bars = source(symbol)
            break
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    else:
        raise RuntimeError(f"All data sources failed for {symbol}: {errors}")
    with open(path, "w") as f:
        f.write(_to_csv(bars))
    return bars


def aligned(bars_by_symbol):
    """Intersect trading days across symbols. Returns (dates, closes_by_symbol)."""
    symbols = sorted(bars_by_symbol)
    common = None
    for s in symbols:
        days = {b["date"] for b in bars_by_symbol[s]}
        common = days if common is None else (common & days)
    dates = sorted(common)
    closes = {}
    for s in symbols:
        by_date = {b["date"]: b["close"] for b in bars_by_symbol[s]}
        closes[s] = [by_date[d] for d in dates]
    return dates, closes


def load_universe(symbols, years=None):
    bars = {s: fetch_daily(s) for s in symbols}
    dates, closes = aligned(bars)
    if years:
        keep = int(years * 252) + 1
        if len(dates) > keep:
            dates = dates[-keep:]
            closes = {s: c[-keep:] for s, c in closes.items()}
    return dates, closes
