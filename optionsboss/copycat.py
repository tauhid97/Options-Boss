"""DAY-TRADE SKILLS - Options Boss copies the day-trade bot's daily stock picks (all its skills,
including any new ones it learns) and turns them into Call tickets.

Explained like you're 5:
  Around 11:30 am the day-trade bot picks stocks it thinks will go UP, each with a "buy price".
  Options Boss watches those stocks. If a stock reaches its buy price, Options Boss sends a
  Call ticket (after the safety skills say OK). If it never gets there by 2 pm, we skip it.
"""
import pandas as pd

from . import config as C
from . import data, plain, ticket


def todays_picks(picks, day, have):
    """The day-trade bot's picks for `day`, "live" skills first, minus stocks we already have."""
    if picks is None or not len(picks) or "date" not in picks:
        return []
    p = picks[picks["date"].astype(str) == day].copy()
    p = p[~p["ticker"].isin(have)].drop_duplicates("ticker")
    p["_live"] = (p.get("mode", "practice") == "live").astype(int)
    p = p.sort_values("_live", ascending=False, kind="stable")
    return p.head(C.MAX_COPIED_PICKS).to_dict("records")


def to_row(pick, ts):
    sent = str(pick.get("published_at") or "") or ts.isoformat()
    return {"date": ts.strftime("%Y-%m-%d"), "sent_at": sent, "skill": pick["setup"],
            "ticker": pick["ticker"], "side": "call", "wait_type": pick.get("order_type", "buy_stop"),
            "wait_price": float(pick["entry"]), "reason": plain.kid_reason(pick["setup"], pick.get("reason")),
            "status": "waiting"}


def reached(row, bars, ts):
    """Did the stock reach its buy price after the pick was sent? Returns the price now, or None."""
    start = pd.Timestamp(row["sent_at"])
    start = start.tz_convert(C.TIMEZONE) if start.tzinfo else start.tz_localize(C.TIMEZONE)
    seen = bars[(bars.index >= start.floor("5min")) & (bars.index + pd.Timedelta(minutes=5) <= ts)
                & (bars.index.normalize() == ts.normalize())]
    if not len(seen):
        return None
    hit = (seen["Low"].min() <= row["wait_price"]) if row["wait_type"] == "buy_limit" \
        else (seen["High"].max() >= row["wait_price"])
    return float(seen["Close"].iloc[-1]) if hit else None


def copy(df, ts):
    """Adds today's day-trade picks as 'waiting' rows. Returns (df, new rows) - new rows is [] if none yet."""
    day = ts.strftime("%Y-%m-%d")
    have = set(df[df["date"] == day]["ticker"]) if len(df) else set()
    rows = [to_row(p, ts) for p in todays_picks(data.day_trade_picks(), day, have)]
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True) if len(df) else pd.DataFrame(rows)
    return df, rows


def bought_today(df, day):
    return int(((df["date"] == day) & df["status"].isin(["open", "target", "stop", "time"])).sum()) if len(df) else 0


def watch(df, ts, send):
    """Every ~15 minutes: buy (on paper) the waiting picks whose stock reached its buy price."""
    day, hm = ts.strftime("%Y-%m-%d"), ts.strftime("%H:%M")
    waiting = df[df["status"] == "waiting"] if len(df) else df
    if not len(waiting):
        return df
    old = waiting[waiting["date"] < day].index
    df.loc[old, ["status", "note"]] = ["missed", "never reached its buy price"]
    waiting = waiting[waiting["date"] == day]
    if not len(waiting):
        return df
    if hm >= C.BUY_BY:
        df.loc[waiting.index, ["status", "note"]] = ["missed", "never reached its buy price"]
        return df
    bars = data.intraday(sorted(set(waiting["ticker"])), period="5d")
    for i, row in waiting.iterrows():
        if row["ticker"] not in bars:
            continue
        price = reached(row, bars[row["ticker"]], ts)
        if price is None:
            continue
        if bought_today(df, day) >= C.MAX_TICKETS_PER_DAY:
            df.loc[i, ["status", "note"]] = ["skipped", "we already have enough tickets today"]
            continue
        t, why = ticket.choose({"ticker": row["ticker"], "side": "call", "price": price}, ts)
        if not t:
            df.loc[i, ["status", "note"]] = ["skipped", ticket.WHY[why]]
            send(plain.skipped(row, ticket.WHY[why]))
            continue
        for k, v in t.items():
            df.at[i, k] = v
        df.at[i, "status"], df.at[i, "sent_at"] = "open", ts.isoformat()
        send(plain.buy_now(t, row["skill"], row["reason"], ts))
    return df
