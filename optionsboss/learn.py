"""🧠 PATTERN NOTEBOOK - the bot writes down HOW each ticket looked, and learns which looks lose.

Explained like you're 5:
  Every ticket gets a few "pattern notes" the moment it's bought: what time it was, how busy the
  stock was, was the whole market going our way, how far the stock had already moved, did it open
  with a jump, Call or Put, and how much the ticket cost.
  Every Friday after the report card, the Coach looks at the finished tickets: "When the market went
  the other way, our tickets lost a lot more." But one week can be luck, so a pattern only counts if
  the SAME thing also happened on the last ~2 months of past prices (estimated ticket prices).
  Then the Coach only SUGGESTS a rule. Boss types /yes or /no. Everything stays PRACTICE.
"""
import json
import os

import pandas as pd

from . import config as C
from . import coach

KEYS = ["time", "side", "market", "moved", "gap", "busy", "price"]

LABEL = {
    ("time", "early"): "it was bought before 11 am",
    ("time", "midday"): "it was bought between 11 am and 12:30 pm",
    ("time", "afternoon"): "it was bought after 12:30 pm",
    ("side", "call"): "it's a Call",
    ("side", "put"): "it's a Put",
    ("market", "with"): "the whole market was going our way",
    ("market", "against"): "the whole market was going the other way",
    ("market", "flat"): "the whole market was flat",
    ("moved", "wrong way"): "the stock was going the other way that day",
    ("moved", "under 1%"): "the stock had moved less than 1% our way",
    ("moved", "1-3%"): "the stock had already moved 1-3% our way",
    ("moved", "3%+"): "the stock had already moved 3% or more (late to the party)",
    ("gap", "none"): "the stock opened near yesterday's price",
    ("gap", "with"): "the stock opened with a jump our way",
    ("gap", "against"): "the stock opened with a jump the other way",
    ("busy", "quiet"): "fewer people than usual were trading the stock",
    ("busy", "normal"): "a normal number of people were trading the stock",
    ("busy", "busy"): "2x or more people than usual were trading the stock",
    ("price", "under $100"): "the ticket cost under $100",
    ("price", "$100-300"): "the ticket cost $100-300",
    ("price", "$300+"): "the ticket cost $300 or more",
}


# ---------- 1. writing the notes ----------

def _today(bars, ts):
    """Price now, yesterday's close, today's open and how busy, from 5-minute candles. None if unknown."""
    if bars is None or not len(bars):
        return None
    done = bars[bars.index + pd.Timedelta(minutes=5) <= ts]
    day = ts.normalize()
    today = done[done.index.normalize() == day]
    before = done[done.index.normalize() < day]
    if today.empty or before.empty:
        return None
    cut = ts.strftime("%H:%M")
    past = [g[g.index.strftime("%H:%M") < cut]["Volume"].sum()
            for _, g in before.groupby(before.index.normalize())][-10:]
    usual = sum(past) / len(past) if past else 0
    return {"price": float(today["Close"].iloc[-1]), "prev": float(before["Close"].iloc[-1]),
            "open": float(today["Open"].iloc[0]),
            "rvol": float(today["Volume"].sum() / usual) if usual else None}


def notes(bars, spy_bars, side, ts, buy_price=None):
    """The pattern notes for one ticket, as text like 'time=early;side=call;market=with;...'."""
    way = 1 if side == "call" else -1
    n = {"time": "early" if ts.strftime("%H:%M") < "11:00" else
         "midday" if ts.strftime("%H:%M") < "12:30" else "afternoon", "side": side}
    s = _today(bars, ts)
    if s:
        moved = way * 100 * (s["price"] / s["prev"] - 1)
        n["moved"] = "wrong way" if moved < 0 else "under 1%" if moved < 1 else "1-3%" if moved < 3 else "3%+"
        gap = 100 * (s["open"] / s["prev"] - 1)
        n["gap"] = "none" if abs(gap) < 0.5 else "with" if way * gap > 0 else "against"
        if s["rvol"] is not None:
            n["busy"] = "quiet" if s["rvol"] < 1 else "normal" if s["rvol"] < 2 else "busy"
    m = _today(spy_bars, ts)
    if m:
        spy = 100 * (m["price"] / m["prev"] - 1)
        n["market"] = "flat" if abs(spy) < 0.2 else "with" if way * spy > 0 else "against"
    if buy_price is not None and buy_price == buy_price:
        cost = float(buy_price) * 100
        n["price"] = "under $100" if cost < 100 else "$100-300" if cost < 300 else "$300+"
    return ";".join(f"{k}={n[k]}" for k in KEYS if k in n)


def parse(text):
    if not isinstance(text, str) or not text:
        return {}
    return dict(p.split("=", 1) for p in text.split(";") if "=" in p)


# ---------- 2. learned rules (only the ones Boss said /yes to) ----------

def _load():
    if os.path.exists(C.LEARNED_RULES_FILE):
        return json.load(open(C.LEARNED_RULES_FILE))
    return {"rules": [], "waiting": None, "declined": []}


def _save(s):
    os.makedirs(os.path.dirname(C.LEARNED_RULES_FILE), exist_ok=True)
    json.dump(s, open(C.LEARNED_RULES_FILE, "w"), indent=1)


def rule_text(r):
    if r["key"] == "side":
        return f"skip {'Calls' if r['value'] == 'call' else 'Puts'}"
    return f"skip tickets when {LABEL.get((r['key'], r['value']), r['key'] + ' = ' + r['value'])}"


def blocked(note_text):
    """The learned rule that says 'skip this ticket', or None."""
    n = parse(note_text)
    for r in _load()["rules"]:
        if n.get(r["key"]) == r["value"]:
            return r
    return None


def skip_note(r):
    return f"🧠 learned rule: {rule_text(r)}"


def answer(word, rest=""):
    """/yes, /no, /rules, /forget -> the reply text."""
    s = _load()
    w = s.get("waiting")
    if word == "/yes":
        if not w:
            return "No new rule is waiting for a yes right now, Boss."
        s["rules"].append({**w, "added": pd.Timestamp.now(tz=C.TIMEZONE).strftime("%Y-%m-%d")})
        s["waiting"] = None
        _save(s)
        return f"✅ Got it, Boss. From now on I'll {rule_text(w)}. (Still PRACTICE. Type /forget to undo it.)"
    if word == "/no":
        if not w:
            return "No new rule is waiting right now, Boss."
        s["declined"].append({"key": w["key"], "value": w["value"]})
        s["waiting"] = None
        _save(s)
        return f"👍 OK, I won't {rule_text(w)}. I won't ask about that one again."
    if word == "/forget":
        if not s["rules"]:
            return "There are no learned rules to forget, Boss."
        r = s["rules"].pop()
        _save(s)
        return f"🗑️ Forgot the newest rule: {rule_text(r)}."
    lines = ["🧠 Learned rules (Boss said yes):"] + [f"• {rule_text(r)} (since {r.get('added', '?')})"
                                                     for r in s["rules"]] if s["rules"] else \
        ["🧠 No learned rules yet. The Coach suggests one on Fridays when a pattern keeps losing."]
    if w:
        lines.append(f"⏳ Waiting for your answer: {rule_text(w)}? Type /yes or /no.")
    return "\n".join(lines)


# ---------- 3. the Friday lesson ----------

def table(done):
    """One row per finished ticket that has notes: its notes + its score (R)."""
    rows = []
    if done is None or not len(done) or "notes" not in done:
        return pd.DataFrame(columns=KEYS + ["r"])
    for _, t in done.iterrows():
        n = parse(t.get("notes"))
        if n and t.get("sell_price") == t.get("sell_price") and t.get("sell_price") is not None:
            rows.append({**n, "r": coach.r_of(t)})
    return pd.DataFrame(rows, columns=KEYS + ["r"])


def groups(tab, min_n):
    """Every pattern with at least min_n tickets: (key, value, n, avg R, avg R of all the others)."""
    out = []
    for k in KEYS:
        if k not in tab:
            continue
        for v, g in tab.groupby(k):
            rest = tab[tab[k] != v]
            if len(g) >= min_n and len(rest):
                out.append((k, v, len(g), float(g["r"].mean()), float(rest["r"].mean())))
    return out


def weak(tab, min_n, worse_by):
    """Patterns that lose AND are clearly worse than the rest, worst first."""
    w = [g for g in groups(tab, min_n) if g[3] < 0 and g[4] - g[3] >= worse_by]
    return sorted(w, key=lambda g: g[3] - g[4])


def holds_on_past(past, key, value):
    """Did the same pattern also lose, and do worse than the rest, on past prices?"""
    if past is None or not len(past) or key not in past:
        return None
    g, rest = past[past[key] == value], past[past[key] != value]
    if len(g) < C.LEARN_PAST_MIN or not len(rest):
        return None
    return {"n": len(g), "avg": float(g["r"].mean()), "rest": float(rest["r"].mean()),
            "ok": bool(g["r"].mean() < 0 and g["r"].mean() < rest["r"].mean())}


def past_table():
    """Notes + scores for the estimated past tickets (Morning Breakout + copied picks, ~2 months)."""
    from . import backtest
    a, _ = backtest.run()
    b, _ = backtest.run_copied(earnings=lambda t: [])
    rows = [{**parse(t.get("notes")), "r": coach.r_of(t)} for t in a + b if t.get("notes")]
    return pd.DataFrame(rows, columns=KEYS + ["r"])


def _r(x):
    return f"{x:+.2f}R"


def lesson(done, past=None, get_past=past_table):
    """The '🧠 What I learned this week' message. May set a rule waiting for Boss's /yes."""
    tab = table(done)
    lines = ["🧠 What I learned this week", ""]
    if len(tab) < C.LEARN_MIN_TICKETS:
        lines += [f"Only {len(tab)} finished ticket{'s' if len(tab) != 1 else ''} with pattern notes so far. "
                  f"I need {C.LEARN_MIN_TICKETS} before I trust any pattern, so no new rules yet.",
                  "(1R = what the stop would lose on a ticket.)"]
        return "\n".join(lines)
    all_g = groups(tab, C.LEARN_MIN_GROUP)
    if all_g:
        best = max(all_g, key=lambda g: g[3])
        lines.append(f"👍 Best: when {LABEL.get(best[:2], best[1])}: {best[2]} tickets, {_r(best[3])} a ticket.")
        worst = min(all_g, key=lambda g: g[3])
        lines.append(f"👎 Worst: when {LABEL.get(worst[:2], worst[1])}: {worst[2]} tickets, {_r(worst[3])} a ticket.")
    s = _load()
    have = {(r["key"], r["value"]) for r in s["rules"]} | {(r["key"], r["value"]) for r in s["declined"]}
    cands = [g for g in weak(tab, C.LEARN_MIN_GROUP, C.LEARN_WORSE_BY) if g[:2] not in have]
    if s.get("waiting"):
        lines += ["", f"⏳ Still waiting for your answer: {rule_text(s['waiting'])}? Type /yes or /no."]
        return "\n".join(lines)
    if not cands:
        lines += ["", "No pattern is clearly losing yet, so no new rule this week."]
        return "\n".join(lines)
    if past is None:
        try:
            past = get_past()
        except Exception as e:
            print("Past check skipped:", e)
            past = None
    for k, v, n, avg, rest in cands:
        h = holds_on_past(past, k, v)
        if h and h["ok"]:
            s["waiting"] = {"key": k, "value": v, "n": n, "avg": round(avg, 2), "past_n": h["n"],
                            "past_avg": round(h["avg"], 2)}
            _save(s)
            lines += ["", f"💡 Idea: {rule_text(s['waiting'])}.",
                      f"   Live practice: {n} tickets like that, {_r(avg)} a ticket (the others: {_r(rest)}).",
                      f"   Past ~2 months (estimated prices): {h['n']} tickets, {_r(h['avg'])} a ticket "
                      f"(the others: {_r(h['rest'])}). Same story, so it's not just luck.",
                      "Type /yes to use this rule, or /no to skip it. (Still PRACTICE.)"]
            return "\n".join(lines)
        why = "the past prices didn't show the same thing" if h else "there weren't enough past tickets to check"
        lines.append(f"🤔 {LABEL.get((k, v), v)} lost lately ({n} tickets, {_r(avg)}), but {why}, "
                     "so it may be luck. No rule.")
    return "\n".join(lines)


def backfill(df, ts, get_bars=None):
    """Older finished tickets (from before the notebook) get their notes from Yahoo's 5-minute
    prices, which go back about 60 days. Returns how many got notes."""
    from . import data
    if not len(df):
        return 0
    if "notes" not in df:
        df["notes"] = None
    df["notes"] = df["notes"].astype("object")
    old = (pd.Timestamp(ts).tz_localize(None) - pd.Timedelta(days=55)).strftime("%Y-%m-%d")
    need = df[df["status"].isin(["target", "stop", "time"]) & df["notes"].isna()
              & (df["date"] >= old) & df["sent_at"].notna()]
    if not len(need):
        return 0
    bars = (get_bars or (lambda t: data.intraday(t, period="60d")))(sorted(set(need["ticker"]) | {C.MARKET_TICKER}))
    for i, t in need.iterrows():
        when = pd.Timestamp(t["sent_at"])
        when = (when.tz_convert(C.TIMEZONE) if when.tzinfo else when.tz_localize(C.TIMEZONE)).floor("min")
        df.at[i, "notes"] = notes(bars.get(t["ticker"]), bars.get(C.MARKET_TICKER), t["side"], when, t["buy_price"])
    return len(need)


def weekly(ts, send, get_bars=None):
    """Friday, after the report card, once a week."""
    from . import bot
    state = bot._state()
    week = f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]}"
    if (ts.weekday() != C.LEARN_DAY or state.get("night") != ts.strftime("%Y-%m-%d")
            or state.get("lesson") == week):
        return
    df = bot.load_tickets()
    try:
        if backfill(df, ts, get_bars):
            bot.save_tickets(df)
    except Exception as e:
        print("Notes for older tickets skipped:", e)
    done = df[df["status"].isin(bot.FINISHED)] if len(df) else df
    send(lesson(done))
    state["lesson"] = week
    bot._save_state(state)
