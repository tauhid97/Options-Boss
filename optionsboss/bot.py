"""The daily routine: morning scan -> watch the tickets -> sell -> nightly report card."""
import json
import os

import pandas as pd

from . import config as C
from . import coach, copycat, data, plain, skill, ticket
from .notify import send

COLS = ["date", "sent_at", "skill", "ticker", "side", "wait_type", "wait_price", "expiry", "strike", "symbol",
        "stock_price", "buy_price", "target", "stop", "reason", "status", "sell_price", "sold_at", "note", "style"]
FINISHED = ["target", "stop", "time"]
# other statuses: "waiting" (stock hasn't reached its buy price yet), "open" (bought, on paper),
# "skipped" (a safety skill said no), "missed" (never reached its buy price by 2 pm)


def now():
    return pd.Timestamp.now(tz=C.TIMEZONE)


def load_tickets():
    if os.path.exists(C.TICKETS_FILE):
        df = pd.read_csv(C.TICKETS_FILE, dtype={c: "object" for c in
                         ["status", "sold_at", "note", "skill", "wait_type", "symbol", "expiry", "sent_at", "style"]})
        df["skill"] = df["skill"].fillna(skill.NAME)
        return df
    return pd.DataFrame(columns=COLS)


def save_tickets(df):
    os.makedirs(os.path.dirname(C.TICKETS_FILE), exist_ok=True)
    for c in COLS:
        if c not in df:
            df[c] = None
    df[COLS].to_csv(C.TICKETS_FILE, index=False)


def scan(ts=None, force=False):
    """Once a day (10:15-11:30 ET): find setups, choose the tickets, send them to Boss."""
    ts = (ts or now()).floor("min")
    hm = ts.strftime("%H:%M")
    if not force and (ts.weekday() >= 5 or not (C.SCAN_START <= hm <= C.SCAN_END)):
        print(f"Outside the ticket window ({hm} ET).")
        return
    df = load_tickets()
    state = _state()
    if not force and state.get("scanned") == ts.strftime("%Y-%m-%d"):
        print("Already looked for tickets today.")
        return
    market = data.intraday(data.load_stocks() + [C.MARKET_TICKER])
    if not market or max(b.index.max() for b in market.values()).normalize() != ts.normalize():
        print("No market data for today (holiday or data down).")
        return
    picked, short, rows = [], [], []
    grade = coach.grade(df[df["status"].isin(FINISHED)] if len(df) else df, skill.NAME)
    trend = data.trend(list(market), ts) if C.TREND_FILTER else None
    for setup in skill.find(market, ts, trend):
        t, why = ticket.choose(setup, ts)
        base = {"date": ts.strftime("%Y-%m-%d"), "sent_at": ts.isoformat(), "skill": skill.NAME,
                "ticker": setup["ticker"], "side": setup["side"], "reason": skill.reason(setup)}
        if t:
            full = grade != coach.BENCHED and len(picked) < C.FULL_TICKETS_PER_DAY
            if full:
                picked.append((t, base["reason"]))
            else:
                short.append((t, coach.BADGE[grade] if grade != coach.LEARNING else ""))
            rows.append({**base, "status": "open", "style": "full" if full else "short", **t})
        else:
            rows.append({**base, "status": "skipped", "note": ticket.WHY[why]})
    text = plain.morning(picked, ts, [r for r in rows if r["status"] == "skipped"], short)
    print(text)
    send(text)
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True) if len(df) else pd.DataFrame(rows)
        save_tickets(df)
    state["scanned"] = ts.strftime("%Y-%m-%d")
    _save_state(state)


def copy_picks(ts=None):
    """11:00 am-1 pm ET, once a day: copy the day-trade bot's picks and start watching them."""
    ts = (ts or now()).floor("min")
    day, hm = ts.strftime("%Y-%m-%d"), ts.strftime("%H:%M")
    state = _state()
    if (ts.weekday() >= 5 or not (C.COPY_FROM <= hm <= C.COPY_UNTIL) or state.get("copied") == day
            or state.get("scanned") != day):           # no morning scan = market closed
        return
    df, rows = copycat.copy(load_tickets(), ts)
    if not rows:
        print("No day-trade picks for today yet.")
        return
    save_tickets(df)
    send(plain.watching(rows))
    state["copied"] = day
    _save_state(state)


def watch(ts=None):
    """Every ~15 minutes: buy (on paper) waiting picks that reached their buy price."""
    ts = (ts or now()).floor("min")
    if ts.weekday() >= 5:
        return
    df = load_tickets()
    if len(df) and (df["status"] == "waiting").any():
        save_tickets(copycat.watch(df, ts, send))


def check(t, q, hm):
    """What to do with one open ticket, given its price now: (status, sell price) or None to keep holding."""
    bid = q["bid"]
    if bid <= 0:
        return None                                  # no real price right now
    if bid >= t["target"]:
        return "target", bid
    if bid <= t["stop"]:
        return "stop", bid
    if hm >= C.SELL_BY:
        return "time", bid
    return None


def track(ts=None):
    """Every ~15 minutes: check the open tickets and sell (on paper) when a rule says so."""
    ts = ts or now()
    df = load_tickets()
    open_ = df[df["status"] == "open"] if len(df) else df
    if not len(open_):
        return
    hm = ts.strftime("%H:%M")
    for i, t in open_.iterrows():
        if hm < "09:45" or ts.weekday() >= 5:
            continue
        q = data.quote(t["ticker"], t["expiry"], t["side"], t["symbol"])
        late = t["date"] < ts.strftime("%Y-%m-%d")      # a ticket from an earlier day never stays open
        res = check(t, q, "23:59" if late else hm) if q else None
        if res:
            df.at[i, "status"], df.at[i, "sell_price"] = res[0], round(res[1], 2)
            df.at[i, "sold_at"] = ts.isoformat()
            send(plain.closed(df.loc[i]))
    save_tickets(df)


def night(ts=None):
    """After the close: the report card (once a day, only on market days)."""
    ts = ts or now()
    state = _state()
    today = ts.strftime("%Y-%m-%d")
    if (state.get("night") == today or state.get("scanned") != today    # no scan = market was closed
            or ts.strftime("%H:%M") < C.NIGHT_REPORT_AFTER):
        return
    df = load_tickets()
    done = df[df["status"].isin(FINISHED)] if len(df) else df
    todays = done[done["date"] == today] if len(done) else done
    other = df[(df["date"] == today) & df["status"].isin(["skipped", "missed"])] if len(df) else df
    no_buys = [f"{t['ticker']} ({t['skill']}): {t['note']}" for _, t in other.iterrows()]
    send(plain.night(todays, done, no_buys))
    state["night"] = today
    _save_state(state)


def _state():
    return json.load(open(C.NIGHT_STATE_FILE)) if os.path.exists(C.NIGHT_STATE_FILE) else {}


def _save_state(s):
    os.makedirs(os.path.dirname(C.NIGHT_STATE_FILE), exist_ok=True)
    json.dump(s, open(C.NIGHT_STATE_FILE, "w"), indent=1)
