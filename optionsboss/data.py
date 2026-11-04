"""Free market data from Yahoo Finance (via yfinance). Option prices are about 15 minutes late."""
import time

import pandas as pd

from . import config as C

COLS = ["Open", "High", "Low", "Close", "Volume"]


def load_stocks(path=C.STOCKS_FILE):
    out = []
    for line in open(path):
        line = line.split("#")[0]
        out += [t.strip().upper() for t in line.split() if t.strip()]
    return list(dict.fromkeys(out))


def intraday(tickers, period="15d", interval="5m"):
    """5-minute candles during market hours, in New York time."""
    import yfinance as yf
    for attempt in range(3):
        try:
            df = yf.download(tickers, group_by="ticker", auto_adjust=False, threads=True,
                             progress=False, period=period, interval=interval, prepost=False)
            break
        except Exception as e:  # rate limits etc.
            print(f"download error ({e}); retrying...")
            time.sleep(10 * (attempt + 1))
    else:
        return {}
    out = {}
    for t in tickers:
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
        except KeyError:
            continue
        sub = sub[[c for c in COLS if c in sub.columns]].dropna(subset=["Close"])
        if not len(sub):
            continue
        idx = sub.index if sub.index.tz is not None else sub.index.tz_localize("UTC")
        sub = sub.copy()
        sub.index = idx.tz_convert(C.TIMEZONE)
        sub = sub.between_time("09:30", "15:59")
        if len(sub):
            out[t] = sub
    return out


def expirations(ticker):
    import yfinance as yf
    try:
        return list(yf.Ticker(ticker).options)
    except Exception as e:
        print("No ticket dates for", ticker, e)
        return []


def chain(ticker, expiry, side):
    """All the tickets (calls or puts) for one end date, as a table."""
    import yfinance as yf
    try:
        ch = yf.Ticker(ticker).option_chain(expiry)
    except Exception as e:
        print("No tickets for", ticker, expiry, e)
        return pd.DataFrame()
    return ch.calls if side == "call" else ch.puts


def quote(ticker, expiry, side, symbol):
    """The current buy (ask) and sell (bid) price of one ticket, or None."""
    df = chain(ticker, expiry, side)
    row = df[df["contractSymbol"] == symbol] if len(df) else df
    if not len(row):
        return None
    r = row.iloc[0]
    return {"bid": float(r["bid"] or 0), "ask": float(r["ask"] or 0), "last": float(r["lastPrice"] or 0)}


def day_trade_picks(url=C.PICKS_URL):
    """The day-trade bot's picks list (public file on GitHub), or an empty table."""
    import io

    import requests
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        print("Couldn't read the day-trade picks:", e)
        return pd.DataFrame()


def earnings_dates(ticker):
    """Past and coming earnings days for a company (empty for funds like SPY/QQQ)."""
    import yfinance as yf
    try:
        ed = yf.Ticker(ticker).get_earnings_dates(limit=12)
        return sorted({pd.Timestamp(i).tz_localize(None).normalize() for i in ed.index}) if ed is not None else []
    except Exception:
        return []


def jumpiness(ticker):
    """How much the stock really moves: last 20 days, yearly size (0.30 = 30%), or None."""
    import math

    import yfinance as yf
    try:
        d = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=False)
        c = d["Close"].squeeze().dropna()
        rets = c.pct_change().dropna().tail(20)
        return float(rets.std() * math.sqrt(252)) if len(rets) >= 10 else None
    except Exception:
        return None


def daily(tickers, period="1y"):
    """Daily closing prices {ticker: series with plain dates}, or {} if Yahoo is down."""
    import yfinance as yf
    try:
        df = yf.download(list(tickers), period=period, interval="1d", group_by="ticker",
                         progress=False, auto_adjust=False, threads=True)
    except Exception as e:
        print("No daily prices:", e)
        return {}
    out = {}
    for t in tickers:
        try:
            c = (df[t] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
        except KeyError:
            continue
        c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
        if len(c):
            out[t] = c
    return out


def trend_on(closes, day):
    """'up' if yesterday's close was above the 200-day average line, 'down' if below, None if unknown."""
    c = closes[closes.index < pd.Timestamp(day).tz_localize(None).normalize()] if closes is not None else []
    if len(c) < C.TREND_DAYS:
        return None
    return "up" if float(c.iloc[-1]) > float(c.tail(C.TREND_DAYS).mean()) else "down"


def trend(tickers, ts):
    """{ticker: 'up'/'down'/None} for today (uses only finished days)."""
    d = daily(tickers)
    return {t: trend_on(d.get(t), ts) for t in tickers}
