"""SCOREBOARD PAGE - writes docs/index.html from data/tickets.csv."""
import html
import os

import pandas as pd

from . import config as C
from . import plain
from .bot import FINISHED, load_tickets


def build():
    df = load_tickets()
    done = df[df["status"].isin(FINISHED)] if len(df) else df
    rows = []
    bought = df[df["status"].isin(FINISHED + ["open"])] if len(df) else df
    for _, t in bought.iloc[::-1].iterrows():
        kind = "Call" if t["side"] == "call" else "Put"
        if t["status"] in FINISHED:
            p = plain.pnl(t)
            res = f"<b class={'win' if p > 0 else 'loss'}>{'+' if p > 0 else '-'}{plain.money(abs(p))}</b>"
        else:
            res = "still open"
        rows.append(f"<tr><td>{t['date']}</td><td>{html.escape(t['ticker'])} {kind} {plain.strike(t['strike'])}"
                    f"<br><small>{html.escape(str(t['skill']))}</small></td>"
                    f"<td>{plain.money(t['buy_price'])}</td><td>{res}</td></tr>")
    summary = "<br>".join(html.escape(x) for x in plain.scoreboard(done))
    coach = "<br>".join(html.escape(x) for x in plain.coach(done))
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Options Boss</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:auto;padding:16px;background:#fff;color:#111}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:6px;border-bottom:1px solid #ddd;text-align:left}}
.win{{color:#0a7a2f}}.loss{{color:#b00020}}.box{{background:#f4f4f4;padding:12px;border-radius:8px}}
@media (prefers-color-scheme:dark){{body{{background:#111;color:#eee}}.box{{background:#222}}td,th{{border-color:#333}}
.win{{color:#5fd38a}}.loss{{color:#ff6b81}}}}</style></head><body>
<h1>🎟️ Options Boss</h1><p>Practice option tickets. <b>Pretend money only</b>, 1 contract each.</p>
<div class="box">{summary}</div><h2>Coach</h2><div class="box">{coach}</div><h2>Every ticket</h2>
<table><tr><th>Day</th><th>Ticket</th><th>Paid</th><th>Result</th></tr>{''.join(rows) or '<tr><td colspan=4>No tickets yet.</td></tr>'}</table>
<p><small>Learning tool, not financial advice. Options can go to $0.</small></p></body></html>"""
    os.makedirs(os.path.dirname(C.REPORT_FILE), exist_ok=True)
    open(C.REPORT_FILE, "w").write(page)
