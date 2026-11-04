"""TICKET PICKER - chooses the exact option (end date + strike price) for a setup,
and runs the 4 option safety skills:

  🎯 Right ticket  - the soonest end date 2-10 days away, the strike closest to the stock price
  👥 Busy enough   - only popular tickets with a small gap between the buy and sell price
  🚫 Too pricey    - skip tickets priced for much more jumping than the stock really does
  📅 Earnings day  - skip if the company reports earnings before the ticket ends
"""
import math

import pandas as pd

from . import config as C
from . import data

WHY = {"no_date": "there was no ticket ending 2-10 days from now",
       "no_ticket": "no ticket was popular enough, close enough, and under $1,000",
       "pricey": "tickets were too pricey right now (people expect big jumps)",
       "earnings": "the company reports earnings before the ticket ends (prices jump wildly)",
       "trend": "the stock is below its 200-day line (its long-term trend is down), so no Call"}


def pick_expiry(dates, today):
    for d in sorted(dates):
        days = (pd.Timestamp(d) - today.tz_localize(None).normalize()).days
        if C.MIN_DAYS_LEFT <= days <= C.MAX_DAYS_LEFT:
            return d
    return None


def pick_strike(df, price, side="call"):
    """The best ticket in a chain (table) near the stock price, or None.
    With ITM_STEPS = 1 it picks one strike "in the money" (a Call's strike just below the price)."""
    if df is None or not len(df):
        return None
    df = df.copy()
    df = df[(df["bid"] > 0) & (df["ask"] > 0)]
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df = df[(100 * (df["ask"] - df["bid"]) / df["mid"] <= C.MAX_SPREAD_PCT)
            & (df["openInterest"].fillna(0) >= C.MIN_OPEN_INTEREST)
            & (df["ask"] * 100 <= C.MAX_TICKET_COST)]
    if not len(df):
        return None
    best = df.loc[(df["strike"] - price).abs().idxmin()]
    if C.ITM_STEPS:
        inside = df[df["strike"] < price] if side == "call" else df[df["strike"] > price]
        inside = inside.sort_values("strike", ascending=(side != "call"))
        if len(inside) >= C.ITM_STEPS:
            best = inside.iloc[C.ITM_STEPS - 1]
    return best


def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def fair_price(side, stock, strike, years, vol):
    """Black-Scholes price of one option (per share), no interest rate."""
    if years <= 0 or vol <= 0:
        return max(0.0, stock - strike) if side == "call" else max(0.0, strike - stock)
    d1 = (math.log(stock / strike) + 0.5 * vol * vol * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    if side == "call":
        return stock * _cdf(d1) - strike * _cdf(d2)
    return strike * _cdf(-d2) - stock * _cdf(-d1)


def implied_jump(side, stock, strike, years, price):
    """How much jumping the ticket's price expects (yearly, 0.30 = 30%). Worked out ourselves,
    because Yahoo's own number is often wrong."""
    lo, hi = 0.01, 5.0
    if price <= fair_price(side, stock, strike, years, lo):
        return lo
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fair_price(side, stock, strike, years, mid) < price else (lo, mid)
    return (lo + hi) / 2


def too_pricey(side, stock, strike, years, price, real_jump):
    if not real_jump:
        return False                                  # unknown -> don't block
    return implied_jump(side, stock, strike, years, price) > C.MAX_PRICEY * max(real_jump, 0.12)


def earnings_before(dates, today, expiry):
    """True if an earnings day falls from today up to the ticket's end date."""
    a, b = today.tz_localize(None).normalize(), pd.Timestamp(expiry).normalize()
    return any(a <= pd.Timestamp(d) <= b for d in dates)


def choose(setup, ts):
    """Turns a setup into a full ticket. Returns (ticket, None), or (None, why it was skipped)."""
    exp = pick_expiry(data.expirations(setup["ticker"]), ts)
    if not exp:
        return None, "no_date"
    if C.SKIP_EARNINGS and earnings_before(data.earnings_dates(setup["ticker"]), ts, exp):
        return None, "earnings"
    row = pick_strike(data.chain(setup["ticker"], exp, setup["side"]), setup["price"], setup["side"])
    if row is None:
        return None, "no_ticket"
    years = max((pd.Timestamp(exp) + pd.Timedelta(hours=16) - ts.tz_localize(None)).total_seconds(), 3600) / (365 * 86400)
    mid = (float(row["bid"]) + float(row["ask"])) / 2
    if too_pricey(setup["side"], setup["price"], float(row["strike"]), years, mid, data.jumpiness(setup["ticker"])):
        return None, "pricey"
    buy = round(float(row["ask"]), 2)             # pay the ask, so the practice fill is honest
    return {"ticker": setup["ticker"], "side": setup["side"], "expiry": exp,
            "strike": float(row["strike"]), "symbol": row["contractSymbol"],
            "buy_price": buy, "target": round(buy * (1 + C.TARGET_PCT / 100), 2),
            "stop": round(buy * (1 - C.STOP_PCT / 100), 2), "stock_price": round(setup["price"], 2)}, None
