"""PRACTICE ON THE PAST - how the Morning Breakout would have done on the last ~2 months.

Yahoo has no free OLD option prices, so the ticket price is ESTIMATED with the standard
option formula (Black-Scholes) from the real stock price. It's a rough guess, not exact:
  - "how jumpy" (volatility) = the stock's last 20 days of moves, plus 10%
  - we pay 2.5% above the fair price and sell 2.5% below it (the buy/sell gap)
  - prices are checked every 15 minutes, like the live bot
"""
import math

import pandas as pd

from . import config as C
from . import copycat, data, plain, skill, ticket

HALF_SPREAD = 0.025


fair_price = ticket.fair_price


def days_to_friday(day):
    """Calendar days to the soonest Friday that is at least MIN_DAYS_LEFT away."""
    d = (4 - day.weekday()) % 7
    return d if d >= C.MIN_DAYS_LEFT else d + 7


def jumpiness(bars, day):
    closes = bars[bars.index.normalize() < day].groupby(lambda i: i.normalize())["Close"].last()
    rets = closes.pct_change().dropna().tail(20)
    return max(0.12, float(rets.std() * math.sqrt(252) * 1.1)) if len(rets) >= 5 else None


def replay(setup, bars, ts):
    """One practice ticket on a past day -> (status, buy, sell) per share, or None."""
    day = ts.normalize()
    vol = jumpiness(bars, day)
    if not vol:
        return None
    step = 1 if setup["price"] < 200 else 5
    k = round(setup["price"] / step) * step
    if C.ITM_STEPS:                                           # one step "in the money"
        k = (math.ceil(setup["price"] / step) - C.ITM_STEPS) * step if setup["side"] == "call" \
            else (math.floor(setup["price"] / step) + C.ITM_STEPS) * step
    expiry = day + pd.Timedelta(days=days_to_friday(day), hours=16)
    years = lambda t: (expiry - t).total_seconds() / (365 * 86400)
    buy = fair_price(setup["side"], setup["price"], k, years(ts), vol) * (1 + HALF_SPREAD)
    if buy * 100 > C.MAX_TICKET_COST or buy <= 0.05:
        return None
    target, stop = buy * (1 + C.TARGET_PCT / 100), buy * (1 - C.STOP_PCT / 100)
    later = bars[(bars.index.normalize() == day) & (bars.index + pd.Timedelta(minutes=5) > ts)]
    sell, status = None, None
    for t, row in later.iloc[2::3].iterrows():                 # a check every 15 minutes
        now = t + pd.Timedelta(minutes=5)
        sell = fair_price(setup["side"], row["Close"], k, years(now), vol) * (1 - HALF_SPREAD)
        hm = now.strftime("%H:%M")
        status = "target" if sell >= target else "stop" if sell <= stop else "time" if hm >= C.SELL_BY else None
        if status:
            break
    return (status or "time", buy, sell) if sell is not None else None


def run(days=55, market=None, closes=None):
    if market is None:
        market = data.intraday(data.load_stocks() + [C.MARKET_TICKER], period="60d")
    if C.MARKET_TICKER not in market:
        return [], "Couldn't get past prices from Yahoo."
    if closes is None:
        closes = data.daily(list(market), period="2y") if C.TREND_FILTER else {}
    all_days = sorted({i.normalize() for i in market[C.MARKET_TICKER].index})[-days:]
    trades = []
    for day in all_days[10:]:                                   # first 10 days only warm up "how busy"
        ts = day + pd.Timedelta(hours=10, minutes=30)
        trend = {t: data.trend_on(closes.get(t), day) for t in market}
        for setup in skill.find(market, ts, trend):
            r = replay(setup, market[setup["ticker"]], ts)
            if r:
                trades.append({"date": f"{day:%Y-%m-%d}", "ticker": setup["ticker"], "side": setup["side"],
                               "status": r[0], "buy_price": r[1], "sell_price": r[2]})
    return trades, summary(trades, len(all_days) - 10)


def summary(trades, n_days, title="Morning Breakout"):
    if not trades:
        return f"In {n_days} past days, the bot found no tickets."
    df = pd.DataFrame(trades)
    df["pnl"] = [plain.pnl(t) for _, t in df.iterrows()]
    wins = int((df["pnl"] > 0).sum())
    total = df["pnl"].sum()
    lines = [f"{title} - practice on the past ({n_days} market days, ESTIMATED ticket prices):",
             f"🎟️ {len(df)} tickets: {wins} won, {len(df) - wins} lost ({100 * wins / len(df):.0f}% won)",
             f"💰 Total: {'+' if total >= 0 else '-'}{plain.money(abs(total))} pretend money (1 contract each)",
             f"📊 Average per ticket: {'+' if total >= 0 else '-'}{plain.money(abs(total / len(df)))}",
             f"✅ Hit the win price: {(df['status'] == 'target').sum()} | 🛑 Hit the stop: {(df['status'] == 'stop').sum()}"
             f" | ⏰ Sold at 3:30: {(df['status'] == 'time').sum()}",
             "This is a rough guess, not real ticket prices. The real test is the live practice."]
    return "\n".join(lines)


TRADES_URL = "https://raw.githubusercontent.com/tauhid97/day-trade-picks/main/data/backtest_trades.csv"


def past_picks():
    """Everything the day-trade bot picked: its own past-practice list + its live picks list."""
    old = data.day_trade_picks(TRADES_URL)
    new = data.day_trade_picks()
    df = pd.concat([x for x in [old, new] if len(x)], ignore_index=True) if len(old) or len(new) else pd.DataFrame()
    if not len(df):
        return df
    df["score"] = df["score"] if "score" in df else 0
    df["_live"] = (df["mode"] == "live").astype(int) if "mode" in df else 0
    df = df.sort_values(["date", "_live", "score"], ascending=[True, False, False], kind="stable")
    return df.drop_duplicates(["date", "ticker"])


def run_copied(picks=None, market=None, earnings=None, closes=None):
    """How the copied day-trade picks would have done as Call tickets (ESTIMATED prices)."""
    picks = past_picks() if picks is None else picks
    if not len(picks):
        return [], "Couldn't get the day-trade bot's past picks."
    if market is None:
        market = data.intraday(sorted(set(picks["ticker"])), period="60d")
    if not market:
        return [], "Couldn't get past prices from Yahoo."
    if closes is None:
        closes = data.daily(list(market), period="2y") if C.TREND_FILTER else {}
    skipped_trend = 0
    first = min(b.index.min() for b in market.values()).normalize() + pd.Timedelta(days=30)   # warm-up for "how jumpy"
    trades, skipped = [], {"earnings": 0, "pricey_or_cost": 0, "never": 0}
    for day, rows in picks.groupby("date"):
        d = pd.Timestamp(day).tz_localize(C.TIMEZONE)
        if d < first:
            continue
        bought, per_skill = 0, {}
        hits = []
        for p in rows.groupby("setup", sort=False).head(C.MAX_PER_SKILL).head(C.MAX_COPIED_PICKS).to_dict("records"):
            bars = market.get(p["ticker"])
            if bars is None or not (bars.index.normalize() == d).any():
                continue
            row = {"sent_at": p.get("published_at") if isinstance(p.get("published_at"), str)
                   else (d + pd.Timedelta(hours=11, minutes=30)).isoformat(),
                   "wait_type": p["order_type"], "wait_price": float(p["entry"])}
            start = pd.Timestamp(row["sent_at"]).tz_convert(C.TIMEZONE).ceil("15min")
            check = start
            while check.strftime("%H:%M") < C.BUY_BY:
                price = copycat.reached(row, bars, check)
                if price is not None:
                    hits.append((check, price, p))
                    break
                check += pd.Timedelta(minutes=15)
            else:
                skipped["never"] += 1
        for check, price, p in sorted(hits, key=lambda h: h[0]):
            if bought >= C.MAX_TICKETS_PER_DAY:
                break
            if per_skill.get(p["setup"], 0) >= C.MAX_PER_SKILL:
                continue
            exp = d.tz_localize(None) + pd.Timedelta(days=days_to_friday(d))
            dates = earnings(p["ticker"]) if earnings else data.earnings_dates(p["ticker"])
            if C.SKIP_EARNINGS and ticket.earnings_before(dates, d, exp):
                skipped["earnings"] += 1
                continue
            if C.TREND_FILTER and data.trend_on(closes.get(p["ticker"]), d) == "down":
                skipped_trend += 1
                continue
            r = replay({"price": price, "side": "call"}, market[p["ticker"]], check)
            if not r:
                skipped["pricey_or_cost"] += 1
                continue
            bought += 1
            per_skill[p["setup"]] = per_skill.get(p["setup"], 0) + 1
            trades.append({"date": day, "ticker": p["ticker"], "skill": p["setup"], "side": "call",
                           "status": r[0], "buy_price": r[1], "sell_price": r[2]})
    n_days = len({t["date"] for t in trades})
    text = summary(trades, n_days, "Day-trade skills as Call tickets") if trades else "The copied picks gave no tickets."
    if trades:
        df = pd.DataFrame(trades)
        df["pnl"] = [plain.pnl(t) for _, t in df.iterrows()]
        text += "\n" + "\n".join(plain.coach(df))
        text += (f"\n📅 Skipped for earnings: {skipped['earnings']} | 🕑 never reached the buy price: {skipped['never']}"
                 f" | 💸 too expensive: {skipped['pricey_or_cost']} | 📉 below the 200-day line: {skipped_trend}")
    return trades, text
