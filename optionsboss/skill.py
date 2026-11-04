"""MORNING BREAKOUT - Options Boss's own skill (PRACTICE). The only one that can give Puts.

Explained like you're 5:
  The first 30 minutes of the day draw a "morning box" (highest and lowest price).
  If a stock climbs OUT THE TOP of the box, is up on the day, is above its average price
  for the day (VWAP), and lots of people are trading it -> CALL (bet it keeps going up).
  If it falls OUT THE BOTTOM, the same but upside down -> PUT (bet it keeps going down).
  The whole market (SPY) must be going the same way, so we're not swimming against the tide.
"""
import pandas as pd

from . import config as C


def look(bars, ts):
    """bars = 5-minute candles (several days) for one stock; ts = now.
    Returns what the stock is doing today, or None if there's not enough data."""
    done = bars[bars.index + pd.Timedelta(minutes=5) <= ts]      # only finished candles
    day = ts.normalize()
    today = done[done.index.normalize() == day]
    before = done[done.index.normalize() < day]
    if before.empty or today.empty:
        return None
    box = today[today.index.strftime("%H:%M") < C.OPENING_RANGE_END]
    if len(box) < 6:
        return None
    prev_close = float(before["Close"].iloc[-1])
    price = float(today["Close"].iloc[-1])
    typical = (today["High"] + today["Low"] + today["Close"]) / 3
    vwap = float((typical * today["Volume"]).sum() / max(today["Volume"].sum(), 1))
    # how busy: today's volume so far vs. the same time of day on the last 10 days
    cut = ts.strftime("%H:%M")
    past = [g[g.index.strftime("%H:%M") < cut]["Volume"].sum() for _, g in before.groupby(before.index.normalize())][-10:]
    usual = sum(past) / len(past) if past else 0
    return {"price": price, "prev_close": prev_close, "move_pct": 100 * (price / prev_close - 1),
            "box_high": float(box["High"].max()), "box_low": float(box["Low"].min()), "vwap": vwap,
            "rvol": float(today["Volume"].sum() / usual) if usual else 0.0}


def side_for(s):
    """'call', 'put' or None for one stock's look()."""
    if not s or s["rvol"] < C.MIN_RVOL:
        return None
    if s["price"] > s["box_high"] and s["price"] > s["vwap"] and s["move_pct"] >= C.MIN_MOVE_PCT:
        return "call"
    if s["price"] < s["box_low"] and s["price"] < s["vwap"] and s["move_pct"] <= -C.MIN_MOVE_PCT:
        return "put"
    return None


def find(market, ts):
    """market = {ticker: bars}. Returns the best setups, strongest first (at most MAX_BREAKOUT_TICKETS)."""
    spy = look(market[C.MARKET_TICKER], ts) if C.MARKET_TICKER in market else None
    tide = "call" if spy and spy["move_pct"] > 0 else "put" if spy and spy["move_pct"] < 0 else None
    found = []
    for t, bars in market.items():
        s = look(bars, ts)
        side = side_for(s)
        if side and side == tide:
            found.append({"ticker": t, "side": side, "score": abs(s["move_pct"]) * s["rvol"], **s})
    found.sort(key=lambda f: -f["score"])
    return found[:C.MAX_BREAKOUT_TICKETS]


NAME = "Morning Breakout"


def reason(f):
    way = "UP" if f["side"] == "call" else "DOWN"
    edge = "top" if f["side"] == "call" else "bottom"
    return (f"{f['ticker']} is going {way} today ({f['move_pct']:+.1f}%). It broke out the {edge} of its "
            f"morning box, and {f['rvol']:.1f}x more people than usual are trading it.")
