"""COMMANDS - answers Boss when he types to the Options Boss bot.

The bot only wakes up about every 15 minutes on market days, so answers can take that long.
It only ever answers Boss's own chat (TELEGRAM_CHAT_ID); messages from anyone else are ignored.

  /status       am I awake, and how is practice going
  /tickets      the practice tickets still open
  /scoreboard   every finished ticket added up
  /skills       the Coach: how each skill is doing
  anything else this help message
"""
import json
import os

import pandas as pd
import requests

from . import config as C
from . import plain
from .bot import FINISHED, load_tickets
from .notify import send

HELP = ("Hi Boss! I wake up about every 15 minutes on market days, so my answers can take that long.\n"
        "Things you can ask me:\n"
        "/status - am I working\n"
        "/tickets - the practice tickets still open\n"
        "/scoreboard - how all the tickets did\n"
        "/skills - the Coach: how each skill is doing")


def get_updates(offset):
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if not tok:
        return []
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", params=params, timeout=20)
    return r.json().get("result", []) if r.ok else []


def tickets_text(df):
    open_ = df[df["status"] == "open"] if len(df) else df
    wait = df[df["status"] == "waiting"] if len(df) else df
    if not len(open_) and not len(wait):
        return "No practice tickets open right now."
    lines = [f"Open practice tickets ({len(open_)}):", ""] if len(open_) else []
    for _, t in open_.iterrows():
        kind = "Call" if t["side"] == "call" else "Put"
        lines.append(f"{t['ticker']} {kind} {plain.strike(t['strike'])}, ends {plain.day(t['expiry'])}")
        lines.append(f"   Bought {plain.money(t['buy_price'])} | Win {plain.money(t['target'])} | Stop {plain.money(t['stop'])}")
    if len(wait):
        lines.append(f"👀 Waiting for their buy price: " + ", ".join(
            f"{t['ticker']} {plain.price(t['wait_price'])}" for _, t in wait.iterrows()))
    return "\n".join(lines)


def answer(text, df, now):
    word = (text or "").strip().split()[0].split("@")[0].lower() if (text or "").strip() else ""
    done = df[df["status"].isin(FINISHED)] if len(df) else df
    if word == "/status":
        t = now.tz_convert(C.TIMEZONE)
        return "\n".join([f"I'm awake, Boss! Checked at {t:%I:%M %p} ET ({t:%a %b} {t.day}).".replace(" 0", " "),
                          tickets_text(df), ""] + plain.scoreboard(done))
    if word == "/tickets":
        return tickets_text(df)
    if word == "/scoreboard":
        return "\n".join(plain.scoreboard(done))
    if word == "/skills":
        return "\n".join(plain.coach(done))
    return HELP


def handle(now=None):
    now = now or pd.Timestamp.now(tz="UTC")
    boss = str(os.getenv("TELEGRAM_CHAT_ID") or "")
    state = json.load(open(C.COMMANDS_STATE_FILE)) if os.path.exists(C.COMMANDS_STATE_FILE) else {}
    updates = get_updates(state.get("next_update"))
    if not updates:
        return
    df = load_tickets()
    for u in sorted(updates, key=lambda u: u["update_id"]):
        m = u.get("message") or {}
        if boss and str((m.get("chat") or {}).get("id")) == boss and "text" in m:
            send(answer(m["text"], df, now))
    state["next_update"] = max(u["update_id"] for u in updates) + 1
    os.makedirs(os.path.dirname(C.COMMANDS_STATE_FILE), exist_ok=True)
    json.dump(state, open(C.COMMANDS_STATE_FILE, "w"), indent=1)
